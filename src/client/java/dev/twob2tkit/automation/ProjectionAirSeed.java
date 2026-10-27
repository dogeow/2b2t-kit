package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.MeteorModules;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.EntityBlock;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.RotatedPillarBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import java.lang.reflect.InvocationTargetException;
import java.lang.reflect.Method;

/** One deliberate Meteor-equivalent projected placement, using current-connection server evidence. */
final class ProjectionAirSeed {
    static final String STAGE="projection_air_seed";
    enum Outcome { RUNNING,DONE,WAITING }
    private final TerrainServerConfirmation confirmation;
    private final String world,requestId,placementKey;
    private final BlockPos target;
    private final BlockState expected,projected;
    private final BlockState originalTarget;
    private final boolean flowingWaterHopper;
    private final java.util.Map<BlockPos,BlockState> waterSources=new java.util.HashMap<>();
    private final Direction face;
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
        projected=schematic.getBlockState(target);
        expected=placementState(projected,string(request,"expected_item"));
        flowingWaterHopper=flowingWaterRequested(request);
        originalTarget=c.level.getBlockState(target);
        if(flowingWaterHopper&&(!targetAllowed(originalTarget,expected,true)
                ||!originalTarget.toString().equals(string(request,"expected_current_state"))))
            throw new IllegalStateException("Flowing-water hopper requires the exact observed flowing water; sources are protected");
        boolean axisOnly=expected.getBlock() instanceof RotatedPillarBlock
            &&expected.getProperties().size()==1&&expected.hasProperty(RotatedPillarBlock.AXIS);
        boolean isolatedStem=MushroomStemPlacementPolicy.isolated(expected,target,schematic::getBlockState)
            &&MushroomStemPlacementPolicy.isolated(expected,target,c.level::getBlockState);
        boolean hopper=expected.is(net.minecraft.world.level.block.Blocks.HOPPER);
        if(expected.isAir()||!hopper&&!ConfirmedPlacementPacer.safeSimple(expected.getProperties().isEmpty()||axisOnly||isolatedStem,
                expected.isCollisionShapeFullBlock(schematic,target),expected.getBlock() instanceof FallingBlock,
                expected.getBlock() instanceof EntityBlock)||!expected.getFluidState().isEmpty()
                ||!expected.toString().equals(string(request,"expected_state")))
            throw new IllegalStateException("Air seed requires the exact projected full cube or its axis-correct unstripped wood precursor");
        face=placementFace(expected,c.player.getMotionDirection());
        item=expected.getBlock().asItem();
        if(!BuiltInRegistries.ITEM.getKey(item).toString().equals(string(request,"expected_item")))
            throw new IllegalStateException("Air seed expected item does not match the projection");
        if(!MeteorModules.isActive(MeteorModules.FLIGHT))
            throw new IllegalStateException("Current Meteor Flight must already be active");
        if(c.gui.screen()!=null||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty()
            ||c.player.isUsingItem()||c.options.keyUse.isDown()
            ||!surfacePlayerAllowed(flowingWaterHopper,c.player.isInWater(),c.player.isUnderWater(),c.player.getAirSupply(),c.player.getMaxAirSupply())
            ||c.player.isInLava()||c.player.isOnFire())
            throw new IllegalStateException("Air seed requires idle inventory, released use key and a dry or oxygen-safe surface position");
        if(flowingWaterHopper)for(var p:BlockPos.betweenClosed(target.offset(-2,-2,-2),target.offset(2,2,2))){
            if(!serverChunk(c,p))throw new IllegalStateException("Flowing-water hopper neighborhood must be server loaded");
            var state=c.level.getBlockState(p);
            if(state.getFluidState().is(net.minecraft.tags.FluidTags.LAVA))
                throw new IllegalStateException("Flowing-water hopper cannot alter water near lava");
            if(state.is(net.minecraft.world.level.block.Blocks.WATER)&&state.getFluidState().isSource())
                waterSources.put(p.immutable(),state);
        }
        selectedSlot=c.player.getInventory().getSelectedSlot();health=c.player.getHealth();
        beforeCount=afterCount=count(c);validateBeforeSend(c);
        // Same primitive used by installed player.AirPlace, without its stale cached camera endpoint.
        interact=Class.forName("meteordevelopment.meteorclient.utils.world.BlockUtils")
            .getMethod("interact",BlockHitResult.class,InteractionHand.class,boolean.class);
        confirmation.begin(world,requestId,STAGE,target,expected.toString());
    }

    static BlockState placementState(BlockState projected,String requestedItem) {
        if(BuiltInRegistries.ITEM.getKey(projected.getBlock().asItem()).toString().equals(requestedItem))return projected;
        String wanted=BuiltInRegistries.BLOCK.getKey(projected.getBlock()).toString();
        if(!(projected.getBlock() instanceof RotatedPillarBlock)||projected.getProperties().size()!=1
                ||!projected.hasProperty(RotatedPillarBlock.AXIS)||!wanted.startsWith("minecraft:stripped_")
                ||!wanted.equals("minecraft:stripped_"+requestedItem.replaceFirst("^minecraft:",""))
                ||!requestedItem.startsWith("minecraft:")
                ||!(wanted.endsWith("_log")||wanted.endsWith("_wood")||wanted.endsWith("_stem")||wanted.endsWith("_hyphae")))
            throw new IllegalStateException("Air seed item is neither the projection item nor its unstripped wood precursor");
        var rawItem=BuiltInRegistries.ITEM.getValue(net.minecraft.resources.Identifier.parse(requestedItem));
        if(!(rawItem instanceof BlockItem raw)||!(raw.getBlock() instanceof RotatedPillarBlock)
                ||raw.getBlock().defaultBlockState().getProperties().size()!=1)
            throw new IllegalStateException("Air seed unstripped item is not an axis-only wood block");
        return raw.getBlock().defaultBlockState().setValue(RotatedPillarBlock.AXIS,projected.getValue(RotatedPillarBlock.AXIS));
    }

    static Direction placementFace(BlockState expected,Direction motion) {
        if(expected.is(net.minecraft.world.level.block.Blocks.HOPPER))
            return expected.getValue(net.minecraft.world.level.block.HopperBlock.FACING).getOpposite();
        return expected.getBlock() instanceof RotatedPillarBlock&&expected.getProperties().size()==1
            ?Direction.fromAxisAndDirection(expected.getValue(RotatedPillarBlock.AXIS),Direction.AxisDirection.POSITIVE)
            :motion.getOpposite();
    }

    static boolean flowingWaterRequested(JsonObject request){
        var value=request.get("replace_flowing_water");
        if(value==null)return false;
        if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isBoolean())
            throw new IllegalArgumentException("replace_flowing_water must be boolean");
        return value.getAsBoolean();
    }
    static boolean targetAllowed(BlockState current,BlockState expected,boolean flowingWater){
        if(!flowingWater)return current.isAir();
        return expected.is(net.minecraft.world.level.block.Blocks.HOPPER)
            &&current.is(net.minecraft.world.level.block.Blocks.WATER)&&!current.getFluidState().isSource();
    }
    static boolean surfacePlayerAllowed(boolean flowingWater,boolean bodyInWater,boolean headInWater,int air,int maxAir){
        return flowingWater?!headInWater&&maxAir>0&&air>=Math.ceil(maxAir*.75):!bodyInWater&&!headInWater;
    }
    private boolean waterSourcesUnchanged(Minecraft c){
        return waterSources.entrySet().stream().allMatch(e->serverChunk(c,e.getKey())&&e.getValue().equals(c.level.getBlockState(e.getKey())));
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
        return serverChunk(c,target);
    }
    private static boolean serverChunk(Minecraft c,BlockPos pos) {
        var chunk=c.level.getChunkSource().getChunk(pos.getX()>>4,pos.getZ()>>4,ChunkStatus.FULL,false);
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
                ||schematic==null||!projected.equals(schematic.getBlockState(target)))
            throw new IllegalStateException("Air seed projection or exact target changed");
    }
    private void validateBeforeSend(Minecraft c) {
        validateProjection();
        if(MushroomStemPlacementPolicy.allFaces(expected)
                &&(!MushroomStemPlacementPolicy.isolated(expected,target,c.level::getBlockState)
                   ||!MushroomStemPlacementPolicy.isolated(projected,target,LitematicaAccess.schematicWorld()::getBlockState)))
            throw new IllegalStateException("Isolated mushroom stem adjacency changed before the single use");
        if(!serverChunk(c)||!targetAllowed(c.level.getBlockState(target),expected,flowingWaterHopper)
                ||flowingWaterHopper&&(!originalTarget.equals(c.level.getBlockState(target))||!waterSourcesUnchanged(c)))
            throw new IllegalStateException("Air seed target is not actual air in a loaded server chunk");
        var held=c.player.getMainHandItem();
        if(held.isEmpty()||!held.is(item)||!(held.getItem() instanceof BlockItem blockItem)
                ||blockItem.getBlock()!=expected.getBlock())
            throw new IllegalStateException("Air seed main hand does not contain the exact expected block item");
        if(c.player.getEyePosition().distanceTo(Vec3.atCenterOf(target))>c.player.blockInteractionRange()-.2)
            throw new IllegalStateException("Air seed target is outside normal interaction reach");
        if(expected.is(net.minecraft.world.level.block.Blocks.HOPPER)){
            var hit=new BlockHitResult(Vec3.atCenterOf(target),face,target,false);
            var context=new net.minecraft.world.item.context.BlockPlaceContext(c.player,InteractionHand.MAIN_HAND,held,hit);
            // Use vanilla placement prediction, including powered state. No corrective second click.
            if(!target.equals(context.getClickedPos())||!expected.equals(expected.getBlock().getStateForPlacement(context)))
                throw new IllegalStateException("Directed hopper air seed does not predict the exact projected state");
        }
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
        if(!MeteorModules.isActive(MeteorModules.FLIGHT))
            throw new IllegalStateException("Flight changed before seed send");
        var hit=new BlockHitResult(Vec3.atCenterOf(target),face,target,false);
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
        if(!sent||!serverChunk(c)||c.player.getHealth()<health||c.gui.screen()!=null||!waterSourcesUnchanged(c)
            ||!surfacePlayerAllowed(flowingWaterHopper,c.player.isInWater(),c.player.isUnderWater(),c.player.getAirSupply(),c.player.getMaxAirSupply())
            ||c.player.getInventory().getSelectedSlot()!=selectedSlot
            ||!c.player.getMainHandItem().isEmpty()&&!c.player.getMainHandItem().is(item)
            ||!MeteorModules.isActive(MeteorModules.FLIGHT))return Outcome.WAITING;
        boolean acknowledged=confirmation.confirmed(world,requestId,STAGE,target);
        if(ProjectionAirSeedPolicy.confirmed(acknowledged,expected.equals(c.level.getBlockState(target)),
            beforeCount,afterCount,ackTick,tick))return Outcome.DONE;
        return timedOut?Outcome.WAITING:Outcome.RUNNING;
    }
    void close(){confirmation.close(requestId);}

    JsonObject snapshot(boolean complete) {
        var out=new JsonObject();out.addProperty("request_id",requestId);out.addProperty("world_session",world);
        out.addProperty("placement_key",placementKey);out.addProperty("expected_state",expected.toString());
        out.addProperty("projected_state",projected.toString());out.addProperty("projection_matches",complete&&expected.equals(projected));
        out.addProperty("requires_stripping",!expected.equals(projected));out.addProperty("face",face.name().toLowerCase(java.util.Locale.ROOT));
        var coordinates=new com.google.gson.JsonArray();coordinates.add(target.getX());coordinates.add(target.getY());coordinates.add(target.getZ());out.add("target",coordinates);
        out.addProperty("use_count",sent?1:0);out.addProperty("item",BuiltInRegistries.ITEM.getKey(item).toString());
        out.addProperty("inventory_before",beforeCount);out.addProperty("inventory_after",afterCount);
        out.addProperty("inventory_delta_observed",beforeCount-afterCount==1);
        out.addProperty("server_confirmed",complete&&confirmation.confirmed(world,requestId,STAGE,target));
        out.addProperty("confirmation_scope",confirmation.scope());
        out.addProperty("module_settings_changed",false);out.addProperty("automatic_retry_allowed",false);
        out.addProperty("replaced_flowing_water",flowingWaterHopper);out.addProperty("original_target_state",originalTarget.toString());
        out.addProperty("protected_water_sources",waterSources.size());
        out.addProperty("water_sources_preserved",complete);
        var sources=new com.google.gson.JsonArray();
        waterSources.forEach((pos,state)->{
            var entry=new JsonObject();var sourcePosition=new com.google.gson.JsonArray();
            sourcePosition.add(pos.getX());sourcePosition.add(pos.getY());sourcePosition.add(pos.getZ());
            entry.add("pos",sourcePosition);entry.addProperty("state",state.toString());sources.add(entry);
        });
        out.add("water_source_baseline",sources);
        out.addProperty("entity_coverage","current_client_loaded_entities_only");return out;
    }
}
