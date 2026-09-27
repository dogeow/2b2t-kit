package dev.twob2tkit.material;

import com.google.gson.*;
import dev.twob2tkit.automation.AutomationScope;
import java.util.Set;

/** Dedicated outer-worker commands. Never accepts a worker path, executable or shell command. */
public final class MaterialTaskProtocol {
    public static final int VERSION=1;
    private static final Set<String> OPERATIONS=Set.of("material_task_start","material_task_status","material_task_pause","material_task_resume","material_task_cancel");
    private static final Set<String> FIELDS=Set.of("schema","id","op","server","dimension","world_session","expected_revision","expires_at","manual_start","mode","item","count","placement_key","job_id");
    private MaterialTaskProtocol(){}
    public record Command(String op,String jobId,String mode,String item,int count,String placementKey){}
    public static String identifier(JsonObject request){
        String id=text(request,"id");
        if(!id.matches("[a-zA-Z0-9_-]{1,96}"))throw new IllegalArgumentException("Invalid material task request id");
        return id;
    }
    public static Command parse(JsonObject request){
        identifier(request);
        for(String key:request.keySet())if(!FIELDS.contains(key))throw new IllegalArgumentException("Unsupported material task parameter: "+key);
        if(request.has("schema")&&integer(request,"schema")!=VERSION)throw new IllegalArgumentException("Unsupported material task schema");
        String op=text(request,"op"),job=text(request,"job_id"),mode=text(request,"mode"),item=text(request,"item"),key=text(request,"placement_key");
        if(!OPERATIONS.contains(op))throw new IllegalArgumentException("Unsupported material task operation");
        if(!job.isBlank()&&!job.matches("[a-zA-Z0-9_-]{1,96}"))throw new IllegalArgumentException("Invalid material task job_id");
        if(!Set.of("material_task_start","material_task_status").contains(op)&&job.isBlank())throw new IllegalArgumentException("Exact job_id is required for material task control");
        if(Set.of("material_task_start","material_task_resume").contains(op)
                &&(!request.has("manual_start")||!request.get("manual_start").isJsonPrimitive()||!request.getAsJsonPrimitive("manual_start").isBoolean()||!request.get("manual_start").getAsBoolean()))
            throw new IllegalArgumentException("Explicit manual_start=true is required");
        int count=0;
        if(op.equals("material_task_start")){
            if(!job.isBlank())throw new IllegalArgumentException("A new material task cannot reuse job_id");
            if(mode.equals("item")){
                long amount=integer(request,"count");
                if(amount<1||amount>1000000||!item.matches("minecraft:[a-z0-9_./-]+")||item.equals("minecraft:air"))throw new IllegalArgumentException("Expected a Minecraft item and count 1..1000000");
                if(!key.isBlank())throw new IllegalArgumentException("Item task cannot carry placement_key");
                count=(int)amount;
            }else if(mode.equals("projection")){
                if(key.isBlank()||request.has("item")||request.has("count"))throw new IllegalArgumentException("Projection task requires only its current placement_key");
            }else throw new IllegalArgumentException("Material task mode must be item or projection");
        }else if(request.has("mode")||request.has("item")||request.has("count")||request.has("placement_key"))throw new IllegalArgumentException("Control/status cannot change task targets");
        return new Command(op,job,mode,item,count,key);
    }
    public static void requireScope(JsonObject request,JsonObject current,long now,boolean alive,boolean manualMovement){
        if(!alive||manualMovement||!AutomationScope.sameServer(text(current,"server"),text(request,"server"))
                ||!text(current,"dimension").equals(text(request,"dimension"))
                ||text(request,"world_session").isBlank()||!text(current,"world_session").equals(text(request,"world_session"))
                ||integer(request,"expected_revision")!=integer(current,"expected_revision"))
            throw new IllegalStateException("Material task world, controller or manual input changed");
        long expires=integer(request,"expires_at");
        if(expires<now||expires-now>15000)throw new IllegalStateException("Material task request expired");
    }
    public static void requireJob(String expected,String current,String jobWorld,String currentWorld){
        if(expected==null||expected.isBlank()||!expected.equals(current))throw new IllegalStateException("Material task job_id is not the current worker");
        if(!jobWorld.equals(currentWorld))throw new IllegalStateException("Material task belongs to another world; create a new task");
    }
    private static String text(JsonObject value,String field){
        if(!value.has(field))return "";
        var raw=value.get(field);if(!raw.isJsonPrimitive()||!raw.getAsJsonPrimitive().isString())throw new IllegalArgumentException("Expected text field: "+field);
        return raw.getAsString();
    }
    private static long integer(JsonObject value,String field){
        try{var raw=value.get(field);if(raw==null||!raw.isJsonPrimitive()||!raw.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException();return raw.getAsBigDecimal().longValueExact();}
        catch(RuntimeException invalid){throw new IllegalArgumentException("Expected integer field: "+field);}
    }
}
