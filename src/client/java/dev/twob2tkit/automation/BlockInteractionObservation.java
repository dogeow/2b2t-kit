package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;
import java.util.Objects;
import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionResult;

/** Read-only local interaction evidence; never a substitute for server confirmation. */
final class BlockInteractionObservation {
    static final int PROTOCOL=1;
    record Input(String requestId,String worldSession,BlockPos target,String stateBefore,
                 String hand,int selectedSlot,String direction,String face,String method,
                 float yaw,float pitch,boolean secondaryUse,boolean sneakKey,
                 boolean forcedSneak,boolean mayBuild){
        Input{Objects.requireNonNull(requestId);Objects.requireNonNull(worldSession);target=Objects.requireNonNull(target).immutable();}
    }
    static JsonObject snapshot(Input in,InteractionResult result,String stateAfter){
        var out=new JsonObject();out.addProperty("protocol",PROTOCOL);
        out.addProperty("request_id",in.requestId());out.addProperty("world_session",in.worldSession());
        var point=new JsonArray();point.add(in.target().getX());point.add(in.target().getY());point.add(in.target().getZ());out.add("pos",point);
        out.addProperty("state_before",in.stateBefore());out.addProperty("state_after_local_call",stateAfter);
        out.addProperty("hand",in.hand());out.addProperty("selected_slot",in.selectedSlot());
        out.addProperty("player_direction",in.direction());out.addProperty("hit_face",in.face());out.addProperty("method",in.method());
        out.addProperty("yaw",in.yaw());out.addProperty("pitch",in.pitch());
        out.addProperty("secondary_use_active",in.secondaryUse());out.addProperty("sneak_key",in.sneakKey());
        out.addProperty("forced_placement_sneak",in.forcedSneak());out.addProperty("may_build",in.mayBuild());
        out.addProperty("result_returned",result!=null);
        if(result==null)out.add("consumed_action",JsonNull.INSTANCE);else out.addProperty("consumed_action",result.consumesAction());
        out.addProperty("result_kind",result==null?"null":result.getClass().getSimpleName());
        out.addProperty("observation_scope","local_client_call_only_not_server_confirmation");return out;
    }
}
