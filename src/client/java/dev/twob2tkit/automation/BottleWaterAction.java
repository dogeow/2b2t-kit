package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.AreaEffectCloud;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.alchemy.PotionContents;
import net.minecraft.world.item.alchemy.Potions;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.LiquidBlock;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.function.BooleanSupplier;

/** One normal BottleItem use at registered source water with server inventory proof. */
final class BottleWaterAction {
    enum Outcome { RUNNING,DONE,WAITING }
    private final BottleWaterPolicy.Receipt receipt=new BottleWaterPolicy.Receipt();
    private final dev.twob2tkit.runtime.engine.BorerMiningConfirmation predictions=new dev.twob2tkit.runtime.engine.BorerMiningConfirmation();
    private final BlockPos target;
    private final String expectedState,world,requestId;
    private final Object level,connection;
    private final BooleanSupplier ownerCurrent;
    private final Path claimPath;
    private final List<ItemStack> before=new ArrayList<>();
    private final int selected,output,bottlesBefore,waterBefore;
    private final float health;
    private int bottlesAfter,waterAfter;
    private boolean retired;
    private final ItemStack water=PotionContents.createItemStack(Items.POTION,Potions.WATER);

    BottleWaterAction(Minecraft c,JsonObject request,String world,String requestId,Path root,BooleanSupplier ownerCurrent)throws java.io.IOException {
        JsonArray a=request.getAsJsonArray("pos");
        if(a==null||a.size()!=3)throw new IllegalArgumentException("Bottle source needs [x,y,z]");
        int[] xyz=new int[3];for(int i=0;i<3;i++){
            var value=a.get(i);
            if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Bottle source needs integer coordinates");
            double n=value.getAsDouble();if(!Double.isFinite(n)||n!=Math.rint(n)||Math.abs(n)>30_000_000)throw new IllegalArgumentException("Bottle source needs bounded integers");xyz[i]=(int)n;
        }
        target=new BlockPos(xyz[0],xyz[1],xyz[2]);
        expectedState=request.has("expected_state")?request.get("expected_state").getAsString():"";
        if(!"Block{minecraft:water}[level=0]".equals(expectedState)||!request.has("expected_hand")
            ||!"minecraft:glass_bottle".equals(request.get("expected_hand").getAsString()))
            throw new IllegalArgumentException("Bottle fill requires exact plain source water and a glass bottle");
        this.world=world;this.requestId=requestId;this.ownerCurrent=ownerCurrent;
        level=c.level;connection=c.getConnection();health=c.player.getHealth();selected=c.player.getInventory().getSelectedSlot();
        int empty=-1;for(int i=0;i<c.player.getInventory().getContainerSize();i++){
            var stack=c.player.getInventory().getItem(i);before.add(stack.copy());if(i<36&&empty<0&&stack.isEmpty())empty=i;
        }
        if(!c.player.getMainHandItem().is(Items.GLASS_BOTTLE))throw new IllegalArgumentException("Select an actual glass bottle first");
        output=BottleWaterPolicy.outputSlot(selected,c.player.getMainHandItem().getCount(),empty);
        if(output<0)throw new IllegalArgumentException("A stacked bottle needs one actual empty carried slot; never drop output");
        bottlesBefore=bottlesAfter=count(c,false);waterBefore=waterAfter=count(c,true);
        claimPath=BucketUseStore.path(root.resolve("bottle-water"),c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip,
            c.level.dimension().identifier().toString(),target.getX(),target.getY(),target.getZ());
        BucketUseStore.requireAvailable(claimPath);validate(c,false);
    }
    private int count(Minecraft c,boolean filled){int n=0;for(int i=0;i<36;i++){
        var s=c.player.getInventory().getItem(i);if(filled?ItemStack.isSameItemSameComponents(s,water):s.is(Items.GLASS_BOTTLE))n+=s.getCount();
    }return n;}
    private boolean same(Minecraft c){return c.player!=null&&c.level==level&&c.getConnection()==connection;}
    private boolean chunk(Minecraft c){return LoadedServerChunkEvidence.isServerChunk(c.level,
        c.level.getChunkSource().getChunk(target.getX()>>4,target.getZ()>>4,ChunkStatus.FULL,false));}
    private boolean source(Minecraft c){var s=c.level.getBlockState(target);return s.toString().equals(expectedState)&&s.is(Blocks.WATER)
        &&s.getFluidState().is(Fluids.WATER)&&s.getFluidState().isSource()&&s.getValue(LiquidBlock.LEVEL)==0&&c.level.getBlockEntity(target)==null;}
    private boolean idle(Minecraft c){return same(c)&&c.gui.screen()==null&&c.player.containerMenu==c.player.inventoryMenu
        &&c.player.containerMenu.getCarried().isEmpty()&&!c.player.isUsingItem()&&!c.options.keyUse.isDown()
        &&c.player.getInventory().getSelectedSlot()==selected&&!c.player.hasInfiniteMaterials()
        &&!c.player.isInWater()&&!c.player.isInLava()&&!c.player.isOnFire()&&c.player.getHealth()>=health;}
    private ItemStack expected(int slot){
        if(slot==output)return water;
        if(slot==selected){var remaining=before.get(selected).copy();remaining.shrink(1);return remaining;}
        return before.get(slot);
    }
    private boolean inventory(Minecraft c,boolean transformed){
        if(c.player.getInventory().getContainerSize()!=before.size())return false;
        for(int i=0;i<before.size();i++)if(!ItemStack.matches(transformed?expected(i):before.get(i),c.player.getInventory().getItem(i)))return false;
        return true;
    }
    private void validate(Minecraft c,boolean owner){
        if(!idle(c)||owner&&!ownerCurrent.getAsBoolean()||!chunk(c)||!source(c)||predictions.pending(c.level,target)
            ||!c.level.getWorldBorder().isWithinBounds(target)||c.level.isOutsideBuildHeight(target)||!inventory(c,false)
            ||c.player.getCooldowns().isOnCooldown(c.player.getMainHandItem()))
            throw new IllegalStateException("Bottle source, exact inventory, ownership or loaded chunk changed");
        // BottleItem checks dragon breath before its water ray. Reject clouds rather than producing another item.
        if(!c.level.getEntitiesOfClass(AreaEffectCloud.class,c.player.getBoundingBox().inflate(2),Entity::isAlive).isEmpty())
            throw new IllegalStateException("Bottle fill preserves nearby effect clouds");
    }
    private void clearRay(Minecraft c,Vec3 point){var eye=c.player.getEyePosition();
        for(var e:c.level.getEntities(c.player,new AABB(eye,point).inflate(.3),Entity::isAlive)){
            var box=e.getBoundingBox().inflate(e.getPickRadius());if(box.contains(eye)||box.clip(eye,point).isPresent())
                throw new IllegalStateException("Bottle water ray is occupied by a loaded entity");
        }
    }
    Vec3 aim(Minecraft c){var point=Vec3.atCenterOf(target);var hit=c.level.clip(new ClipContext(c.player.getEyePosition(),point,
        ClipContext.Block.OUTLINE,ClipContext.Fluid.SOURCE_ONLY,c.player));
        if(!BlockFaceTarget.matches(hit,target,null)||c.player.getEyePosition().distanceTo(point)>c.player.blockInteractionRange()-.2)
            throw new IllegalStateException("Bottle water is occluded or outside normal reach");clearRay(c,point);return point;}
    void useOnce(Minecraft c)throws java.io.IOException {
        if(receipt.sent())throw new IllegalStateException("Bottle fill already attempted; no second use allowed");validate(c,true);
        var eye=c.player.getEyePosition();var end=eye.add(c.player.calculateViewVector(c.player.getXRot(),c.player.getYRot()).scale(c.player.blockInteractionRange()));
        var hit=c.level.clip(new ClipContext(eye,end,ClipContext.Block.OUTLINE,ClipContext.Fluid.SOURCE_ONLY,c.player));
        if(!BlockFaceTarget.matches(hit,target,null)||!c.level.mayInteract(c.player,target))throw new IllegalStateException("Fresh normal bottle ray or permissions changed");
        clearRay(c,hit.getLocation());var claim=snapshot(false);claim.addProperty("stage","claimed_before_single_use");
        claim.addProperty("use_may_have_been_sent",true);BucketUseStore.claim(claimPath,claim);receipt.sendOnce();
        if(!c.gameMode.useItem(c.player,InteractionHand.MAIN_HAND).consumesAction())throw new IllegalStateException("Bottle use sent but unconfirmed; do not retry");
    }
    void serverInventory(Minecraft c,Object sender,int containerId,int slot,boolean direct,ItemStack packet,long tick){
        int actual=BottleWaterPolicy.inventorySlot(containerId,slot,direct);
        if(actual!=selected&&actual!=output)return;
        receipt.inventory(same(c)&&sender==connection,actual,selected,output,
            ItemStack.matches(packet,c.player.getInventory().getItem(actual)),ItemStack.matches(packet,expected(actual)),tick);
    }
    Outcome poll(Minecraft c,long tick,boolean timedOut)throws java.io.IOException {
        if(!idle(c)||!ownerCurrent.getAsBoolean()||!chunk(c)||!source(c))return Outcome.WAITING;
        bottlesAfter=count(c,false);waterAfter=count(c,true);
        if(receipt.done(true,true,!predictions.pending(c.level,target),inventory(c,true)
            &&BottleWaterPolicy.exactDelta(bottlesBefore,bottlesAfter,waterBefore,waterAfter),tick)){
            retired=true;try{BucketUseStore.update(claimPath,snapshot(true));}catch(java.io.IOException|RuntimeException failed){retired=false;throw failed;}return Outcome.DONE;
        }return timedOut?Outcome.WAITING:Outcome.RUNNING;
    }
    void terminal(String outcome)throws java.io.IOException {if(!receipt.sent())return;var saved=snapshot(retired);
        saved.addProperty("stage","terminal_"+outcome);BucketUseStore.update(claimPath,saved);}
    JsonObject snapshot(boolean confirmed){var out=new JsonObject();out.addProperty("request_id",requestId);out.addProperty("world_session",world);
        out.addProperty("operation","bottle_fill");var p=new JsonArray();p.add(target.getX());p.add(target.getY());p.add(target.getZ());out.add("pos",p);
        out.addProperty("selected_slot",selected);out.addProperty("water_slot",output);out.addProperty("water_item","minecraft:potion");out.addProperty("potion","minecraft:water");
        out.addProperty("use_count",receipt.sent()?1:0);out.addProperty("empty_bottles_before",bottlesBefore);out.addProperty("empty_bottles_after",bottlesAfter);
        out.addProperty("water_bottles_before",waterBefore);out.addProperty("water_bottles_after",waterAfter);
        out.addProperty("server_hand_confirmed",receipt.handConfirmed());out.addProperty("server_water_slot_confirmed",receipt.outputConfirmed());
        out.addProperty("confirmed",confirmed&&retired);out.addProperty("unknown_outcome",receipt.sent()&&!retired);out.addProperty("automatic_retry_allowed",false);
        out.addProperty("source_not_consumed_by_bottle_use",true);out.addProperty("expected_state_before",expectedState);
        out.addProperty("confirmation_scope","single_normal_bottle_use_current_connection_exact_hand_and_water_potion_slot_server_packets_source_unchanged_prediction_settled_inventory_delta_after_8_ticks");return out;}
}
