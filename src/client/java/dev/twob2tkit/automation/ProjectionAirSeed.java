package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.MeteorModules;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/** One deliberate Meteor-equivalent air seed, using current-connection server evidence. */
final class ProjectionAirSeed {
    static final String STAGE="projection_air_seed";
    enum Outcome { RUNNING,DONE,WAITING }
    private final TerrainServerConfirmation confirmation;
    private final String world,requestId,placementKey;
    private final BlockPos target;
    private final BlockState expected;
    private final Item item;
    private final int selectedSlot,beforeCount;
    private final float health;
    private final Method interact;
    private int afterCount;
    private boolean sent;
    private long ackTick=-1;

    ProjectionAirSeed(Minecraft c,JsonObject request,String world,String requestId,
                      TerrainServerConfirmation confirmation) throws ReflectiveOperationException {
        this.world=world;this.requestId=requestId;this.confirmation=confirmation;
        target=position(request);placementKey=string(request,"placement_key");
        var selection=LitematicaAccess.lockedBuildSelection();
        if(!selection.key().equals(placementKey)||!selection.contains(target)||!LitematicaAccess.inVisibleLayer(target))
            throw new IllegalStateException("Air seed must belong to the current selected locked visible projection");
        String loading=LitematicaAccess.loadingReason(selection);
        if(!loading.isEmpty())throw new IllegalStateException(loading);
        var schematic=LitematicaAccess.schematicWorld();
        if(schematic==null)throw new IllegalStateException("Air seed projection world is unavailable");
        expected=schematic.getBlockState(target);
        if(expected.isAir()||!ConfirmedPlacementPacer.safeSimple(expected.getProperties().isEmpty(),
                expected.isCollisionShapeFullBlock(schematic,target),expected.getBlock() instanceof FallingBlock,
                expected.getBlock() instanceof EntityBlock)||!expected.getFluidState().isEmpty()
                ||!expected.toString().equals(string(request,"expected_state")))
            throw new IllegalStateException("Air seed requires the exact projected plain full cube without gravity, fluid or block entity");
        item=expected.getBlock().asItem();
        if(!BuiltInRegistries.ITEM.getKey(item).toString().equals(string(request,"expected_item")))
            throw new IllegalStateException("Air seed expected item does not match the projection");
        if(!MeteorModules.isActive(MeteorModules.AIR_PLACE)||!MeteorModules.isActive(MeteorModules.FLIGHT))
            throw new IllegalStateException("Current Meteor player.AirPlace and Flight must already be active");
        if(c.screen!=null||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty()
            ||c.player.isUsingItem()||c.options.keyUse.isDown()||c.player.isInWater()||c.player.isInLava()||c.player.isOnFire())
            throw new IllegalStateException("Air seed requires an idle dry inventory and released use key");
        selectedSlot=c.player.getInventory().getSelectedSlot();health=c.player.getHealth();
        beforeCount=afterCount=count(c);validateBeforeSend(c);
        // Same primitive used by installed player.AirPlace, without its stale cached camera endpoint.
        interact=Class.forName("meteordevelopment.meteorclient.utils.world.BlockUtils")
            .getMethod("interact",BlockHitResult.class,InteractionHand.class,boolean.class);
        confirmation.begin(world,requestId,STAGE,target,expected.toString());
    }

