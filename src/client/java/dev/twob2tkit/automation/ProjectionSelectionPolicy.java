package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.util.Set;

final class ProjectionSelectionPolicy {
    private ProjectionSelectionPolicy(){}
    static void envelope(JsonObject r){
        var allowed=Set.of("schema","id","op","server","dimension","site","world_session","expected_revision","expires_at","manual_start",
            "placement_index","expected_registry","expected_fingerprint");
        for(String key:r.keySet())if(!allowed.contains(key))throw new IllegalArgumentException("Unsupported projection-select field: "+key);
        if(!ProjectionLoadPolicy.text(r,"id",96).matches("[A-Za-z0-9_-]{1,96}")
            ||!ProjectionLoadPolicy.text(r,"op",40).equals("projection_select")||ProjectionLoadPolicy.integer(r,"schema")!=1
            ||!r.has("manual_start")||!r.get("manual_start").isJsonPrimitive()||!r.getAsJsonPrimitive("manual_start").isBoolean()
            ||!r.get("manual_start").getAsBoolean())throw new IllegalArgumentException("Existing selection requires an explicit schema-1 request");
        long index=ProjectionLoadPolicy.integer(r,"placement_index");
        if(index<0||index>=1024)throw new IllegalArgumentException("Existing placement index is outside limits");
        for(String key: new String[]{"expected_registry","expected_fingerprint"})
            if(!ProjectionLoadPolicy.text(r,key,64).matches("[a-f0-9]{64}"))throw new IllegalArgumentException("Existing selection needs exact registry and placement fingerprints");
    }
}
