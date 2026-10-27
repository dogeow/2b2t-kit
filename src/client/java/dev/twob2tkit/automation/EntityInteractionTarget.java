package dev.twob2tkit.automation;

import java.util.function.Predicate;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

/** Ordinary entity hit points: inside the current body, reachable and visibly clear. */
final class EntityInteractionTarget {
    record Selection(Vec3 hit, boolean inRange) {}
    private EntityInteractionTarget() {}

    static Selection find(AABB body,Vec3 eye,double reach,Predicate<Vec3> visible){
        if(body==null||eye==null||visible==null||!Double.isFinite(reach)||reach<=0
                ||!finite(body.minX,body.minY,body.minZ,body.maxX,body.maxY,body.maxZ,eye.x,eye.y,eye.z)
                ||body.getXsize()<=0||body.getYsize()<=0||body.getZsize()<=0)
            throw new IllegalArgumentException("Current finite entity body, eye and reach required");
        double skinX=Math.min(.01,body.getXsize()/4),skinZ=Math.min(.01,body.getZsize()/4);
        double nearX=Math.clamp(eye.x,body.minX+skinX,body.maxX-skinX);
        double nearZ=Math.clamp(eye.z,body.minZ+skinZ,body.maxZ-skinZ);
        double middleX=(body.minX+body.maxX)/2,middleZ=(body.minZ+body.maxZ)/2;
        double skinY=Math.min(.01,body.getYsize()/4);
        double[] heights={.55,.25,.75,.1,.9,
            (Math.clamp(eye.y,body.minY+skinY,body.maxY-skinY)-body.minY)/body.getYsize()};
        double range=Math.min(reach,128),rangeSquared=range*range;
        boolean inRange=false;
        for(double fraction:heights){
            double y=body.minY+body.getYsize()*fraction;
            for(int horizontal=0;horizontal<2;horizontal++){
                Vec3 point=new Vec3(horizontal==0?nearX:middleX,y,horizontal==0?nearZ:middleZ);
                if(eye.distanceToSqr(point)>rangeSquared)continue;
                inRange=true;
                if(visible.test(point))return new Selection(point,true);
            }
        }
        return new Selection(null,inRange);
    }
    private static boolean finite(double... values){
        for(double value:values)if(!Double.isFinite(value))return false;
        return true;
    }
}
