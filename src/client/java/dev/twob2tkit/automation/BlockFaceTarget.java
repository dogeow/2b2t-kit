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
            // A button or hook can cover the centre while the surrounding
            // wall face remains visible. Sample inside the same actual shape
            // surface; every choice still passes the normal outline ray.
            for(double u:new double[]{.2,.5,.8})for(double v:new double[]{.2,.5,.8}){
                if(u==.5&&v==.5)continue;
                double a=box.minX+(box.maxX-box.minX)*u;
                double b=box.minY+(box.maxY-box.minY)*u;
                double d=box.minZ+(box.maxZ-box.minZ)*v;
                points.add(switch(face){
                    case WEST,EAST->new Vec3(x,b,d);
                    case DOWN,UP->new Vec3(a,y,d);
                    case NORTH,SOUTH->new Vec3(a,box.minY+(box.maxY-box.minY)*v,z);
                });
            }
        }
        return List.copyOf(points);
    }
    static BlockHitResult visible(Minecraft c,Vec3 eye,BlockPos pos,Direction requested,double reach){
        var shape=c.level.getBlockState(pos).getShape(c.level,pos);
        var centres=new ArrayList<Vec3>();var edges=new ArrayList<Vec3>();
        for(var face:requested==null?Direction.values():new Direction[]{requested}){
            var sampled=points(shape,face);
            for(int i=0;i<sampled.size();i++)(i%9==0?centres:edges).add(sampled.get(i).add(pos.getX(),pos.getY(),pos.getZ()));
        }
        centres.sort(Comparator.comparingDouble(eye::distanceToSqr));edges.sort(Comparator.comparingDouble(eye::distanceToSqr));
        centres.addAll(edges);
        for(var point:centres){
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
