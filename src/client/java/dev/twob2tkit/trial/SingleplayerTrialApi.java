package dev.twob2tkit.trial;
import com.google.gson.*;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitKeys;
import net.minecraft.client.Minecraft;
import net.minecraft.resources.Identifier;
import net.minecraft.world.Difficulty;
import net.minecraft.world.level.*;
import net.minecraft.world.level.levelgen.WorldOptions;
import net.minecraft.world.level.levelgen.presets.WorldPresets;
import java.nio.file.*;
import java.util.UUID;

/** Native trial lifecycle mailbox. Never accepts model-generated commands. */
public final class SingleplayerTrialApi {
    private static String last="";private static long nextPoll;
    private SingleplayerTrialApi(){}
    private static Path folder(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/singleplayer-trial");}
    private static String text(JsonObject j,String k){return j.has(k)?j.get(k).getAsString():"";}
    public static void create(Minecraft c){
        requireEmpty(c);String name="Clef Dragon Trial "+UUID.randomUUID().toString().substring(0,8);
        try{String level=net.minecraft.util.FileUtil.findAvailableName(c.getLevelSource().getBaseDir(),name,"");
            var settings=new LevelSettings(name,GameType.SURVIVAL,new LevelSettings.DifficultySettings(Difficulty.NORMAL,false,false),false,WorldDataConfiguration.DEFAULT);
            c.createWorldOpenFlows().createFreshLevel(level,settings,WorldOptions.defaultWithRandomSeed(),WorldPresets::createNormalWorldDimensions,c.screen);
        }catch(Exception e){throw new IllegalStateException("无法通过原版流程新建试验世界",e);}
    }
    private static void requireEmpty(Minecraft c){if(c.player!=null||c.level!=null||c.getSingleplayerServer()!=null||c.getCurrentServer()!=null)
        throw new IllegalStateException("先保存退出当前世界；不会替换已打开的世界");}
    private static void current(Minecraft c,JsonObject r){
        if(c.player==null||c.level==null||c.getSingleplayerServer()==null||c.getCurrentServer()!=null||c.getSingleplayerServer().isPublished())
            throw new IllegalStateException("只允许当前未开放局域网的单人存档");
        String world=c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize().toString();
        if(!world.equals(text(r,"world_id"))||!dev.twob2tkit.automation.AutomationBridge.materialJobWorldSession(c).equals(text(r,"world_session"))
            ||!r.has("expected_revision")||r.get("expected_revision").getAsLong()!=dev.twob2tkit.automation.AutomationBridge.currentRevision()
            ||KitKeys.manualMovementDown(c))throw new IllegalStateException("单人存档或控制版本已变化");
    }
    public static void tick(Minecraft c){
        long now=System.currentTimeMillis();if(now<nextPoll)return;nextPoll=now+250;
        Path root=folder(c),request=root.resolve("api-request.json");if(!Files.isRegularFile(request))return;
        JsonObject result=new JsonObject();String id="";
        try{if(Files.size(request)>8192)throw new IllegalArgumentException("Trial request too large");var r=JsonParser.parseString(Files.readString(request)).getAsJsonObject();
            id=text(r,"id");if(!id.matches("[A-Za-z0-9_-]{1,96}")||id.equals(last)||Files.exists(root.resolve("api-reply-"+id+".json"))||Files.exists(root.resolve("api-intent-"+id+".json")))return;last=id;
            result.addProperty("id",id);result.addProperty("protocol",1);
            if(!r.has("protocol")||r.get("protocol").getAsInt()!=1||!r.has("expires_at")
                ||r.get("expires_at").getAsLong()<now||r.get("expires_at").getAsLong()-now>30000)throw new IllegalArgumentException("Trial request expired");
            String command=text(r,"command");
            Files.createDirectories(root);Files.writeString(root.resolve("api-intent-"+id+".json"),r.toString(),StandardOpenOption.CREATE_NEW);
            switch(command){
                case "status"->{}
                case "quit_game"->{requireEmpty(c);c.stop();}
                case "create_world"->create(c);
                case "open_world"->{
                    requireEmpty(c);String requested=text(r,"world_id");Path save=Path.of(requested).toAbsolutePath().normalize();
                    Path saves=c.getLevelSource().getBaseDir().toAbsolutePath().normalize();
                    if(!save.getParent().equals(saves)||Files.isSymbolicLink(save)||!Files.isRegularFile(save.resolve("level.dat")))throw new IllegalArgumentException("Only one existing local save is allowed");
                    c.createWorldOpenFlows().openWorld(save.getFileName().toString(),()->c.setScreen(new net.minecraft.client.gui.screens.TitleScreen()));
                }
                case "start"->{current(c,r);SingleplayerTrialRuntime.start(c,KitClient.config());}
                case "pause","resume","cancel"->{current(c,r);SingleplayerTrialRuntime.control(c,command);}
                default->throw new IllegalArgumentException("Unsupported trial lifecycle command");
            }
            result.addProperty("phase","done");result.addProperty("detail","试验请求已接收；实际运行状态另行核对");
            result.add("trial_identity",SingleplayerTrialRuntime.snapshot(c));
        }catch(Exception e){result.addProperty("id",id);result.addProperty("phase","error");result.addProperty("detail",e.getMessage());}
        if(!id.matches("[A-Za-z0-9_-]{1,96}"))return;
        try{Files.createDirectories(root);Path temp=root.resolve("api-reply-"+id+".tmp");Files.writeString(temp,result.toString());
            Files.move(temp,root.resolve("api-reply-"+id+".json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        }catch(Exception e){KitClient.LOGGER.warn("Could not persist trial API receipt",e);}
    }
}
