package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.block.LiquidBlockContainer;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import java.util.ArrayList;
import java.util.List;
import java.util.function.BooleanSupplier;

/** Water-only, one-cell normal bucket use. Neither predictions nor delayed old-connection packets are proof. */
final class BucketWaterAction {
    enum Outcome { RUNNING,DONE,WAITING }
    private final BucketWaterPolicy.Mode mode;
    private final BucketWaterPolicy.Receipt receipt=new BucketWaterPolicy.Receipt();
    private final dev.twob2tkit.runtime.engine.BorerMiningConfirmation predictions=new dev.twob2tkit.runtime.engine.BorerMiningConfirmation();
    private final java.nio.file.Path claimPath;
    private final BlockPos target,support;
    private final Direction face;
    private final String expectedState,expectedSupport,world,requestId;
    private final Object level,connection;
    private final BooleanSupplier ownerCurrent;
    private final List<ItemStack> before=new ArrayList<>();
    private final int selected,emptyBefore,waterBefore;
    private final float health;
    private int emptyAfter,waterAfter;
    private boolean retired;
    private String sourceEffect="unobserved";

    BucketWaterAction(Minecraft c,JsonObject request,String world,String requestId,java.nio.file.Path root,BooleanSupplier ownerCurrent) throws java.io.IOException {
        mode=switch(text(request,"op")){case "bucket_fill"->BucketWaterPolicy.Mode.FILL;case "bucket_place"->BucketWaterPolicy.Mode.PLACE;default->throw new IllegalArgumentException("Only water bucket fill/place are supported");};
        target=position(request,"pos");expectedState=text(request,"expected_state");
        if(expectedState.isBlank())throw new IllegalArgumentException("An exact fresh target state is required");
        support=mode==BucketWaterPolicy.Mode.PLACE?position(request,"support"):target;
        face=mode==BucketWaterPolicy.Mode.PLACE?Direction.valueOf(text(request,"face").toUpperCase(java.util.Locale.ROOT)):null;
        expectedSupport=mode==BucketWaterPolicy.Mode.PLACE?text(request,"expected_support_state"):"";
        if(mode==BucketWaterPolicy.Mode.PLACE&&(!support.relative(face).equals(target)||expectedSupport.isBlank()))
            throw new IllegalArgumentException("Bucket placement needs the exact adjacent support and face");
        this.world=world;this.requestId=requestId;this.ownerCurrent=ownerCurrent;
        level=c.level;connection=c.getConnection();selected=c.player.getInventory().getSelectedSlot();health=c.player.getHealth();
        if(!BucketWaterPolicy.allowedHand(mode,text(request,"expected_hand"),c.player.getMainHandItem().getCount()))
            throw new IllegalArgumentException("Expected singleton empty/water bucket must match this operation");
        claimPath=BucketUseStore.path(root,c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip,c.level.dimension().identifier().toString(),target.getX(),target.getY(),target.getZ());
        BucketUseStore.requireAvailable(claimPath);
        for(int i=0;i<c.player.getInventory().getContainerSize();i++)before.add(c.player.getInventory().getItem(i).copy());
        emptyBefore=emptyAfter=count(c,Items.BUCKET);waterBefore=waterAfter=count(c,Items.WATER_BUCKET);
        validateBeforeSend(c,false);
    }
    private static String text(JsonObject request,String key){return request.has(key)?request.get(key).getAsString():"";}
    private static BlockPos position(JsonObject request,String key) {
        JsonArray a=request.getAsJsonArray(key);if(a==null||a.size()!=3)throw new IllegalArgumentException(key+" needs [x,y,z]");
        int[] p=new int[3];for(int i=0;i<3;i++){
            var raw=a.get(i);if(!raw.isJsonPrimitive()||!raw.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Bucket coordinates must be integers");
            double n=raw.getAsDouble();if(!Double.isFinite(n)||n!=Math.rint(n)||Math.abs(n)>30_000_000)throw new IllegalArgumentException("Bucket coordinates must be bounded world integers");p[i]=(int)n;
        }return new BlockPos(p[0],p[1],p[2]);
    }
    private boolean sameContext(Minecraft c){return c.level==level&&c.getConnection()==connection&&c.player!=null;}
    private boolean serverChunk(Minecraft c,BlockPos pos) {
        var chunk=c.level.getChunkSource().getChunk(pos.getX()>>4,pos.getZ()>>4,ChunkStatus.FULL,false);
        return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    private static int count(Minecraft c,net.minecraft.world.item.Item item) {
        int n=0;for(int i=0;i<c.player.getInventory().getContainerSize();i++)if(c.player.getInventory().getItem(i).is(item))n+=c.player.getInventory().getItem(i).getCount();return n;
    }
    private boolean inventoryUnchanged(Minecraft c,boolean transformed) {
        if(before.size()!=c.player.getInventory().getContainerSize())return false;
        for(int i=0;i<before.size();i++){
            var expected=transformed&&i==selected?new ItemStack(mode==BucketWaterPolicy.Mode.FILL?Items.WATER_BUCKET:Items.BUCKET):before.get(i);
            if(!ItemStack.matches(expected,c.player.getInventory().getItem(i)))return false;
        }return true;
    }
    private boolean idle(Minecraft c) {
        return sameContext(c)&&c.screen==null&&c.player.containerMenu==c.player.inventoryMenu
            &&c.player.containerMenu.getCarried().isEmpty()&&!c.player.isUsingItem()&&!c.options.keyUse.isDown()
            &&c.player.getInventory().getSelectedSlot()==selected&&!c.player.hasInfiniteMaterials()
            &&!c.player.isInWater()&&!c.player.isInLava()&&!c.player.isOnFire()&&c.player.getHealth()>=health;
    }
    private boolean plainSource(BlockState state) {
        return BucketWaterPolicy.source(state.is(Blocks.WATER),state.getFluidState().is(Fluids.WATER)&&state.getFluidState().isSource(),
            state.hasProperty(LiquidBlock.LEVEL)?state.getValue(LiquidBlock.LEVEL):-1,false);
    }
    private boolean dryFullBlock(Minecraft c,BlockPos pos) {
        return serverChunk(c,pos)&&c.level.getBlockEntity(pos)==null&&c.level.getFluidState(pos).isEmpty()
            &&!(c.level.getBlockState(pos).getBlock() instanceof LiquidBlockContainer)
            &&c.level.getBlockState(pos).isCollisionShapeFullBlock(c.level,pos);
    }
    private boolean boundedHole(Minecraft c,boolean airRequired) {
        int sides=0;for(Direction d:Direction.Plane.HORIZONTAL)if(dryFullBlock(c,target.relative(d)))sides++;
        var state=c.level.getBlockState(target);
        return (!airRequired||state.isAir())&&BucketWaterPolicy.boundedHole(true,airRequired?state.getFluidState().isEmpty():true,
            c.level.getBlockEntity(target)!=null,dryFullBlock(c,target.below()),sides,
            c.level.environmentAttributes().getValue(net.minecraft.world.attribute.EnvironmentAttributes.WATER_EVAPORATES,target));
    }
    private void validateBeforeSend(Minecraft c,boolean checkOwner) {
        if(!idle(c)||checkOwner&&!ownerCurrent.getAsBoolean()||!serverChunk(c,target)
                ||!c.level.getWorldBorder().isWithinBounds(target)||c.level.isOutsideBuildHeight(target)
                ||!c.level.getBlockState(target).toString().equals(expectedState)||predictions.pending(c.level,target)||!inventoryUnchanged(c,false))
            throw new IllegalStateException("Bucket inventory, ownership, server chunk, or exact target changed");
        var held=c.player.getMainHandItem();String id=BuiltInRegistries.ITEM.getKey(held.getItem()).toString();
        if(!BucketWaterPolicy.allowedHand(mode,id,held.getCount())||c.player.getCooldowns().isOnCooldown(held))
            throw new IllegalStateException("A selected singleton water-only bucket without cooldown is required");
        if(mode==BucketWaterPolicy.Mode.FILL){
            if(!plainSource(c.level.getBlockState(target))||c.level.getBlockEntity(target)!=null)
                throw new IllegalStateException("Bucket fill requires a plain level-0 water source, never flowing water, waterlogged blocks or lava");
        }else if(!boundedHole(c,true)||!serverChunk(c,support)||!c.level.getBlockState(support).toString().equals(expectedSupport)
                ||c.level.getBlockState(support).getBlock() instanceof LiquidBlockContainer)
            throw new IllegalStateException("Bucket place needs actual air in a dry full-block basin with bottom and four sides, and the exact non-waterloggable support");
        if(!c.level.getEntities((Entity)null,new AABB(target),Entity::isAlive).isEmpty())
            throw new IllegalStateException("Bucket target contains a currently loaded entity");
    }
    Vec3 aim(Minecraft c) {
        if(mode==BucketWaterPolicy.Mode.FILL){
            Vec3 point=Vec3.atCenterOf(target);var hit=c.level.clip(new ClipContext(c.player.getEyePosition(),point,ClipContext.Block.OUTLINE,ClipContext.Fluid.SOURCE_ONLY,c.player));
            if(!BlockFaceTarget.matches(hit,target,null)||c.player.getEyePosition().distanceTo(point)>c.player.blockInteractionRange()-.2)
                throw new IllegalStateException("Source water is occluded or outside normal reach");
            entityRayClear(c,point);return point;
        }
        var hit=BlockFaceTarget.visible(c,c.player.getEyePosition(),support,face,c.player.blockInteractionRange()-.2);
        if(hit==null)throw new IllegalStateException("Bucket support face is occluded or outside normal reach");
        Vec3 point=BlockFaceTarget.inside(hit);entityRayClear(c,point);return point;
    }
    private void entityRayClear(Minecraft c,Vec3 point) {
        Vec3 eye=c.player.getEyePosition();AABB ray=new AABB(eye,point).inflate(.3);
        for(var entity:c.level.getEntities(c.player,ray,Entity::isAlive)){
            AABB box=entity.getBoundingBox().inflate(entity.getPickRadius());
            if(box.contains(eye)||box.clip(eye,point).isPresent())throw new IllegalStateException("Bucket ray contains a currently loaded entity");
        }
    }
    void useOnce(Minecraft c) throws java.io.IOException {
        if(receipt.sent())throw new IllegalStateException("Bucket interaction was already attempted; no second use allowed");
        validateBeforeSend(c,true);
        Vec3 eye=c.player.getEyePosition();Vec3 end=eye.add(c.player.calculateViewVector(c.player.getXRot(),c.player.getYRot()).scale(c.player.blockInteractionRange()));
        BlockHitResult hit=c.level.clip(new ClipContext(eye,end,ClipContext.Block.OUTLINE,
            mode==BucketWaterPolicy.Mode.FILL?ClipContext.Fluid.SOURCE_ONLY:ClipContext.Fluid.NONE,c.player));
        if(!BlockFaceTarget.matches(hit,support,face)||mode==BucketWaterPolicy.Mode.PLACE&&!hit.getBlockPos().relative(hit.getDirection()).equals(target))
            throw new IllegalStateException("Fresh vanilla bucket ray no longer matches the selected target");
        entityRayClear(c,hit.getLocation());
        if(!c.level.mayInteract(c.player,hit.getBlockPos())||!c.player.mayUseItemAt(hit.getBlockPos().relative(hit.getDirection()),hit.getDirection(),c.player.getMainHandItem()))
            throw new IllegalStateException("Normal bucket interaction permissions reject this target");
        JsonObject claim=snapshot(false);claim.addProperty("stage","claimed_before_single_use");
        claim.addProperty("use_may_have_been_sent",true);claim.addProperty("claimed_at",System.currentTimeMillis());
        BucketUseStore.claim(claimPath,claim);receipt.sendOnce();
        // Vanilla BucketItem.use performs its own identical POV ray; useItemOn would not fill a bucket.
        if(!c.gameMode.useItem(c.player,InteractionHand.MAIN_HAND).consumesAction())
            throw new IllegalStateException("One bucket use was sent but not accepted; outcome unknown, do not retry");
    }
    void serverBlock(Minecraft c,BlockPos pos,BlockState state,boolean applied,long tick) {
        boolean expected=mode==BucketWaterPolicy.Mode.PLACE?plainSource(state):BucketWaterPolicy.fillResult(state.isAir(),state.is(Blocks.WATER));
        if(mode==BucketWaterPolicy.Mode.FILL&&receipt.sent()&&sameContext(c)&&pos.equals(target))
            sourceEffect=state.isAir()?"removed":plainSource(state)?"preserved_or_regenerated":state.is(Blocks.WATER)?"changed_to_flowing":"unexpected_server_state";
        // Vanilla may defer applying this packet until its prediction acknowledgement.
        // Preserve corrective packets too; poll waits for vanilla to resolve that scope.
        receipt.block(sameContext(c),pos.equals(target),true,state.toString(),expected,tick);
    }
    void serverInventory(Minecraft c,Object sender,int containerId,int slot,boolean direct,ItemStack packet,long tick) {
        boolean correct=packet.is(mode==BucketWaterPolicy.Mode.FILL?Items.WATER_BUCKET:Items.BUCKET)&&packet.getCount()==1;
        receipt.inventory(sameContext(c)&&sender==connection,
            BucketWaterPolicy.selectedPacketSlot(selected,containerId,slot,direct),
            ItemStack.matches(packet,c.player.getInventory().getItem(selected)),correct,tick);
    }
    Outcome poll(Minecraft c,long tick,boolean timedOut) throws java.io.IOException {
        if(!idle(c)||!ownerCurrent.getAsBoolean()||!serverChunk(c,target)
                ||mode==BucketWaterPolicy.Mode.PLACE&&!boundedHole(c,false))return Outcome.WAITING;
        emptyAfter=count(c,Items.BUCKET);waterAfter=count(c,Items.WATER_BUCKET);
        boolean delta=BucketWaterPolicy.exactDelta(mode,emptyBefore,waterBefore,emptyAfter,waterAfter)&&inventoryUnchanged(c,true);
        if(receipt.done(!predictions.pending(c.level,target),delta,c.level.getBlockState(target).toString().equals(receipt.blockState()),tick)){
            retired=true;
            try{BucketUseStore.update(claimPath,snapshot(true));}
            catch(java.io.IOException|RuntimeException failed){retired=false;throw failed;}
            return Outcome.DONE;
        }return timedOut?Outcome.WAITING:Outcome.RUNNING;
    }
    void terminal(String outcome) throws java.io.IOException {
        if(!receipt.sent())return;
        JsonObject saved=snapshot(retired);saved.addProperty("stage","terminal_"+outcome);
        saved.addProperty("finished_at",System.currentTimeMillis());BucketUseStore.update(claimPath,saved);
    }
    JsonObject snapshot(boolean confirmed) {
        var out=new JsonObject();out.addProperty("request_id",requestId);out.addProperty("world_session",world);out.addProperty("operation",mode==BucketWaterPolicy.Mode.FILL?"bucket_fill":"bucket_place");
        JsonArray p=new JsonArray();p.add(target.getX());p.add(target.getY());p.add(target.getZ());out.add("pos",p);
        out.addProperty("use_count",receipt.sent()?1:0);out.addProperty("empty_buckets_before",emptyBefore);out.addProperty("empty_buckets_after",emptyAfter);
        out.addProperty("water_buckets_before",waterBefore);out.addProperty("water_buckets_after",waterAfter);
        out.addProperty("server_block_update_seen",receipt.blockSeen());out.addProperty("server_block_confirmed",receipt.blockConfirmed());out.addProperty("server_observed_state",receipt.blockState());
        out.addProperty("server_inventory_update_seen",receipt.inventorySeen());out.addProperty("server_inventory_confirmed",receipt.inventoryConfirmed());
        out.addProperty("confirmed",confirmed&&retired);out.addProperty("unknown_outcome",receipt.sent()&&!retired);
        out.addProperty("confirmation_scope","post_single_normal_use_current_connection_target_block_and_selected_bucket_slot_server_packets_plus_vanilla_prediction_settled_and_exact_inventory_delta_after_8_ticks");
        out.addProperty("expected_state_before",expectedState);
        if(mode==BucketWaterPolicy.Mode.FILL){
            out.addProperty("source_effect",sourceEffect);
            out.addProperty("source_observation_scope","matched_current_connection_source_cell_packet_may_show_preserved_or_regenerated_source_does_not_prove_source_removal");
        }
        out.addProperty("entity_scope","currently_client_loaded_entities_only");out.addProperty("automatic_retry_allowed",false);return out;
    }
}
