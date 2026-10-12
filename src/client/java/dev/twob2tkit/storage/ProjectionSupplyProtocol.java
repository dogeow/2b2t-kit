package dev.twob2tkit.storage;

import com.google.gson.*;
import dev.twob2tkit.material.MaterialTaskProtocol;
import java.util.Set;

/** Metadata-only command, with current-world proof and no physical action or toggle. */
public final class ProjectionSupplyProtocol {
    public static final String OP="projection_supply_set";
    private static final Set<String> FIELDS=Set.of("schema","id","op","server","dimension","world_session",
        "expected_revision","expires_at","site","pos","enabled");
    private ProjectionSupplyProtocol(){}
    public record Command(int x,int y,int z,boolean enabled){}
    public static Command parse(JsonObject request){
        MaterialTaskProtocol.identifier(request);
        for(String field:request.keySet())if(!FIELDS.contains(field))throw new IllegalArgumentException("Unsupported depot parameter: "+field);
        if(!request.has("op")||!request.get("op").isJsonPrimitive()||!request.getAsJsonPrimitive("op").isString()
                ||!OP.equals(request.get("op").getAsString()))throw new IllegalArgumentException("Expected explicit depot setter");
        if(request.has("schema")&&integer(request.get("schema"))!=1)throw new IllegalArgumentException("Unsupported depot schema");
        if(!request.has("enabled")||!request.get("enabled").isJsonPrimitive()
                ||!request.getAsJsonPrimitive("enabled").isBoolean())throw new IllegalArgumentException("Expected enabled boolean");
        if(!request.has("pos")||!request.get("pos").isJsonArray()||request.getAsJsonArray("pos").size()!=3)
            throw new IllegalArgumentException("Expected exact depot coordinates");
        var pos=request.getAsJsonArray("pos");int x=integer(pos.get(0)),y=integer(pos.get(1)),z=integer(pos.get(2));
        if(Math.abs((long)x)>30000000||Math.abs((long)z)>30000000||y< -2048||y>2048)
            throw new IllegalArgumentException("Depot coordinates outside supported world bounds");
        return new Command(x,y,z,request.get("enabled").getAsBoolean());
    }
    private static int integer(JsonElement raw){
        try{if(!raw.isJsonPrimitive()||!raw.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException();return raw.getAsBigDecimal().intValueExact();}
        catch(RuntimeException invalid){throw new IllegalArgumentException("Expected integer depot coordinate/schema");}
    }
}
