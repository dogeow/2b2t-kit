package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.ObserverBlock;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.context.BlockPlaceContext;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.AABB;
/** Lock an ordinary visible block use to the schematic's observer facing, as the printer does. */
final class ProjectedObserverPlacementGuard {
    private ProjectedObserverPlacementGuard(){}
    static boolean requested(JsonObject r){
        if(r==null||!r.has("projected_observer_place"))return false;
        var v=r.get("projected_observer_place");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Observer placement flag must be boolean");
        return v.getAsBoolean();
    }
    static RotationAim.Look require(Minecraft c,JsonObject r,BlockPos support,Direction face,boolean owned,BlockHitResult actualHit){
        if(!requested(r)||!owned||c.player==null||c.level==null||c.gameMode==null||c.player.hasInfiniteMaterials()
                ||c.player.getHealth()<19||c.player.getFoodData().getFoodLevel()<16||c.player.getAirSupply()<270
                ||c.player.isInWater()||c.player.isUnderWater()||c.player.isInLava()||c.player.isOnFire()
                ||c.gui.screen()!=null||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty()
                ||c.player.isUsingItem()||c.options.keyUse.isDown()||!c.player.getMainHandItem().is(Items.OBSERVER))
            throw new IllegalStateException("Healthy dry guarded observer owner required");
        var target=ProjectedSourceColumnGuard.point(r.get("place_pos"));
        var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(!support.relative(face).equals(target)||model==null||!selection.key().equals(ProjectionLoadPolicy.text(r,"placement_key",8192))
                ||!selection.contains(target)||!LitematicaAccess.inVisibleLayer(target)||!LitematicaAccess.loadingReason(selection).isEmpty())
            throw new IllegalStateException("Observer placement must match the locked projection and adjacent visible support");
        for(var p:new BlockPos[]{target,support}){
            var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
            if(!c.level.getWorldBorder().isWithinBounds(p)||c.level.isOutsideBuildHeight(p)||!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))
                throw new IllegalStateException("Current server-loaded observer target and support required");
        }
        var goal=model.getBlockState(target);var anchor=c.level.getBlockState(support);
        if(!goal.is(Blocks.OBSERVER)||!c.level.getBlockState(target).isAir()||c.level.getBlockEntity(target)!=null
                ||c.level.getBlockEntity(support)!=null||!anchor.getFluidState().isEmpty()||!anchor.isCollisionShapeFullBlock(c.level,support)
                ||c.player.getBoundingBox().intersects(new AABB(target))
                ||!c.level.getEntities(c.player,new AABB(target),e->e instanceof net.minecraft.world.entity.LivingEntity&&e.isAlive()).isEmpty())
            throw new IllegalStateException("Only a dry empty original observer cell and dry non-container support may be used");
        if(r.has("dry_paving_guard")||r.has("terrain_replace_stage"))throw new IllegalArgumentException("Observer placement cannot combine terrain operations");
        var angles=ProjectedObserverPlacementPolicy.look(goal.getValue(ObserverBlock.FACING).getName());
        if(actualHit!=null){
            if(!actualHit.getBlockPos().equals(support)||actualHit.getDirection()!=face)throw new IllegalStateException("Verified observer support face changed");
            var context=new BlockPlaceContext(c.player,InteractionHand.MAIN_HAND,c.player.getMainHandItem(),actualHit);
            var predicted=Blocks.OBSERVER.getStateForPlacement(context);
            if(!context.getClickedPos().equals(target)||predicted==null||predicted.getValue(ObserverBlock.FACING)!=goal.getValue(ObserverBlock.FACING))
                throw new IllegalStateException("Normal observer placement prediction disagrees with the requested facing");
        }
        return new RotationAim.Look(angles.yaw(),angles.pitch());
    }
}
