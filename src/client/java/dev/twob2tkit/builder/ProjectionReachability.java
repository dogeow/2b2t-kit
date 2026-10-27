package dev.twob2tkit.builder;

import java.util.ArrayList;
import java.util.List;
import java.util.function.Predicate;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

/** Read-only reach probes inside the intended cell; native placement still proves its actual hit. */
public final class ProjectionReachability {
    private static final double INSET=1e-5;
    private static final List<Vec3> OFFSETS=offsets();
    private ProjectionReachability() {}

    private static List<Vec3> offsets() {
        var points=new ArrayList<Vec3>();
        points.add(new Vec3(.5,.5,.5));
        for(var face:Direction.values())points.add(onFace(face,.5,.5));
        for(var face:Direction.values())for(double u:new double[]{.2,.5,.8})for(double v:new double[]{.2,.5,.8})
            if(u!=.5||v!=.5)points.add(onFace(face,u,v));
        return List.copyOf(points);
    }
    private static Vec3 onFace(Direction face,double u,double v) {
        return switch(face) {
            case WEST -> new Vec3(INSET,u,v);
            case EAST -> new Vec3(1-INSET,u,v);
            case DOWN -> new Vec3(u,INSET,v);
            case UP -> new Vec3(u,1-INSET,v);
            case NORTH -> new Vec3(u,v,INSET);
            case SOUTH -> new Vec3(u,v,1-INSET);
        };
    }
    static boolean visible(Vec3 eye,BlockPos target,double reach,Predicate<Vec3> rayClear) {
        if(!Double.isFinite(eye.x)||!Double.isFinite(eye.y)||!Double.isFinite(eye.z)
                ||!Double.isFinite(reach)||reach<=0)return false;
        for(var offset:OFFSETS) {
            var point=offset.add(target.getX(),target.getY(),target.getZ());
            if(eye.distanceToSqr(point)<=reach*reach&&rayClear.test(point))return true;
        }
        return false;
    }
    public static boolean reachable(Minecraft client,Vec3 eye,BlockPos target,double reach) {
        if(client.level==null||client.player==null)return false;
        return visible(eye,target,reach,point->{
            var hit=client.level.clip(new ClipContext(eye,point,ClipContext.Block.COLLIDER,
                ClipContext.Fluid.NONE,client.player));
            return hit.getType()==HitResult.Type.MISS||hit.getBlockPos().equals(target);
        });
    }
}
