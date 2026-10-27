package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.twob2tkit.MeteorModules;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.FenceGateBlock;
import net.minecraft.world.level.block.LiquidBlockContainer;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;

/** Opt-in construction only; the ordinary fluid-neighbour prohibition remains the default. */
final class ControlledWaterReleaseGuard {
    private ControlledWaterReleaseGuard(){}
    static boolean requested(JsonObject request){
        if(request==null||!request.has("controlled_water_release"))return false;
        var value=request.get("controlled_water_release");
        if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Controlled water release flag must be boolean");
        return value.getAsBoolean();
    }
    private static ControlledWaterReleasePolicy.Cell cell(JsonArray a){
        if(a==null||a.size()!=3)throw new IllegalArgumentException("Release bounds require integer XYZ");
        int[] v=new int[3];
        for(int i=0;i<3;i++){
            if(!a.get(i).isJsonPrimitive()||!a.get(i).getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Release bounds require integer XYZ");
            try{v[i]=a.get(i).getAsBigDecimal().intValueExact();}
            catch(ArithmeticException e){throw new IllegalArgumentException("Release bounds require integer XYZ",e);}
            if(Math.abs((long)v[i])>30_000_000)throw new IllegalArgumentException("Release bound outside world limits");
        }
        return new ControlledWaterReleasePolicy.Cell(v[0],v[1],v[2]);
    }
    static void require(Minecraft c,JsonObject request,BlockPos target,boolean owned,boolean started){
        if(!request.has("water_release_bounds")||!request.get("water_release_bounds").isJsonObject())throw new IllegalArgumentException("Controlled release needs exact enclosure bounds");
        var box=request.getAsJsonObject("water_release_bounds");
        var bounds=new ControlledWaterReleasePolicy.Bounds(cell(box.getAsJsonArray("min")),cell(box.getAsJsonArray("max")));
        boolean healthy=owned&&c.player!=null&&c.level!=null&&c.player.getHealth()>=19&&!c.player.hasInfiniteMaterials()
            &&c.gui.screen()==null&&c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty()
            &&!c.player.isInWater()&&!c.player.isInLava()&&!c.player.isOnFire()&&!c.player.isUsingItem()&&!c.options.keyUse.isDown()
            &&c.player.getY()>=target.getY()+1&&(c.player.onGround()||MeteorModules.isActive(MeteorModules.FLIGHT))
            &&c.level.noCollision(c.player,c.player.getBoundingBox())&&c.player.getMainHandItem().is(ItemTags.PICKAXES)
            &&(!c.player.getMainHandItem().isDamageableItem()||c.player.getMainHandItem().getMaxDamage()-c.player.getMainHandItem().getDamageValue()>=(started?1:33));
        if(c.level==null)throw new IllegalStateException("Controlled release world is unavailable");
        var state=c.level.getBlockState(target);
        boolean removed=started&&(state.isAir()||state.is(Blocks.WATER));
        boolean exact=state.toString().equals(request.has("expected_state")?request.get("expected_state").getAsString():"");
        boolean allowed=removed||exact&&state.is(Blocks.COBBLESTONE)&&state.getFluidState().isEmpty()&&c.level.getBlockEntity(target)==null;
        var min=bounds.min();var max=bounds.max();
        if(!bounds.bounded()||min.y()<c.level.getMinY()||max.y()>=c.level.getMaxY())throw new IllegalArgumentException("Controlled release enclosure exceeds local build limits");
        var living=c.level.getEntities(c.player,new AABB(min.x(),min.y(),min.z(),max.x()+1,max.y()+1,max.z()+1),e->e instanceof LivingEntity&&e.isAlive());
        var world=new ControlledWaterReleasePolicy.World(){
            private BlockPos pos(ControlledWaterReleasePolicy.Cell p){return new BlockPos(p.x(),p.y(),p.z());}
            public boolean loaded(ControlledWaterReleasePolicy.Cell p){
                var q=pos(p);var chunk=c.level.getChunkSource().getChunk(q.getX()>>4,q.getZ()>>4,ChunkStatus.FULL,false);
                return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
            }
            public boolean barrier(ControlledWaterReleasePolicy.Cell p){
                var q=pos(p);var s=c.level.getBlockState(q);var block=s.getBlock();
                return s.getFluidState().isEmpty()&&c.level.getBlockEntity(q)==null&&!(block instanceof LiquidBlockContainer)
                    &&(block instanceof FenceGateBlock||!(block instanceof FallingBlock)&&s.isCollisionShapeFullBlock(c.level,q));
            }
            public boolean air(ControlledWaterReleasePolicy.Cell p){return c.level.getBlockState(pos(p)).isAir();}
            public boolean water(ControlledWaterReleasePolicy.Cell p){return c.level.getBlockState(pos(p)).is(Blocks.WATER);}
            public boolean otherFluid(ControlledWaterReleasePolicy.Cell p){var q=pos(p);return !c.level.getFluidState(q).isEmpty()&&!c.level.getBlockState(q).is(Blocks.WATER);}
            public boolean container(ControlledWaterReleasePolicy.Cell p){return c.level.getBlockEntity(pos(p))!=null;}
            public boolean living(ControlledWaterReleasePolicy.Cell p){var b=new AABB(pos(p));return c.player!=null&&c.player.getBoundingBox().intersects(b)||living.stream().anyMatch(e->e.getBoundingBox().intersects(b));}
        };
        String rejection=ControlledWaterReleasePolicy.rejection(world,bounds,new ControlledWaterReleasePolicy.Cell(target.getX(),target.getY(),target.getZ()),healthy,allowed);
        if(rejection!=null)throw new IllegalStateException(rejection);
    }
}
