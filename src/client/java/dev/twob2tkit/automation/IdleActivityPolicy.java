package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.nio.file.Path;
import java.util.*;
import java.util.function.LongPredicate;

/** Exact idle authority and activity accounting; no input, file writes or Minecraft calls. */
public final class IdleActivityPolicy {
    record Owner(String service,String world,String task,String lease,long revision,long pid) {}
    private IdleActivityPolicy() {}
    static Owner owner(JsonObject marker,JsonObject lease,String world,long revision,long now,
                       Path root,LongPredicate alive){
        try{
            if(marker==null||lease==null||number(marker,"schema")!=1
                    ||!"materials".equals(string(lease,"kind"))
                    ||!marker.has("input_released")||!marker.get("input_released").isJsonPrimitive()
                    ||!marker.getAsJsonPrimitive("input_released").isBoolean()||marker.get("input_released").getAsBoolean())return null;
            String id=string(marker,"idle_service_id"),task=string(marker,"task_session"),leaseId=string(marker,"lease_id");
            long updated=number(marker,"updated_at"),pid=number(marker,"pid"),rev=number(marker,"revision");
            if(!id.matches("[0-9a-f]{20}")||task.isBlank()||leaseId.isBlank()||world==null||world.isBlank()
                    ||updated<=0||now-updated< -1000||now-updated>2500||pid<=0||!alive.test(pid)
                    ||revision<0||rev!=revision||number(lease,"revision")!=revision
                    ||!world.equals(string(marker,"world_session"))||!world.equals(string(lease,"world_session"))
                    ||!task.equals(string(lease,"job_session"))||!leaseId.equals(string(lease,"id")))return null;
            Path expected=root.resolve("idle-services").resolve(id).resolve("worker.lock").toAbsolutePath().normalize();
            if(!Path.of(string(marker,"lock_path")).toAbsolutePath().normalize().equals(expected))return null;
            return new Owner(id,world,task,leaseId,rev,pid);
        }catch(RuntimeException malformed){return null;}
    }
    static boolean requestOwned(Owner owner,JsonObject request){
        return owner!=null&&request!=null&&owner.service.equals(string(request,"idle_service_id"))
            &&owner.task.equals(string(request,"task_session"))&&owner.world.equals(string(request,"world_session"));
    }
    static List<String> conflicts(Map<String,Boolean> activities,Owner owner,Set<String> owned){
        var result=new ArrayList<String>();
        activities.forEach((key,busy)->{if(Boolean.TRUE.equals(busy)&&(owner==null||!owned.contains(key)))result.add(key);});
        return List.copyOf(result);
    }
    static boolean mayCancel(Owner owner,boolean foreignActive,boolean foreignNativeOwner,boolean foreignScan){
        return owner!=null&&!foreignActive&&!foreignNativeOwner&&!foreignScan;
    }
    static boolean inputsReleased(Map<String,Boolean> activities,Set<String> owned){
        return owned.stream().filter(k->!Set.of("material_lease","mining_isolation").contains(k))
            .noneMatch(k->Boolean.TRUE.equals(activities.get(k)));
    }
    static String string(JsonObject object,String key){
        if(object==null||!object.has(key)||!object.get(key).isJsonPrimitive()||!object.getAsJsonPrimitive(key).isString())return "";
        return object.get(key).getAsString();
    }
    private static long number(JsonObject object,String key){
        if(object==null||!object.has(key)||!object.get(key).isJsonPrimitive()||!object.getAsJsonPrimitive(key).isNumber())throw new IllegalArgumentException("Integer required");
        return object.get(key).getAsBigDecimal().longValueExact();
    }
}
