package dev.twob2tkit.material;
import com.google.gson.*;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class MaterialTaskProtocolTest {
    private JsonObject request(){return JsonParser.parseString("{\"id\":\"request-1\",\"op\":\"material_task_start\",\"mode\":\"item\",\"item\":\"minecraft:stone\",\"count\":64,\"manual_start\":true,\"server\":\"simpcraft.com:25565\",\"dimension\":\"minecraft:overworld\",\"world_session\":\"world-a\",\"expected_revision\":4,\"expires_at\":5000}").getAsJsonObject();}
    private JsonObject context(){return JsonParser.parseString("{\"server\":\"simpcraft.com\",\"dimension\":\"minecraft:overworld\",\"world_session\":\"world-a\",\"expected_revision\":4}").getAsJsonObject();}
    @Test void explicitItemStartHasExactCountAndProjectionHasExactKey(){
        var r=request();var command=MaterialTaskProtocol.parse(r);assertEquals(64,command.count());assertEquals("minecraft:stone",command.item());
        r.addProperty("mode","projection");r.remove("item");r.remove("count");r.addProperty("placement_key","actual-selected-key");
        assertEquals("actual-selected-key",MaterialTaskProtocol.parse(r).placementKey());
        r.remove("placement_key");assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));
    }
    @Test void nonIntegralNumbersAndFalseOrStringAcknowledgementAreRejected(){
        for(JsonElement count:List.of(new JsonPrimitive(0),new JsonPrimitive(1.5),new JsonPrimitive("64"),new JsonPrimitive(1000001))){var r=request();r.add("count",count);assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));}
        for(JsonElement consent:List.of(new JsonPrimitive(false),new JsonPrimitive("true"))){var r=request();r.add("manual_start",consent);assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));}
    }
    @Test void arbitraryCommandsPathsAndNativeLeaseFieldsCannotReachWorkerLaunch(){
        for(String field:List.of("worker","python","command","out","path","task_session","background_ok")){var r=request();r.addProperty(field,"/tmp/injected");assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));}
        for(String item:List.of("minecraft:air","other:stone","minecraft:stone;rm","../../stone")){var r=request();r.addProperty("item",item);assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));}
    }
    @Test void writeScopeRejectsOldWorldRevisionExpiryManualMovementAndDeadActor(){
        assertDoesNotThrow(()->MaterialTaskProtocol.requireScope(request(),context(),1000,true,false));
        for(String field:List.of("server","dimension","world_session")){var r=request();r.addProperty(field,"other");assertThrows(IllegalStateException.class,()->MaterialTaskProtocol.requireScope(r,context(),1000,true,false));}
        for(long rev:new long[]{3,5}){var r=request();r.addProperty("expected_revision",rev);assertThrows(IllegalStateException.class,()->MaterialTaskProtocol.requireScope(r,context(),1000,true,false));}
        for(long expiry:new long[]{999,16001}){var r=request();r.addProperty("expires_at",expiry);assertThrows(IllegalStateException.class,()->MaterialTaskProtocol.requireScope(r,context(),1000,true,false));}
        assertThrows(IllegalStateException.class,()->MaterialTaskProtocol.requireScope(request(),context(),1000,false,false));
        assertThrows(IllegalStateException.class,()->MaterialTaskProtocol.requireScope(request(),context(),1000,true,true));
    }
    @Test void readOnlyStatusNeedsNoLiveWorldAndCannotModifyTargets(){
        var r=JsonParser.parseString("{\"id\":\"read\",\"op\":\"material_task_status\"}").getAsJsonObject();
        assertEquals("material_task_status",MaterialTaskProtocol.parse(r).op());r.addProperty("count",64);
        assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));
    }
    @Test void controlsNeedExactJobAndOnlyResumeNeedsFreshAcknowledgement(){
        for(String action:List.of("pause","resume","cancel")){
            var r=JsonParser.parseString("{\"id\":\"control\",\"op\":\"material_task_"+action+"\"}").getAsJsonObject();
            assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));r.addProperty("job_id","job-1");
            if(action.equals("resume")){assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(r));r.addProperty("manual_start",true);}
            assertEquals("job-1",MaterialTaskProtocol.parse(r).jobId());
        }
        assertDoesNotThrow(()->MaterialTaskProtocol.requireJob("job-1","job-1","world-a","world-a"));
        assertThrows(IllegalStateException.class,()->MaterialTaskProtocol.requireJob("job-0","job-1","world-a","world-a"));
        assertThrows(IllegalStateException.class,()->MaterialTaskProtocol.requireJob("job-1","job-1","world-a","world-b"));
    }
    @Test void identityCannotEscapeReplyDirectoryOrReuseCurrentWorkerForNewStart(){
        var bad=request();bad.addProperty("id","../request");assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(bad));
        var reuse=request();reuse.addProperty("job_id","job-1");assertThrows(IllegalArgumentException.class,()->MaterialTaskProtocol.parse(reuse));
    }
}
