package dev.twob2tkit.combat;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class MaterialHealthHoldPolicyTest {
    @TempDir Path dir;
    private JsonObject ack(long time){
        var record=new JsonObject();record.addProperty("active",false);record.addProperty("cleared_by","game_ui");record.addProperty("cleared_at",time);return record;
    }
    private boolean held(String text,JsonObject nativeRecord){return MaterialHealthHoldPolicy.active(JsonParser.parseString(text),nativeRecord);}
    @Test void absentScriptDoesNotCreateAHold(){assertFalse(MaterialHealthHoldPolicy.active(dir.resolve("absent.json"),new JsonObject()));}
    @Test void inactiveValidScriptDoesNotNeedAcknowledgement(){assertFalse(held("{\"active\":false,\"time\":100}",new JsonObject()));}
    @Test void scriptHealthExitNeedsExplicitNewerGameUiAcknowledgement(){
        var text="{\"active\":true,\"time\":100}";
        assertTrue(held(text,null));assertTrue(held(text,new JsonObject()));
        assertTrue(held(text,ack(99)));assertTrue(held(text,ack(100)));assertFalse(held(text,ack(101)));
        var automatic=ack(101);automatic.addProperty("cleared_by","automation");assertTrue(held(text,automatic));
        var stillNativeHeld=ack(101);stillNativeHeld.addProperty("active",true);assertTrue(held(text,stillNativeHeld));
    }
    @Test void staleAckCannotReleaseANewTaskAndFileIsReadFresh()throws Exception{
        var p=dir.resolve("material-health-hold.json");Files.writeString(p,"{\"active\":true,\"time\":100}");
        assertFalse(MaterialHealthHoldPolicy.active(p,ack(101)));
        Files.writeString(p,"{\"active\":true,\"time\":102}");assertTrue(MaterialHealthHoldPolicy.active(p,ack(101)));
    }
    @Test void corruptOrIncompleteExistingScriptFailsClosedEvenAfterAck()throws Exception{
        var p=dir.resolve("material-health-hold.json");
        for(var text:List.of("{bad","null","[]","{}","{\"active\":\"false\",\"time\":100}","{\"active\":true}","{\"active\":false,\"time\":true}","{\"active\":true,\"time\":-1}","{\"active\":true,\"time\":100.0}","{\"active\":true,\"time\":\"100\"}","{\"active\":true,\"time\":999999999999999999999}")){
            Files.writeString(p,text);assertTrue(MaterialHealthHoldPolicy.active(p,ack(101)),text);
        }
        Files.delete(p);Files.createDirectory(p);assertTrue(MaterialHealthHoldPolicy.active(p,ack(101)));
    }
    @Test void malformedNativeAcknowledgementCannotReleaseScript(){
        var text="{\"active\":true,\"time\":100}";
        for(var nativeText:List.of("{}","{\"active\":false,\"cleared_by\":\"game_ui\"}","{\"active\":false,\"cleared_by\":\"game_ui\",\"cleared_at\":true}","{\"active\":false,\"cleared_by\":\"game_ui\",\"cleared_at\":\"101\"}","{\"active\":\"false\",\"cleared_by\":\"game_ui\",\"cleared_at\":101}"))
            assertTrue(held(text,JsonParser.parseString(nativeText).getAsJsonObject()),nativeText);
    }
    private List<String> calls(String type,String name)throws Exception{
        var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+type+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}
        var result=new ArrayList<String>();for(var i:n.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow().instructions)
            if(i instanceof MethodInsnNode call)result.add(call.owner+"."+call.name);return result;
    }
    @Test void nativeHeldRetainsOriginalStoreBeforeScriptPolicyAndJoinedUsesHeld()throws Exception{
        var held=calls("combat/EmergencyExit","held");
        assertTrue(calls("combat/EmergencyExit","nativeHeld").contains("dev/twob2tkit/combat/SafetyHoldStore.active"));
        assertTrue(held.indexOf("dev/twob2tkit/combat/EmergencyExit.nativeHeld")<held.indexOf("dev/twob2tkit/combat/MaterialHealthHoldPolicy.active"));
        var joined=calls("combat/EmergencyExit","joined");assertTrue(joined.contains("dev/twob2tkit/combat/EmergencyExit.held"));assertTrue(joined.contains("dev/twob2tkit/MeteorModules.disable"));
        var bridge=calls("automation/AutomationBridge","joined");assertTrue(bridge.indexOf("dev/twob2tkit/combat/EmergencyExit.held")<bridge.indexOf("dev/twob2tkit/MeteorModules.enable"));
    }
    @Test void scriptHoldNeverSuppressesNativeLowHealthEscapeAndAckRechecksFinalHold()throws Exception{
        var observe=calls("combat/EmergencyExit","observeHealth");
        assertTrue(observe.contains("dev/twob2tkit/combat/EmergencyExit.nativeHeld"));
        assertFalse(observe.contains("dev/twob2tkit/combat/EmergencyExit.held"));
        var tick=calls("combat/EmergencyExit","tick");
        assertTrue(tick.indexOf("dev/twob2tkit/combat/EmergencyExit.observeHealth")<tick.indexOf("dev/twob2tkit/KitClient.emergencyStop"));
        var ack=calls("combat/EmergencyExit","acknowledge");
        assertTrue(ack.indexOf("dev/twob2tkit/combat/SafetyHoldStore.clearByUser")<ack.indexOf("dev/twob2tkit/combat/EmergencyExit.held"));
    }
    @Test void policyContainsNoWriteOrUnlockApi(){
        assertEquals(Set.of("active","booleanValue","timestamp"),Arrays.stream(MaterialHealthHoldPolicy.class.getDeclaredMethods()).map(java.lang.reflect.Method::getName).collect(java.util.stream.Collectors.toSet()));
    }
}
