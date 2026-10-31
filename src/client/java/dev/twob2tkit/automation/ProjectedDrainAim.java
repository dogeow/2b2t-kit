package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.Comparator;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.shapes.CollisionContext;

/** Find a real exposed waterlogged surface using the same ray as vanilla BucketItem. */
final class ProjectedDrainAim {
    private ProjectedDrainAim(){}
    static BlockHitResult visible(BlockGetter level,Vec3 eye,BlockPos target,double reach,CollisionContext context){
        if(!Double.isFinite(reach)||reach<=0)return null;
        var shape=level.getBlockState(target).getShape(level,target,context);
        var points=new ArrayList<Vec3>();
        for(var face:Direction.values())for(var point:BlockFaceTarget.points(shape,face))
            points.add(point.add(target.getX(),target.getY(),target.getZ()));
        points.sort(Comparator.comparingDouble(eye::distanceToSqr));
        for(var point:points){
            if(eye.distanceTo(point)>reach)continue;
            var hit=level.clip(new ClipContext(eye,point,ClipContext.Block.OUTLINE,ClipContext.Fluid.SOURCE_ONLY,context));
            if(BlockFaceTarget.matches(hit,target,null)&&eye.distanceTo(hit.getLocation())<=reach)return hit;
        }return null;
    }
}
