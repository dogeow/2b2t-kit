package dev.twob2tkit.automation;

import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.*;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.*;
import net.minecraft.world.phys.shapes.VoxelShape;

/** Aim inside a real outline surface, then use the ray's actual position and face. */
final class BlockFaceTarget {
    static final double INSET=1e-5;
    static List<Vec3> points(VoxelShape shape,Direction face){
        var points=new ArrayList<Vec3>();
        for(var box:shape.toAabbs()){
            double x=(box.minX+box.maxX)*.5,y=(box.minY+box.maxY)*.5,z=(box.minZ+box.maxZ)*.5;
            double ex=Math.min(INSET,(box.maxX-box.minX)*.25),ey=Math.min(INSET,(box.maxY-box.minY)*.25),ez=Math.min(INSET,(box.maxZ-box.minZ)*.25);
            switch(face){
                case WEST->x=box.minX+ex;case EAST->x=box.maxX-ex;
                case DOWN->y=box.minY+ey;case UP->y=box.maxY-ey;
                case NORTH->z=box.minZ+ez;case SOUTH->z=box.maxZ-ez;
            }
            points.add(new Vec3(x,y,z));
        }
        return List.copyOf(points);
    }
    static BlockHitResult visible(Minecraft c,Vec3 eye,BlockPos pos,Direction requested,double reach){
        var shape=c.level.getBlockState(pos).getShape(c.level,pos);
        var candidates=new ArrayList<Vec3>();
        for(var face:requested==null?Direction.values():new Direction[]{requested})
            for(var p:points(shape,face))candidates.add(p.add(pos.getX(),pos.getY(),pos.getZ()));
        candidates.sort(Comparator.comparingDouble(eye::distanceToSqr));
        for(var point:candidates){
            if(eye.distanceTo(point)>reach)continue;
            var hit=c.level.clip(new ClipContext(eye,point,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
            if(matches(hit,pos,requested))return hit;
        }
        return null;
    }
    static boolean matches(BlockHitResult hit,BlockPos pos,Direction requested){
        return hit!=null&&hit.getType()==HitResult.Type.BLOCK&&hit.getBlockPos().equals(pos)&&(requested==null||hit.getDirection()==requested);
    }
    static Vec3 inside(BlockHitResult hit){
        var face=hit.getDirection();return hit.getLocation().add(-face.getStepX()*INSET,-face.getStepY()*INSET,-face.getStepZ()*INSET);
    }
    private BlockFaceTarget(){}
}
