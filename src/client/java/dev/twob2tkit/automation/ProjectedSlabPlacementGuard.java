package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.SlabBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;

/** Choose a real visible support ray whose normal placement predicts the original single slab. */
final class ProjectedSlabPlacementGuard {
    private ProjectedSlabPlacementGuard(){}
    static boolean requested(JsonObject r){
        if(r==null||!r.has("projected_slab_place"))return false;
        var v=r.get("projected_slab_place");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Slab placement flag must be boolean");
        return v.getAsBoolean();
    }
    static BlockState require(Minecraft c,JsonObject r,BlockPos support,Direction face,boolean owned,BlockHitResult hit){
        if(!requested(r)||!owned||c.player==null||c.level==null||c.gameMode==null||c.player.hasInfiniteMaterials()
                ||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<16||c.player.getAirSupply()<270
                ||c.player.isInWater()||c.player.isUnderWater()||c.player.isInLava()||c.player.isOnFire()
                ||c.gui.screen()!=null||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty()
                ||c.player.isUsingItem()||c.options.keyUse.isDown())throw new IllegalStateException("Healthy dry guarded slab owner required");
        if(r.has("dry_paving_guard")||r.has("terrain_replace_stage")||ProjectedObserverPlacementGuard.requested(r))
            throw new IllegalArgumentException("Slab placement cannot combine other placement guards");
        var target=ProjectedSourceColumnGuard.point(r.get("place_pos"));
        var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(!support.relative(face).equals(target)||model==null||!selection.key().equals(ProjectionLoadPolicy.text(r,"placement_key",8192))
                ||!selection.contains(target)||!LitematicaAccess.inVisibleLayer(target)||!LitematicaAccess.loadingReason(selection).isEmpty())
            throw new IllegalStateException("Slab must match the locked visible projection and adjacent support");
        for(var p:new BlockPos[]{target,support}){
            var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
            if(!c.level.getWorldBorder().isWithinBounds(p)||c.level.isOutsideBuildHeight(p)||!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))
                throw new IllegalStateException("Current server-loaded slab target and support required");
        }
        var goal=model.getBlockState(target);var anchor=c.level.getBlockState(support);
        if(!(goal.getBlock() instanceof SlabBlock)||goal.getValue(SlabBlock.TYPE)==SlabType.DOUBLE||!goal.getFluidState().isEmpty()
                ||!c.player.getMainHandItem().is(goal.getBlock().asItem())||!c.level.getBlockState(target).isAir()
                ||c.level.getBlockEntity(target)!=null||c.level.getBlockEntity(support)!=null||!anchor.getFluidState().isEmpty()
                ||!(anchor.is(Blocks.COBBLESTONE)||anchor.is(Blocks.GLASS)||anchor.getBlock() instanceof SlabBlock)
                ||c.player.getBoundingBox().intersects(new AABB(target))
                ||!c.level.getEntities(c.player,new AABB(target),e->e instanceof net.minecraft.world.entity.LivingEntity&&e.isAlive()).isEmpty())
            throw new IllegalStateException("Only an empty original dry single slab cell and dry non-container support may be used");
        if(hit!=null&&(!BlockFaceTarget.matches(hit,support,face)||!predicts(c,hit,target,goal)))
            throw new IllegalStateException("Normal visible slab placement predicts a different position or half");
        return goal;
    }
    static boolean predicts(Minecraft c,BlockHitResult hit,BlockPos target,BlockState goal){
        var context=new BlockPlaceContext(c.player,InteractionHand.MAIN_HAND,c.player.getMainHandItem(),hit);
        var predicted=goal.getBlock().getStateForPlacement(context);
        return context.getClickedPos().equals(target)&&goal.equals(predicted);
    }
    static BlockHitResult visible(Minecraft c,JsonObject r,BlockPos support,Direction face,boolean owned){
        var goal=require(c,r,support,face,owned,null);var target=ProjectedSourceColumnGuard.point(r.get("place_pos"));
        return BlockFaceTarget.visible(c,c.player.getEyePosition(),support,face,c.player.blockInteractionRange(),
            hit->predicts(c,hit,target,goal));
    }
}
