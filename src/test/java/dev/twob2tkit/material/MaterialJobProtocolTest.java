package dev.twob2tkit.material;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class MaterialJobProtocolTest {
    @TempDir Path temporary;
    private JsonObject context() { return JsonParser.parseString("{\"server\":\"local\",\"dimension\":\"minecraft:overworld\",\"world_session\":\"world-a\",\"expected_revision\":3,\"start_pos\":[1,2,3]}").getAsJsonObject(); }
    private JsonObject status() { return JsonParser.parseString("{\"schema\":1,\"id\":\"job-a\",\"state\":\"crafting\",\"phase\":\"制作\",\"detail\":\"核对背包\",\"done\":32,\"total\":64,\"updated_at\":2000,\"native_task_session\":\"native-a\"}").getAsJsonObject(); }
    @Test void itemRequestCopiesWorldScopeAndPreservesExactCount() {
        var context = context(); var request = MaterialJobProtocol.request("job-a", "item", Map.of("minecraft:white_concrete", 800), "", context, 1000);
        context.addProperty("expected_revision", 9);
        assertEquals(3, request.getAsJsonObject("context").get("expected_revision").getAsInt());
        assertEquals(800, request.getAsJsonObject("targets").get("minecraft:white_concrete").getAsInt());
        assertEquals(1000, request.get("created_at").getAsLong()); assertFalse(request.has("projection_key"));
    }
    @Test void refusesInvalidQuantityOrUnsafelyNamedItem() {
        for (int amount : new int[]{0,-1,1_000_001}) assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.request("job-a","item",Map.of("minecraft:stone", amount),"", context(),1000));
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.request("job-a","item",Map.of("minecraft:stone; touch /tmp/bad",1),"",context(),1000));
    }
    @Test void projectionMustCarryActualSelectedIdentity() {
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.request("job-a","projection",Map.of(),"",context(),1000));
        var request = MaterialJobProtocol.request("job-a","projection",Map.of(),"ship-origin-and-rotation",context(),1000);
        assertEquals("ship-origin-and-rotation",request.get("projection_key").getAsString());
    }
    @Test void malformedWorldContextIsRejectedBeforeLaunch() {
        var data = context(); data.addProperty("expected_revision",-1);
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.request("job-a","item",Map.of("minecraft:stone",1),"",data,1000));
        data.addProperty("expected_revision",1); data.add("start_pos",JsonParser.parseString("[1,2]"));
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.request("job-a","item",Map.of("minecraft:stone",1),"",data,1000));
    }
    @Test void staleOrDifferentJobReceiptCannotBecomeCurrentProgress() {
        var data = status(); data.addProperty("id", "other-job");
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.progress(data,"job-a",1000,2000));
        data.addProperty("id","job-a"); data.addProperty("updated_at",999);
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.progress(data,"job-a",1000,2000));
        data.addProperty("updated_at",8001);
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.progress(data,"job-a",1000,2000));
    }
    @Test void malformedOrNegativeCountsNeverLookCompleted() {
        var data = status(); data.addProperty("done",-1);
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.progress(data,"job-a",1000,2000));
        data.addProperty("done",0); data.remove("total");
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.progress(data,"job-a",1000,2000));
        data.addProperty("total",64); data.addProperty("state","invented-success");
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.progress(data,"job-a",1000,2000));
    }
    @Test void partialAndOverTargetCountsStayTruthful() {
        var data = status(); data.addProperty("done",80);
        var progress = MaterialJobProtocol.progress(data,"job-a",1000,2000);
        assertEquals(80,progress.done()); assertEquals(64,progress.total()); assertEquals("native-a",progress.taskSession());
        assertFalse(MaterialJobProtocol.terminal("paused")); assertTrue(MaterialJobProtocol.terminal("cancelled"));
    }
    @Test void shellCharactersAndSpacesAreLiteralArguments() throws Exception {
        Path python = temporary.resolve("python runtime"), worker = temporary.resolve("worker ' with spaces.py");
        Files.writeString(python,"#!/bin/sh\nexit 0\n"); assertTrue(python.toFile().setExecutable(true)); Files.writeString(worker,"");
        var command = MaterialJobProtocol.command(python,worker,temporary,temporary.resolve("request $(touch).json"),temporary.resolve("output dir"));
        assertEquals(python.toString(),command.getFirst()); assertEquals(worker.toString(),command.get(2));
        assertEquals(temporary.resolve("request $(touch).json").toString(),command.get(6));
        assertFalse(command.contains("sh")); assertFalse(command.contains("-c"));
    }
    @Test void missingWorkerFailsBeforeAnyProcessIsStarted() {
        assertThrows(IllegalStateException.class, () -> MaterialJobProtocol.command(temporary.resolve("missing"),temporary.resolve("worker.py"),temporary,temporary,temporary));
    }
    @Test void controlsAreExplicitAndTimestamped() {
        var control = MaterialJobProtocol.control("job-a","pause",3200);
        assertEquals("job-a",control.get("id").getAsString()); assertEquals(3200,control.get("created_at").getAsLong());
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.control("job-a","reconnect",3300));
    }
    @Test void resumeCarriesFreshExplicitContextWithoutReusingOldRevision() {
        var current = context(); current.addProperty("expected_revision",42);
        var control = MaterialJobProtocol.resume("job-a",3200,current);
        current.addProperty("expected_revision",43);
        assertEquals(42,control.getAsJsonObject("context").get("expected_revision").getAsInt());
        assertEquals("world-a",control.getAsJsonObject("context").get("world_session").getAsString());
        assertThrows(IllegalArgumentException.class, () -> MaterialJobProtocol.resume("job-a",3300,null));
    }
    @Test void blockedWorkerExitRetainsActionableReasonRatherThanGenericError() {
        var result = MaterialJobProtocol.exited(2,false,"blocked","缺少可达水源");
        assertEquals("blocked",result.state());assertEquals("缺少可达水源",result.detail());
    }
    @Test void completionRequiresVerifiedReceiptAndSuccessfulProcessExit() {
        assertEquals("completed",MaterialJobProtocol.exited(0,false,"completed","背包已核对").state());
        assertEquals("failed",MaterialJobProtocol.exited(2,false,"completed","背包已核对").state());
        assertEquals("failed",MaterialJobProtocol.exited(0,false,"crafting","制作中").state());
        assertEquals("cancelled",MaterialJobProtocol.exited(0,true,"crafting","制作中").state());
    }
    @Test void installerRuntimeWinsWhenHmclOverridesJavaHome() throws Exception {
        Path worker=temporary.resolve("material_jobs_cli.py");
        String venv="/Users/sam/Library/Application Support/MinecraftDecisions/venv/bin/python";
        Files.writeString(temporary.resolve("runtime-python.txt"),venv+"\n");
        assertEquals(Path.of(venv),MaterialJobProtocol.resolvePython("",worker,"/Applications","/Applications"));
    }
    @Test void explicitConfigWinsAndEnvironmentHomePrecedesIsolatedProperty() throws Exception {
        Path worker=temporary.resolve("material_jobs_cli.py");
        assertEquals(Path.of("/Users/real/Library/Application Support/MinecraftDecisions/venv/bin/python"),
            MaterialJobProtocol.resolvePython("",worker,"/Users/real","/Applications"));
        Files.writeString(temporary.resolve("runtime-python.txt"),"/installed/python\n");
        assertEquals(Path.of("/custom/venv/bin/python"),MaterialJobProtocol.resolvePython("/custom/venv/bin/python",worker,"/Users/real","/Applications"));
    }
    @Test void propertyHomeIsLastFallbackOnly() {
        assertEquals(Path.of("/Users/fallback/Library/Application Support/MinecraftDecisions/venv/bin/python"),
            MaterialJobProtocol.resolvePython(null,temporary.resolve("worker.py"),null,"/Users/fallback"));
    }
    @Test void malformedRuntimeRecordDoesNotSilentlyFallBack() throws Exception {
        Path marker=temporary.resolve("runtime-python.txt"),worker=temporary.resolve("worker.py");
        for(String value:new String[]{"relative/python\n","/good/python\n/other/python\n","\n","/path\u0000/python","/"+"x".repeat(4097)}) {
            Files.writeString(marker,value);
            assertThrows(IllegalStateException.class,()->MaterialJobProtocol.resolvePython("",worker,"/Users/real","/Users/real"));
        }
    }
    @Test void runtimeParserKeepsVenvSymlinkPathAndAcceptsOneLineEnding() throws Exception {
        Path executable=temporary.resolve("python-real"),link=temporary.resolve("venv-python"),worker=temporary.resolve("worker.py");
        Files.writeString(executable,"");Files.createSymbolicLink(link,executable);
        Files.writeString(temporary.resolve("runtime-python.txt"),link+"\r\n");
        assertEquals(link,MaterialJobProtocol.resolvePython("",worker,null,"/Applications"));
        assertNotEquals(executable,MaterialJobProtocol.resolvePython("",worker,null,"/Applications"));
    }
}
