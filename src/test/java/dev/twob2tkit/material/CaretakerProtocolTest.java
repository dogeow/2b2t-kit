package dev.twob2tkit.material;

import com.google.gson.*;
import java.nio.file.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class CaretakerProtocolTest {
    @TempDir Path directory;
    private JsonObject fixture()throws Exception{
        try(var input=getClass().getResourceAsStream("/caretaker/registered-potatoes-cows-sheep.json")){
            assertNotNull(input);return JsonParser.parseString(new String(input.readAllBytes(),StandardCharsets.UTF_8)).getAsJsonObject();
        }
    }
    private CaretakerProtocol.Installation installed()throws Exception{
        Path game=directory.resolve("game with spaces"),config=game.resolve("config/twob2tkit"),runtime=config.resolve("material-worker");Files.createDirectories(runtime);
        Path python=directory.resolve("venv with spaces/python");Files.createDirectories(python.getParent());Files.writeString(python,"not launched by this fixture");assertTrue(python.toFile().setExecutable(true));
        Files.writeString(runtime.resolve("runtime-python.txt"),python+"\n");
        var manifest=new JsonObject();manifest.addProperty("schema",1);var files=new JsonObject();manifest.add("files",files);
        for(String file:List.of("farm_caretaker_cli.py","farm_caretaker.py","farm_caretaker_stages.py","requirements.txt")){
            Path source=runtime.resolve(file);Files.writeString(source,"# verified fixture for "+file);
            files.addProperty(file,HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(Files.readAllBytes(source))));
        }
        Files.writeString(runtime.resolve("worker-manifest.json"),manifest.toString());Files.writeString(config.resolve("farm-caretaker-profile.json"),fixture().toString());
        return CaretakerProtocol.installed(game);
    }
    private JsonObject journal(CaretakerProtocol.Installation install){
        var j=new JsonObject();j.addProperty("schema",1);j.add("profile",install.profile().deepCopy());j.addProperty("enabled",false);j.addProperty("paused",true);
        j.addProperty("cycle",0);j.addProperty("ai_calls",0);j.addProperty("stage","harvest_store");j.addProperty("reason","NOT_STARTED");j.add("pending",JsonNull.INSTANCE);return j;
    }
    private JsonObject ready(CaretakerProtocol.Installation install){
        var s=new JsonObject();s.addProperty("connected",true);s.addProperty("server","simpcraft.com:25565");s.addProperty("dimension","minecraft:overworld");
        s.addProperty("world_session","world");s.addProperty("control_revision",4);s.addProperty("time",1000);s.addProperty("health",20);s.addProperty("food",20);
        s.addProperty("manual_movement",false);s.addProperty("under_water",false);s.addProperty("screen","");s.add("pos",install.profile().get("park_target").deepCopy());return s;
    }
    @Test void fullRegisteredFixtureKeepsDefaultsCapabilitiesAndExactTypedCliArguments()throws Exception{
        var install=installed();assertEquals("31f1ed743135ec8202d0",install.key());
        assertTrue(CaretakerProtocol.summary(install.profile()).contains("24 格土豆田 · 牛、羊"));
        for(String action:List.of("run","pause","stop","status","resume","inspect-pending")){
            assertEquals(List.of(install.python().toString(),"-u",install.script().toString(),"--game-dir",install.game().toString(),"--profile",install.profilePath().toString(),action),install.command(action));
        }
        assertThrows(IllegalArgumentException.class,()->install.command("run; arbitrary shell"));assertNull(CaretakerProtocol.journal(install));
    }
    @Test void importerTamperMissingManifestTraversalAndShellInterpreterAreRejected()throws Exception{
        var install=installed();Path runtime=install.script().getParent();Files.writeString(runtime.resolve("farm_caretaker_stages.py"),"modified import");
        Path tamperedGame=install.game();assertThrows(IllegalStateException.class,()->CaretakerProtocol.installed(tamperedGame));
        install=installed();Path selectedGame=install.game();runtime=install.script().getParent();var manifest=CaretakerProtocol.read(runtime.resolve("worker-manifest.json"));
        manifest.getAsJsonObject("files").addProperty("../outside.py","0".repeat(64));Files.writeString(runtime.resolve("worker-manifest.json"),manifest.toString());
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.installed(selectedGame));
        install=installed();Path shellGame=install.game();Files.writeString(install.script().resolveSibling("runtime-python.txt"),"/bin/sh\n");
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.installed(shellGame));
        Files.delete(install.script().resolveSibling("worker-manifest.json"));assertThrows(IllegalStateException.class,()->CaretakerProtocol.installed(shellGame));
    }
    @Test void originalJournalPendingIsNeverConvertedToCompletedOrRestartedAndControlsOnlyWriteControl()throws Exception{
        var install=installed();Files.createDirectories(install.directory());var j=journal(install);var pending=new JsonObject();pending.addProperty("stage","harvest_store");pending.addProperty("directory","original-cycle");j.add("pending",pending);
        Path file=install.directory().resolve("caretaker.json");Files.writeString(file,j.toString());String before=Files.readString(file);
        assertTrue(CaretakerProtocol.status(CaretakerProtocol.journal(install),false).contains("原动作待核对"));
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,ready(install),j,1000,false));
        CaretakerProtocol.control(install,"pause");var control=CaretakerProtocol.read(install.directory().resolve("control.json"));
        assertEquals("pause",control.get("action").getAsString());assertEquals(install.key(),control.get("key").getAsString());assertEquals(before,Files.readString(file));
    }
    @Test void locksManualWorkLeaseStaleStateAndForeignWorldAllBlockExplicitRun()throws Exception{
        var install=installed();var initial=ready(install);assertDoesNotThrow(()->CaretakerProtocol.requireReady(install,initial,null,1000,false));
        for(String flag:List.of("manual_movement","borer_active","navigating","printing","native_material_busy","guard_busy","health_recovery_hold")){
            var s=initial.deepCopy();s.addProperty(flag,true);assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,s,null,1000,false));
        }
        var stale=initial.deepCopy();assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,stale,null,4000,false));
        var foreign=initial.deepCopy();foreign.addProperty("server","another.example");assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,foreign,null,1000,false));
        var work=initial.deepCopy();var lease=new JsonObject();lease.addProperty("kind","materials");work.add("supervision_lease",lease);assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,work,null,1000,false));
        Path automation=install.game().resolve("config/twob2tkit/automation");Files.createDirectories(automation);Files.writeString(automation.resolve("safety-hold.json"),"{\"active\":true}");
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireUnlocked(automation,initial));
    }
    @Test void explicitLaunchMayReuseOnlyVerifiedIdleGuardedParkingAndKitUiMustCloseFirst()throws Exception{
        var install=installed();var s=ready(install);var lease=new JsonObject();lease.addProperty("kind","parking");lease.addProperty("world_session","world");lease.addProperty("revision",4);s.add("supervision_lease",lease);
        s.addProperty("guard_armed",true);s.addProperty("guard_pve_only",true);s.addProperty("flight",true);
        assertDoesNotThrow(()->CaretakerProtocol.requireReady(install,s,null,1000,false));
        s.addProperty("screen","KitFormScreen");assertDoesNotThrow(()->CaretakerProtocol.requireReady(install,s,null,1000,true));
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,s,null,1000,false));
        s.addProperty("screen","InventoryScreen");assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,s,null,1000,true));
    }
    @Test void enabledJournalDoesNotClaimLiveWorkerAndMissingProbeCannotGrantParkingOwnership(){
        var probe=new JsonObject();probe.addProperty("enabled",true);probe.addProperty("worker_running",false);
        assertFalse(CaretakerProtocol.workerRunning(probe));probe.addProperty("worker_running",true);assertTrue(CaretakerProtocol.workerRunning(probe));
        probe.remove("worker_running");assertThrows(IllegalStateException.class,()->CaretakerProtocol.workerRunning(probe));
    }
    @Test void alteredProfileOrJournalDirectoryCannotBypassOriginalCycleRegistration()throws Exception{
        var install=installed();Path home=install.directory().getParent();Files.createDirectories(home);var registry=new JsonObject();registry.add("profile",install.profile());registry.addProperty("directory",directory.resolve("new-out").toString());Files.writeString(home.resolve("registry.json"),registry.toString());
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.installed(install.game()));
        registry.addProperty("directory",install.directory().toString());registry.getAsJsonObject("profile").addProperty("adult_keep",21);Files.writeString(home.resolve("registry.json"),registry.toString());
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.installed(install.game()));
    }
    @Test void pendingReviewNamesOriginalFetchMissingProofAndChangedWorldWithoutWritingHistory()throws Exception{
        var install=installed();Path cycle=install.directory().resolve("cycle-000001"),stage=cycle.resolve("harvest_store");Files.createDirectories(stage);
        var j=journal(install);j.addProperty("cycle",1);j.addProperty("reason","CONTROL_CHANGED");
        var pending=new JsonObject();pending.addProperty("stage","harvest_store");pending.addProperty("directory",stage.toString());j.add("pending",pending);
        var original=new JsonObject();original.addProperty("id",1);original.addProperty("directory",cycle.toString());original.addProperty("world_session","old-world");j.add("current_cycle",original);
        var record=new JsonObject();record.addProperty("cycle_id",1);record.addProperty("stage","harvest_store");record.addProperty("world_session","old-world");
        var intent=new JsonObject();intent.addProperty("operation","fetch");var params=new JsonObject();var targets=new JsonObject();targets.addProperty("minecraft:potato",5);params.add("targets",targets);intent.add("params",params);record.add("pending",intent);
        Path file=stage.resolve("stage.json"),journal=install.directory().resolve("caretaker.json");Files.writeString(file,record.toString());Files.writeString(journal,j.toString());
        String before=Files.readString(file),bookBefore=Files.readString(journal);var state=ready(install);
        String review=String.join("\n",CaretakerProtocol.pendingReview(install,j,state));
        assertTrue(review.contains("土豆种薯 5"));assertTrue(review.contains("不是已取出的数量"));assertTrue(review.contains("该旧动作缺少开始前库存"));
        assertTrue(review.contains("当前世界会话已改变"));assertTrue(review.contains(file.toString()));assertTrue(review.contains("日志没有开箱事件也不足"));
        assertTrue(CaretakerProtocol.status(j,false).contains("原动作期间控制版本改变"));
        assertEquals(before,Files.readString(file));assertEquals(bookBefore,Files.readString(journal));
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.requireReady(install,state,j,1000,false));
        var preview=CaretakerProtocol.archivePreview(install);assertEquals(1,preview.cycle());
        assertEquals(HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bookBefore.getBytes(StandardCharsets.UTF_8))),preview.pendingSha256());
        assertEquals(List.of(install.python().toString(),"-u",install.script().toString(),"--game-dir",install.game().toString(),"--profile",install.profilePath().toString(),
            "archive-pending","--acknowledge-unknown-outcome","--expected-pending-sha256",preview.pendingSha256()),install.archiveCommand(preview.pendingSha256()));
        assertThrows(IllegalArgumentException.class,()->install.command("archive-pending"));
        assertThrows(IllegalArgumentException.class,()->install.archiveCommand("invalid"));
        assertEquals(bookBefore,Files.readString(journal));
        pending.addProperty("directory",directory.resolve("outside").toString());
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.pendingReview(install,j,state));
    }
    @Test void archivePreviewRequiresAnOriginalPendingCycleAndNeverWritesControls()throws Exception{
        var install=installed();Files.createDirectories(install.directory());Path path=install.directory().resolve("caretaker.json");
        var book=journal(install);Files.writeString(path,book.toString());String before=Files.readString(path);
        assertThrows(IllegalStateException.class,()->CaretakerProtocol.archivePreview(install));
        assertEquals(before,Files.readString(path));assertFalse(Files.exists(install.directory().resolve("control.json")));
    }
}
