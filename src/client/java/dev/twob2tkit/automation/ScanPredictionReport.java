package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;

/** Read-only vanilla prediction observations, including cells currently predicted as air. */
final class ScanPredictionReport {
    private final JsonArray positions=new JsonArray();
    void observe(int x,int y,int z,boolean pending){
        if(!pending)return;
        var row=new JsonArray();row.add(x);row.add(y);row.add(z);positions.add(row);
    }
    JsonObject receipt(boolean successful,int read,int total,boolean sameWorld,long startRevision,long endRevision){
        var value=new JsonObject();value.addProperty("protocol",1);
        value.addProperty("complete",successful&&read==total&&sameWorld&&startRevision==endRevision);
        value.add("pending_positions",positions.deepCopy());value.addProperty("pending_count",positions.size());
        value.addProperty("old_action_confirmation_credit",0);
        value.addProperty("scope","vanilla_pending_predictions_sampled_with_current_loaded_cells_not_old_request_acknowledgement");
        return value;
    }
}
