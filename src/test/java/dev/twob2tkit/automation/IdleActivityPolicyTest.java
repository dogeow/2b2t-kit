package dev.twob2tkit.automation;

import com.google.gson.*;
import java.nio.file.Path;
import java.util.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class IdleActivityPolicyTest {
    final Path root=Path.of("/tmp/idle-host-policy");
    final String service="0123456789abcdefabcd";
    JsonObject marker(){
        var j=new JsonObject();j.addProperty("schema",1);j.addProperty("idle_service_id",service);
        j.addProperty("world_session","world");j.addProperty("task_session","idle-task");j.addProperty("lease_id","idle-lease");
        j.addProperty("revision",7);j.addProperty("pid",77);j.addProperty("updated_at",10000);j.addProperty("input_released",false);
        j.addProperty("lock_path",root.resolve("idle-services").resolve(service).resolve("worker.lock").toString());return j;
    }
    JsonObject lease(){return JsonParser.parseString("{\"kind\":\"materials\",\"id\":\"idle-lease\",\"job_session\":\"idle-task\",\"world_session\":\"world\",\"revision\":7}").getAsJsonObject();}
    IdleActivityPolicy.Owner read(JsonObject marker,JsonObject lease){return IdleActivityPolicy.owner(marker,lease,"world",7,10000,root,p->p==77);}
    @Test void exactFreshLiveOwnerHasAuthorityAndOnlyItsTaggedRequestMatches(){
        var owner=read(marker(),lease());assertNotNull(owner);
        var r=JsonParser.parseString("{\"idle_service_id\":\""+service+"\",\"task_session\":\"idle-task\",\"world_session\":\"world\"}").getAsJsonObject();
        assertTrue(IdleActivityPolicy.requestOwned(owner,r));
        for(String key:List.of("idle_service_id","task_session","world_session")){
            var changed=r.deepCopy();changed.addProperty(key,"foreign");assertFalse(IdleActivityPolicy.requestOwned(owner,changed));
        }
        assertFalse(IdleActivityPolicy.requestOwned(null,r));
    }
    @Test void staleDeadWrongWorldLeaseTaskRevisionAndLockCannotHideActivity(){
        for(String key:List.of("schema","idle_service_id","world_session","task_session","lease_id","revision","pid","updated_at","lock_path","input_released")){
            var j=marker();
            switch(key){
                case "schema" -> j.addProperty(key,2);
                case "revision" -> j.addProperty(key,8);
                case "pid" -> j.addProperty(key,78);
                case "updated_at" -> j.addProperty(key,7499);
                case "input_released" -> j.addProperty(key,true);
                default -> j.addProperty(key,"foreign");
            }
            assertNull(read(j,lease()),key);
            assertEquals(List.of("fisher"),IdleActivityPolicy.conflicts(Map.of("fisher",true),read(j,lease()),Set.of("fisher")));
        }
        var future=marker();future.addProperty("updated_at",11001);assertNull(read(future,lease()));
        var decimal=marker();decimal.addProperty("revision",7.5);assertNull(read(decimal,lease()));
        var missing=marker();missing.remove("pid");assertNull(read(missing,lease()));
        assertNull(IdleActivityPolicy.owner(marker(),lease(),"world",7,10000,root,p->false));
    }
    @Test void parkingForeignAndChangedNativeLeaseAreNotIdleAuthority(){
        for(String key:List.of("kind","id","job_session","world_session","revision")){
            var changed=lease();if(key.equals("revision"))changed.addProperty(key,8);else changed.addProperty(key,"foreign");
            assertNull(read(marker(),changed),key);
        }
        var parking=lease();parking.addProperty("kind","parking");assertNull(read(marker(),parking));
    }
    @Test void owningIdleFisherNeverHidesOtherActualControllers(){
        var flags=new LinkedHashMap<String,Boolean>();
        for(String key:List.of("fisher","nether_roof","material_task","native_material_owner","professional_printer","scaffold_row","concrete","guard"))flags.put(key,true);
        var conflicts=IdleActivityPolicy.conflicts(flags,read(marker(),lease()),Set.of("fisher"));
        assertFalse(conflicts.contains("fisher"));assertEquals(7,conflicts.size());
        assertTrue(conflicts.containsAll(List.of("nether_roof","material_task","native_material_owner","professional_printer","scaffold_row","concrete","guard")));
    }
    @Test void foreignActiveNativeOwnerOrScanCannotBeCancelledByIdleScope(){
        var owner=read(marker(),lease());assertTrue(IdleActivityPolicy.mayCancel(owner,false,false,false));
        assertFalse(IdleActivityPolicy.mayCancel(owner,true,false,false));
        assertFalse(IdleActivityPolicy.mayCancel(owner,false,true,false));
        assertFalse(IdleActivityPolicy.mayCancel(owner,false,false,true));
        assertFalse(IdleActivityPolicy.mayCancel(null,false,false,false));
    }
    @Test void releaseRequiresRealOwnedControllersToStopButPreservesForeignWork(){
        var own=Set.of("fisher","navigation","native_request","material_lease","mining_isolation");
        assertTrue(IdleActivityPolicy.inputsReleased(Map.of("fisher",false,"navigation",false,"native_request",false,"nether_roof",true,"material_lease",true),own));
        for(String key:List.of("fisher","navigation","native_request"))assertFalse(IdleActivityPolicy.inputsReleased(Map.of(key,true),own));
    }
}