    private static String string(JsonObject request,String key) {
        return request.has(key)?request.get(key).getAsString():"";
    }
    private static BlockPos position(JsonObject request) {
        var coordinates=request.getAsJsonArray("target");
        if(coordinates==null||coordinates.size()!=3)throw new IllegalArgumentException("Air seed target requires [x,y,z]");
        int[] values=new int[3];
        for(int i=0;i<3;i++) {
            var raw=coordinates.get(i);
            if(!raw.isJsonPrimitive()||!raw.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Air seed coordinates must be integers");
            double value=raw.getAsDouble();
            if(!Double.isFinite(value)||value!=Math.rint(value)||Math.abs(value)>30_000_000)
                throw new IllegalArgumentException("Air seed coordinates must be finite world integers");
            values[i]=(int)value;
        }
        return new BlockPos(values[0],values[1],values[2]);
    }
    private boolean serverChunk(Minecraft c) {
        var chunk=c.level.getChunkSource().getChunk(target.getX()>>4,target.getZ()>>4,ChunkStatus.FULL,false);
        return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    private int count(Minecraft c) {
        int total=0;for(int i=0;i<c.player.getInventory().getContainerSize();i++) {
            var stack=c.player.getInventory().getItem(i);if(stack.is(item))total+=stack.getCount();
        }return total;
    }
    private void validateProjection() {
        var current=LitematicaAccess.lockedBuildSelection();
        var schematic=LitematicaAccess.schematicWorld();
        if(!current.key().equals(placementKey)||!current.contains(target)||!LitematicaAccess.inVisibleLayer(target)
                ||schematic==null||!expected.equals(schematic.getBlockState(target)))
            throw new IllegalStateException("Air seed projection or exact target changed");
    }
    private void validateBeforeSend(Minecraft c) {
        validateProjection();
        if(!serverChunk(c)||!c.level.getBlockState(target).isAir())
            throw new IllegalStateException("Air seed target is not actual air in a loaded server chunk");
        var held=c.player.getMainHandItem();
        if(held.isEmpty()||!held.is(item)||!(held.getItem() instanceof BlockItem blockItem)
                ||blockItem.getBlock()!=expected.getBlock())
            throw new IllegalStateException("Air seed main hand does not contain the exact expected block item");
        if(c.player.getEyePosition().distanceTo(Vec3.atCenterOf(target))>c.player.blockInteractionRange()-.2)
            throw new IllegalStateException("Air seed target is outside normal interaction reach");
        if(!c.level.getEntities((Entity)null,new AABB(target),Entity::isAlive).isEmpty())
            throw new IllegalStateException("Air seed cube contains an entity");
        var obstruction=c.level.clip(new ClipContext(c.player.getEyePosition(),Vec3.atCenterOf(target),
            ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,c.player));
        if(obstruction.getType()!=HitResult.Type.MISS)
            throw new IllegalStateException("Air seed target is occluded");
    }

    void sendOnce(Minecraft c) throws ReflectiveOperationException {
        if(sent)throw new IllegalStateException("Air seed use was already attempted; no resend allowed");
        validateBeforeSend(c);
        if(!MeteorModules.isActive(MeteorModules.AIR_PLACE)||!MeteorModules.isActive(MeteorModules.FLIGHT))
            throw new IllegalStateException("AirPlace or Flight changed before seed send");
        var hit=new BlockHitResult(Vec3.atCenterOf(target),c.player.getMotionDirection().getOpposite(),target,false);
        confirmation.sent(world,requestId,STAGE,target);sent=true;
        try{interact.invoke(null,hit,InteractionHand.MAIN_HAND,true);}
        catch(InvocationTargetException uncertain){throw new IllegalStateException("One Meteor seed interaction was attempted; outcome unknown and no resend allowed",uncertain.getCause());}
    }

    void serverBlock(String currentWorld,BlockPos position,BlockState packetState,
                     boolean clientApplied,long tick) {
        if(confirmation.serverBlock(currentWorld,requestId,STAGE,position,packetState.toString(),clientApplied)) {
            if(ackTick<0)ackTick=tick;
        } else if(position.equals(target)&&confirmation.serverUpdateSeen(currentWorld,requestId,STAGE,target)
                &&!confirmation.confirmed(currentWorld,requestId,STAGE,target))ackTick=-1;
    }

    Outcome poll(Minecraft c,long tick,boolean timedOut) {
        validateProjection();afterCount=count(c);
        if(!sent||!serverChunk(c)||c.player.getHealth()<health||c.screen!=null
            ||c.player.getInventory().getSelectedSlot()!=selectedSlot
            ||!c.player.getMainHandItem().isEmpty()&&!c.player.getMainHandItem().is(item)
            ||!MeteorModules.isActive(MeteorModules.AIR_PLACE)||!MeteorModules.isActive(MeteorModules.FLIGHT))return Outcome.WAITING;
        boolean acknowledged=confirmation.confirmed(world,requestId,STAGE,target);
        if(ProjectionAirSeedPolicy.confirmed(acknowledged,expected.equals(c.level.getBlockState(target)),
            beforeCount,afterCount,ackTick,tick))return Outcome.DONE;
        return timedOut?Outcome.WAITING:Outcome.RUNNING;
    }
    void close(){confirmation.close(requestId);}

    JsonObject snapshot(boolean complete) {
        var out=new JsonObject();out.addProperty("request_id",requestId);out.addProperty("world_session",world);
        out.addProperty("placement_key",placementKey);out.addProperty("expected_state",expected.toString());
        var coordinates=new com.google.gson.JsonArray();coordinates.add(target.getX());coordinates.add(target.getY());coordinates.add(target.getZ());out.add("target",coordinates);
        out.addProperty("use_count",sent?1:0);out.addProperty("item",BuiltInRegistries.ITEM.getKey(item).toString());
        out.addProperty("inventory_before",beforeCount);out.addProperty("inventory_after",afterCount);
        out.addProperty("inventory_delta_observed",beforeCount-afterCount==1);
        out.addProperty("server_confirmed",complete&&confirmation.confirmed(world,requestId,STAGE,target));
        out.addProperty("confirmation_scope",confirmation.scope());
        out.addProperty("module_settings_changed",false);out.addProperty("automatic_retry_allowed",false);
        out.addProperty("entity_coverage","current_client_loaded_entities_only");return out;
    }
}
