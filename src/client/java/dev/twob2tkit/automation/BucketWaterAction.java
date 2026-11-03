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
    private final boolean modelMinorThermal;
    private int emptyAfter,waterAfter;
    private boolean retired;
    private boolean observationDeferred;
    private String observationGate="not_polled";
    private String sourceEffect="unobserved";
    private final ProjectedWaterFlowGuard projectedColumn;
    private final ProjectedWaterlogDrain projectedDrain;
    private final ProjectedChannelWaterGuard projectedChannel;
    private final ProjectedSourceColumnGuard projectedSources;
    private final ProjectedSourceColumnSupplyGuard projectedSupply;
    private final ProjectedBentChannelGuard projectedBent;
    private final ProjectedBentChannelGuard projectedBentCollect;
    private final String sourceProfile;
    private final ProjectedTrapdoorWaterlog projectedWaterlog;
    private final ProjectedBubbleColumnGuard projectedBubble;
    private final ProjectedSourceReturnGuard projectedReturn;
    private final ProjectedModelWaterGuard projectedModelWater;
    private final ProjectedFlowCorrectionGuard flowCorrection;
    private boolean flowCorrectionProbeSent;
    private boolean sourceReturnProbeSent;

    BucketWaterAction(Minecraft c,JsonObject request,String world,String requestId,java.nio.file.Path root,BooleanSupplier ownerCurrent) throws java.io.IOException {
        mode=switch(text(request,"op")){case "bucket_fill"->BucketWaterPolicy.Mode.FILL;case "bucket_place"->BucketWaterPolicy.Mode.PLACE;default->throw new IllegalArgumentException("Only water bucket fill/place are supported");};
        target=position(request,"pos");expectedState=text(request,"expected_state");
        boolean column=ProjectedWaterFlowGuard.requested(request);
        if(column&&mode!=BucketWaterPolicy.Mode.PLACE)throw new IllegalArgumentException("Projected water column is place-only");
        projectedColumn=column?new ProjectedWaterFlowGuard(request,target):null;
        boolean drain=ProjectedWaterlogDrain.requested(request);
        if(drain&&(mode!=BucketWaterPolicy.Mode.FILL||column))throw new IllegalArgumentException("Projected waterlogged drain is an explicit fill-only operation");
        projectedDrain=drain?new ProjectedWaterlogDrain(c,request,target):null;
        boolean channel=ProjectedChannelWaterGuard.requested(request);
        if(!channel&&request.has("channel_service_ceiling"))throw new IllegalArgumentException("A service ceiling requires explicit projected channel mode");
        if(channel&&(mode!=BucketWaterPolicy.Mode.PLACE||column||drain))
            throw new IllegalArgumentException("Projected channel is an exclusive place-only operation");
        projectedChannel=channel?new ProjectedChannelWaterGuard(request,target):null;
        boolean sources=ProjectedSourceColumnGuard.requested(request);
        if(sources&&!ProjectedSourceColumnPolicy.exclusivePlace(mode==BucketWaterPolicy.Mode.PLACE,column,drain,channel))
            throw new IllegalArgumentException("Source-column repair is an exclusive place-only operation");
        projectedSources=sources?new ProjectedSourceColumnGuard(c,request,target):null;
        boolean supply=ProjectedSourceColumnSupplyGuard.requested(request);
        if(supply&&!SourceColumnSupplyPolicy.exclusiveFill(mode==BucketWaterPolicy.Mode.FILL,column,drain,channel,sources))
            throw new IllegalArgumentException("Source-column supply is an exclusive fill-only operation");
        if(!supply&&request.has("source_supply_completed_overflow"))throw new IllegalArgumentException("Completed overflow supply requires explicit source supply mode");
        projectedSupply=supply?new ProjectedSourceColumnSupplyGuard(c,request,target):null;
        boolean bent=ProjectedBentChannelGuard.requested(request);
        if(bent&&!ProjectedBentChannelPolicy.exclusive(mode==BucketWaterPolicy.Mode.PLACE,column,drain,channel,sources,supply))
            throw new IllegalArgumentException("Bent overflow is an exclusive place-only operation");
        if(!bent&&request.has("projected_bent_channel_seed"))throw new IllegalArgumentException("Seed requires explicit bent-channel mode");
        projectedBent=bent?new ProjectedBentChannelGuard(c,request,target):null;
        boolean collect=ProjectedBentChannelGuard.collectRequested(request);
        if(collect&&(mode!=BucketWaterPolicy.Mode.FILL||column||drain||channel||sources||supply||bent||ProjectedTrapdoorWaterlog.requested(request)))throw new IllegalArgumentException("Bent seed collection is an exclusive fill operation");
        projectedBentCollect=collect?new ProjectedBentChannelGuard(c,request,target):null;
        if((request.has("bent_service_ceiling")||request.has("bent_middle_ceiling"))&&!bent&&!collect)throw new IllegalArgumentException("Bent service ceiling requires explicit bent operation");
        boolean sourceReturn=ProjectedSourceReturnGuard.requested(request);
        if(request.has("source_column_profile")&&!sources&&!supply&&!bent&&!collect&&!sourceReturn)throw new IllegalArgumentException("Source profile needs an explicit source or overflow operation");
        sourceProfile=ProjectedSourceColumnGuard.profileRows(request)==4?"four_rows":"nine_rows";
        boolean waterlog=ProjectedTrapdoorWaterlog.requested(request);
        if(waterlog&&!ProjectedTrapdoorRowPolicy.exclusive(mode==BucketWaterPolicy.Mode.PLACE,column,drain,channel,sources,supply,bent))throw new IllegalArgumentException("Trapdoor waterlogging is an exclusive place-only operation");
        projectedWaterlog=waterlog?new ProjectedTrapdoorWaterlog(c,request,target):null;
        boolean bubble=ProjectedBubbleColumnGuard.requested(request);
        if(bubble&&!ProjectedBubblePolicy.exclusive(mode==BucketWaterPolicy.Mode.PLACE,column,drain,channel,sources,supply,bent,collect,waterlog))throw new IllegalArgumentException("Bubble column is an exclusive place-only operation");
        if(!bubble&&(request.has("bubble_bounds")||request.has("bubble_service_cap")||request.has("bubble_boundary_pins")))throw new IllegalArgumentException("Bubble geometry requires explicit bubble mode");
        projectedBubble=bubble?new ProjectedBubbleColumnGuard(request,target):null;
        if(sourceReturn&&!ProjectedBubblePolicy.exclusive(mode==BucketWaterPolicy.Mode.PLACE,column,drain,channel,sources,supply,bent,collect,waterlog,bubble))throw new IllegalArgumentException("Source return is an exclusive place-only operation");
        projectedReturn=sourceReturn?new ProjectedSourceReturnGuard(c,request,target):null;
        boolean modelWater=ProjectedModelWaterGuard.requested(request);
        if(!modelWater&&(request.has("model_water_bounds")||request.has("model_water_tiered_containment")))throw new IllegalArgumentException("Model bounds require explicit source mode");
        if(modelWater&&!ProjectedBubblePolicy.exclusive(mode==BucketWaterPolicy.Mode.PLACE,column,drain,channel,sources,supply,bent,collect,waterlog,bubble,sourceReturn))throw new IllegalArgumentException("Model source mode is exclusive place-only");
        modelMinorThermal=ProjectedModelWaterGuard.option(request,"model_water_minor_thermal");
        ProjectedModelWaterGuard.option(request,"model_water_remote_calm_creeper");
        projectedModelWater=modelWater?new ProjectedModelWaterGuard(request,target):null;
        boolean flowDrain=ProjectedFlowCorrectionGuard.requested(request);
        if(flowDrain&&(mode!=BucketWaterPolicy.Mode.FILL||column||drain||channel||sources||supply||bent||collect||waterlog||bubble||sourceReturn||modelWater))throw new IllegalArgumentException("Extra flow source drain is an exclusive fill-only operation");
        flowCorrection=flowDrain?new ProjectedFlowCorrectionGuard(request,target):null;
        if(expectedState.isBlank())throw new IllegalArgumentException("An exact fresh target state is required");
        support=mode==BucketWaterPolicy.Mode.PLACE?position(request,"support"):target;
        face=mode==BucketWaterPolicy.Mode.PLACE?Direction.valueOf(text(request,"face").toUpperCase(java.util.Locale.ROOT)):null;
        expectedSupport=mode==BucketWaterPolicy.Mode.PLACE?text(request,"expected_support_state"):"";
        if(mode==BucketWaterPolicy.Mode.PLACE&&((projectedWaterlog!=null?!support.equals(target)||face!=Direction.DOWN:!support.relative(face).equals(target))||expectedSupport.isBlank()))
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
        return sameContext(c)&&c.gui.screen()==null&&c.player.containerMenu==c.player.inventoryMenu
            &&c.player.containerMenu.getCarried().isEmpty()&&!c.player.isUsingItem()&&!c.options.keyUse.isDown()
            &&c.player.getInventory().getSelectedSlot()==selected&&!c.player.hasInfiniteMaterials()
            &&!c.player.isInWater()&&!c.player.isInLava()
            &&((!c.player.isOnFire()&&c.player.getHealth()>=health)
                ||projectedModelWater!=null&&ProjectedModelWaterGuard.thermalWorkAllowed(c,modelMinorThermal));
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
        if(projectedModelWater!=null){projectedModelWater.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()));return true;}
        if(projectedReturn!=null){projectedReturn.require(c);return true;}
        if(projectedBubble!=null){projectedBubble.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()));return true;}
        if(projectedWaterlog!=null){projectedWaterlog.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()));return true;}
        if(projectedBent!=null){projectedBent.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()));return true;}
        if(projectedSources!=null){projectedSources.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()));return true;}
        if(projectedColumn!=null){projectedColumn.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()));return true;}
        if(projectedChannel!=null){projectedChannel.require(c,BucketWaterPolicy.columnRequiresAir(airRequired,receipt.sent()));return true;}
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
            if(flowCorrection!=null)flowCorrection.require(c,true);
            if(projectedSupply!=null)projectedSupply.requireBefore(c);
            if(projectedBentCollect!=null)projectedBentCollect.require(c,true);
            if(projectedDrain!=null)projectedDrain.requireBefore(c);
            else if(!plainSource(c.level.getBlockState(target))||c.level.getBlockEntity(target)!=null)
                throw new IllegalStateException("Bucket fill requires a plain level-0 water source, never flowing water, waterlogged blocks or lava");
        }else if(!boundedHole(c,true)||!serverChunk(c,support)||!c.level.getBlockState(support).toString().equals(expectedSupport)
                ||projectedWaterlog==null&&c.level.getBlockState(support).getBlock() instanceof LiquidBlockContainer)
            throw new IllegalStateException("Bucket place needs actual air in a dry full-block basin with bottom and four sides, and the exact non-waterloggable support");
        if(!c.level.getEntities((Entity)null,new AABB(target),e->e.isAlive()
                &&SourceColumnSupplyPolicy.entityBlocks(mode==BucketWaterPolicy.Mode.FILL,projectedSupply!=null,e==c.player)).isEmpty())
            throw new IllegalStateException("Bucket target contains a currently loaded entity");
    }
    Vec3 aim(Minecraft c) {
        if(mode==BucketWaterPolicy.Mode.FILL){
            if(projectedDrain!=null){
                var hit=ProjectedDrainAim.visible(c.level,c.player.getEyePosition(),target,
                    c.player.blockInteractionRange()-.2,net.minecraft.world.phys.shapes.CollisionContext.of(c.player));
                if(hit==null)throw new IllegalStateException("No exposed waterlogged surface within normal bucket reach");
                Vec3 point=BlockFaceTarget.inside(hit);entityRayClear(c,point);return point;
            }
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
        if(!BlockFaceTarget.matches(hit,support,face)||mode==BucketWaterPolicy.Mode.PLACE&&(projectedWaterlog!=null?!hit.getBlockPos().equals(target):!hit.getBlockPos().relative(hit.getDirection()).equals(target)))
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
        if(flowCorrection!=null){
            if(!sameContext(c)||!ownerCurrent.getAsBoolean()||!c.player.getMainHandItem().is(Items.WATER_BUCKET)||c.player.getMainHandItem().getCount()!=1)throw new IllegalStateException("Drain verification context changed after one use; do not retry");
            flowCorrectionProbeSent=true;var probeClaim=snapshot(false);probeClaim.addProperty("stage","before_single_inert_flow_probe");BucketUseStore.update(claimPath,probeClaim);flowCorrection.probe(c);
        }
        if(projectedReturn!=null){
            // One ordinary bucket use above may preserve a source without a block
            // packet. One inert block interaction asks vanilla to send its real
            // support and adjacent block updates. Never fall back to useItem.
            projectedReturn.require(c);
            if(!sameContext(c)||!ownerCurrent.getAsBoolean()||!c.player.getMainHandItem().is(Items.BUCKET)||c.player.getMainHandItem().getCount()!=1
                    ||!c.level.getBlockState(support).toString().equals(expectedSupport))throw new IllegalStateException("Return verification context changed after the one use; do not retry");
            sourceReturnProbeSent=true;var probeClaim=snapshot(false);probeClaim.addProperty("stage","before_single_inert_return_probe");BucketUseStore.update(claimPath,probeClaim);
            projectedReturn.probe(c,hit);
        }

    }
    void serverBlock(Minecraft c,BlockPos pos,BlockState state,boolean applied,long tick) {
        boolean expected=mode==BucketWaterPolicy.Mode.PLACE?(projectedBubble!=null?projectedBubble.expectedPacket(state):projectedWaterlog!=null?projectedWaterlog.expectedPacket(state):plainSource(state)):projectedDrain!=null?projectedDrain.expectedPacket(state):BucketWaterPolicy.fillResult(state.isAir(),state.is(Blocks.WATER));
        if(mode==BucketWaterPolicy.Mode.FILL&&receipt.sent()&&sameContext(c)&&pos.equals(target))
            sourceEffect=projectedDrain!=null?(expected?"waterlogged_block_drained":"unexpected_or_refilled_waterlogged_block")
                :state.isAir()?"removed":plainSource(state)?"preserved_or_regenerated":state.is(Blocks.WATER)?"changed_to_flowing":"unexpected_server_state";
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
        boolean stable=false;
        if(!sameContext(c))return Outcome.WAITING;
        try{
            if(!idle(c))observationGate="idle_changed";
            else if(!ownerCurrent.getAsBoolean())observationGate="owner_or_protection_changed";
            else if(!serverChunk(c,target))observationGate="target_chunk_changed";
            else if(mode==BucketWaterPolicy.Mode.PLACE&&!boundedHole(c,false))observationGate="placement_geometry_changed";
            else if(flowCorrection!=null&&!flowCorrection.current(c))observationGate="original_flow_target_changed";
            else if(projectedDrain!=null&&!projectedDrain.current(c))observationGate="drain_geometry_changed";
            else if(projectedSupply!=null&&!projectedSupply.current(c))observationGate="supply_geometry_changed";
            else if(projectedBentCollect!=null){projectedBentCollect.require(c,false);stable=true;observationGate="ready";}
            else {stable=true;observationGate="ready";}
        }catch(RuntimeException changed){observationGate="geometry_recheck_changed";}
        if(!stable){
            // No more input is sent. Keep the original callbacks alive within
            // the existing deadline so a transient guard change cannot erase
            // the two server receipts that arrive after this single use.
            observationDeferred|=receipt.sent();
            return BucketWaterPolicy.awaitOriginalPackets(receipt.sent(),sameContext(c),timedOut)?Outcome.RUNNING:Outcome.WAITING;
        }
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
        out.addProperty("post_use_observation_deferred",observationDeferred);out.addProperty("post_use_observation_gate",observationGate);
        out.addProperty("use_count",receipt.sent()?1:0);out.addProperty("empty_buckets_before",emptyBefore);out.addProperty("empty_buckets_after",emptyAfter);
        out.addProperty("water_buckets_before",waterBefore);out.addProperty("water_buckets_after",waterAfter);
        out.addProperty("server_block_update_seen",receipt.blockSeen());out.addProperty("server_block_confirmed",receipt.blockConfirmed());out.addProperty("server_observed_state",receipt.blockState());
        out.addProperty("server_inventory_update_seen",receipt.inventorySeen());out.addProperty("server_inventory_confirmed",receipt.inventoryConfirmed());
        out.addProperty("confirmed",confirmed&&retired);out.addProperty("unknown_outcome",receipt.sent()&&!retired);
        out.addProperty("confirmation_scope","post_single_normal_use_current_connection_target_block_and_selected_bucket_slot_server_packets_plus_vanilla_prediction_settled_and_exact_inventory_delta_after_8_ticks");
        out.addProperty("expected_state_before",expectedState);
        out.addProperty("flow_source_drain_probe_count",flowCorrectionProbeSent?1:0);out.addProperty("projected_flow_source_drain",flowCorrection!=null);out.addProperty("projected_source_return",projectedReturn!=null);out.addProperty("projected_model_water_source",projectedModelWater!=null);
        out.addProperty("source_return_block_probe_count",sourceReturnProbeSent?1:0);
        out.addProperty("projected_bubble_column",projectedBubble!=null);
        if(projectedBubble!=null)out.addProperty("expected_bubble_state",projectedBubble.expectedState());
        out.addProperty("projected_bent_channel",projectedBent!=null);
        out.addProperty("projected_bent_channel_seed",projectedBent!=null&&projectedBent.seed());
        out.addProperty("projected_bent_channel_collect_index",projectedBentCollect==null?0:projectedBentCollect.collectIndex());
        var bend=projectedBent!=null?projectedBent:projectedBentCollect;
        if(bend!=null){
            if(bend.serviceRoof()!=null){var roof=new JsonArray();roof.add(bend.serviceRoof().getX());roof.add(bend.serviceRoof().getY());roof.add(bend.serviceRoof().getZ());out.add("bent_service_ceiling",roof);}
            if(bend.middleRoof()!=null){var roof=new JsonArray();roof.add(bend.middleRoof().getX());roof.add(bend.middleRoof().getY());roof.add(bend.middleRoof().getZ());out.add("bent_middle_ceiling",roof);}
        }
        if(projectedSources!=null||projectedSupply!=null||projectedBent!=null||projectedBentCollect!=null||projectedReturn!=null)out.addProperty("source_column_profile",sourceProfile);
        out.addProperty("projected_trapdoor_waterlog",projectedWaterlog!=null);
        if(projectedWaterlog!=null)out.addProperty("expected_wet_state",projectedWaterlog.expectedWet());
        out.addProperty("projected_water_column",projectedColumn!=null);
        out.addProperty("projected_source_column",projectedSources!=null);
        out.addProperty("projected_source_column_supply",projectedSupply!=null);
        out.addProperty("source_supply_completed_overflow",projectedSupply!=null&&projectedSupply.completedOverflow());
        out.addProperty("projected_waterlog_drain",projectedDrain!=null);
        out.addProperty("projected_water_channel",projectedChannel!=null);
        if(projectedChannel!=null){
            out.addProperty("channel_length",8);out.addProperty("channel_direction","west");
            BlockPos service=projectedChannel.serviceCeiling();var ceiling=new JsonArray();ceiling.add(service.getX());ceiling.add(service.getY());ceiling.add(service.getZ());out.add("channel_service_ceiling",ceiling);
            out.addProperty("channel_flow_observation_scope","source_and_bucket_only_downstream_requires_independent_scan");
        }
        if(projectedDrain!=null)out.addProperty("expected_dry_state",projectedDrain.expectedDry());
        if(mode==BucketWaterPolicy.Mode.FILL){
            out.addProperty("source_effect",sourceEffect);
            out.addProperty("source_observation_scope","matched_current_connection_source_cell_packet_may_show_preserved_or_regenerated_source_does_not_prove_source_removal");
        }
        out.addProperty("entity_scope","currently_client_loaded_entities_only");out.addProperty("automatic_retry_allowed",false);return out;
    }
}
