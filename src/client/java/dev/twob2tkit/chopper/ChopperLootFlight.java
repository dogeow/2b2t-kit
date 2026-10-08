package dev.twob2tkit.chopper;

import dev.twob2tkit.KitClient;
import dev.twob2tkit.runtime.api.BuildNavigation;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerAreaFlightSession;
import dev.twob2tkit.runtime.engine.BorerFlyPath;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Bounded real flight to a pickup body, with fresh collision checks and local replanning. */
final class ChopperLootFlight {
    private final BorerAreaFlightSession flight=new BorerAreaFlightSession();
    private BuildNavigation navigation;
    private BuildNavigation.Search search;
    private List<BlockPos> route=List.of();
    private Object world;
    private UUID target;
    private Vec3 targetPosition;
    private BlockPos low,high;
    private int node,replans,stalled,liftAttempts;
    private Vec3 previous;
    private boolean acquired,blocked;
    private boolean originallyFlying;

    boolean tick(Minecraft c,ItemEntity item) {
        var p=c.player;
        if(p==null||c.level==null||c.screen!=null||!item.isAlive()){pause(c);return false;}
        if(world!=c.level||!Objects.equals(target,item.getUUID())){
            resetRoute();world=c.level;target=item.getUUID();replans=stalled=liftAttempts=0;blocked=false;
        }
        if(!acquired){
            originallyFlying=dev.twob2tkit.runtime.engine.BorerFlight.isFlying(p);
            flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/chopper-loot-flight.bak"));
            String error=flight.acquire(p);
            if(error!=null)throw new IllegalStateException("拾取飞行无法接管："+error);
            acquired=true;
        }
        flight.fly();
        if(!c.level.noCollision(p,p.getBoundingBox())){
            if(recoverThinFloorOverlap(c))return true;
            flight.hover();ChopperKeys.holdStill(c);blocked=true;return false;
        }
        if(pickupIntersects(p.getBoundingBox(),item.getBoundingBox())){
            flight.hover();ChopperKeys.holdStill(c);return true;
        }
        if(targetPosition!=null&&targetPosition.distanceToSqr(item.position())>1){
            resetRoute();blocked=false;
        }
        if(blocked){flight.hover();ChopperKeys.holdStill(c);return false;}
        if(search==null&&route.isEmpty())plan(c,item);
        if(blocked){flight.hover();ChopperKeys.holdStill(c);return false;}
        if(search!=null){
            flight.hover();ChopperKeys.holdStill(c);
            var policy=navigation.policy();
            var result=search.advance(policy.sliceNodes(),System.nanoTime()+policy.sliceNanos());
            if(result==null)return true;
            search=null;route=result.nodes();node=0;previous=p.position();stalled=0;
            if(route.isEmpty()){blocked=true;log(c,"loot-flight-no-path uuid="+target);return false;}
            log(c,"loot-flight-route uuid="+target+" nodes="+route.size()+" expanded="+result.expanded());
        }
        while(node<route.size()&&p.position().distanceToSqr(feet(route.get(node)))<.0121)node++;
        if(node>=route.size())return replan(c,"pickup-body-not-reached");
        if(previous==null||p.position().distanceToSqr(previous)>.0025){previous=p.position();stalled=0;}
        else if(++stalled>=30)return replan(c,"no-actual-movement");
        var destination=feet(route.get(node));
        var input=BorerFlyPath.input(p.position(),destination,p.getYRot());
        var swept=stepSweep(p.getBoundingBox(),input.delta());
        if(!clear(c,route.get(node))||!safeBody(c,swept))return replan(c,"actual-body-collision");
        ChopperKeys.releaseWalk(c);
        flight.speed(input.speed());
        RotationAim.apply(p,input.yaw(),0);
        c.options.keyUp.setDown(input.forward());
        c.options.keyJump.setDown(input.up());
        c.options.keyShift.setDown(input.down());
        return true;
    }
    private void plan(Minecraft c,ItemEntity item){
        navigation=KitClient.borer().buildNavigation();
        var origin=c.player.blockPosition();var destination=item.blockPosition();
        low=new BlockPos(Math.min(origin.getX(),destination.getX())-6,Math.max(-64,Math.min(origin.getY(),destination.getY())-6),Math.min(origin.getZ(),destination.getZ())-6);
        high=new BlockPos(Math.max(origin.getX(),destination.getX())+6,Math.min(316,Math.max(origin.getY(),destination.getY())+6),Math.max(origin.getZ(),destination.getZ())+6);
        if(Math.abs(origin.getX()-destination.getX())>32||Math.abs(origin.getY()-destination.getY())>32||Math.abs(origin.getZ()-destination.getZ())>32){blocked=true;return;}
        BlockPos start=null;double best=Double.POSITIVE_INFINITY;
        for(var q:BlockPos.betweenClosed(origin.offset(-1,-1,-1),origin.offset(1,1,1))){
            double distance=feet(q).distanceToSqr(c.player.position());
            if(distance<best&&clear(c,q)&&safeBody(c,c.player.getBoundingBox().expandTowards(feet(q).subtract(c.player.position())))){
                start=q.immutable();best=distance;
            }
        }
        var goals=new ArrayList<BlockPos>();
        for(var q:BlockPos.betweenClosed(destination.offset(-2,-2,-2),destination.offset(2,2,2)))
            if(clear(c,q)&&pickupIntersects(body(feet(q)),item.getBoundingBox()))goals.add(q.immutable());
        if(start==null||goals.isEmpty()){blocked=true;return;}
        targetPosition=item.position();
        search=navigation.search(new BuildNavigation.World(){
            public boolean clear(BlockPos q){return ChopperLootFlight.this.clear(c,q);}
            public boolean edge(BlockPos from,BlockPos to){return adjacentEdge(from,to)&&safeBody(c,body(feet(from)).expandTowards(feet(to).subtract(feet(from))));}
        },start,goals);
    }
    private boolean replan(Minecraft c,String reason){
        flight.hover();ChopperKeys.holdStill(c);
        resetRoute();
        if(++replans>2){blocked=true;log(c,"loot-flight-blocked reason="+reason);return false;}
        log(c,"loot-flight-replan attempt="+replans+" reason="+reason);return true;
    }
    private boolean clear(Minecraft c,BlockPos p){
        return low!=null&&p.getX()>=low.getX()&&p.getX()<=high.getX()&&p.getY()>=low.getY()&&p.getY()<=high.getY()
            &&p.getZ()>=low.getZ()&&p.getZ()<=high.getZ()&&safeBody(c,body(feet(p)));
    }
    private boolean safeBody(Minecraft c,AABB box){
        if(c.player==null||c.level==null||!c.level.noCollision(c.player,box)||!safeCells(c,box))return false;
        return c.level.getEntities(c.player,box).stream().noneMatch(e->!(e instanceof ItemEntity)&&e.isAlive()&&e.getBoundingBox().intersects(box));
    }
    private boolean safeCells(Minecraft c,AABB box){
        for(var p:BlockPos.betweenClosed(BlockPos.containing(box.minX,box.minY,box.minZ),BlockPos.containing(box.maxX-1e-7,box.maxY-1e-7,box.maxZ-1e-7))){
            var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,net.minecraft.world.level.chunk.status.ChunkStatus.FULL,false);
            if(p.getY()<-64||p.getY()>319||!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))return false;
            var state=c.level.getBlockState(p);
            if(!state.getFluidState().isEmpty()||state.is(Blocks.FIRE)||state.is(Blocks.SOUL_FIRE)||state.is(Blocks.COBWEB)||state.is(Blocks.POWDER_SNOW))return false;
        }
        return true;
    }
    private boolean recoverThinFloorOverlap(Minecraft c){
        var p=c.player;var box=p.getBoundingBox();
        if(liftAttempts>=2||!safeCells(c,box))return false;
        var collisions=new ArrayList<AABB>();
        for(var shape:c.level.getBlockCollisions(p,box))if(!shape.isEmpty())collisions.addAll(shape.toAabbs());
        if(!thinFloorOverlap(box,collisions))return false;
        for(double lift:new double[]{.08,.12,.16,.20})if(safeBody(c,box.move(0,lift,0))){
            resetRoute();liftAttempts++;ChopperKeys.holdStill(c);flight.speed(lift/5);
            c.options.keyJump.setDown(true);log(c,"loot-flight-floor-lift height="+lift);return true;
        }
        return false;
    }
    void resetRoute(){search=null;route=List.of();node=0;previous=null;stalled=0;targetPosition=null;blocked=false;}
    void pause(Minecraft c){if(acquired)flight.hover();ChopperKeys.releaseWalk(c);}
    void close(Minecraft c){
        if(acquired){
            ChopperKeys.holdStill(c);
            if(!originallyFlying&&safeSmallLanding(c)){flight.digOnFoot();flight.close();}
            else if(c.player!=null&&!c.player.onGround())flight.closeKeepingFlight();else flight.close();
        }
        acquired=false;resetRoute();target=null;world=null;
    }
    private boolean safeSmallLanding(Minecraft c){
        if(c.player==null||c.level==null)return false;
        var p=c.player;if(p.onGround())return true;
        var cell=p.blockPosition().below();
        var state=c.level.getBlockState(cell);var shape=state.getCollisionShape(c.level,cell);
        if(shape.isEmpty()||!state.getFluidState().isEmpty()||state.is(Blocks.MAGMA_BLOCK)||state.is(Blocks.CACTUS))return false;
        double floor=cell.getY()+shape.max(net.minecraft.core.Direction.Axis.Y),gap=p.getY()-floor;
        return gap>=0&&gap<=.35&&safeBody(c,p.getBoundingBox().move(0,-gap,0));
    }
    static boolean pickupIntersects(AABB player,AABB item){return player.inflate(1,.5,1).deflate(.15).intersects(item);}
    static boolean thinFloorOverlap(AABB body,List<AABB> collisions){
        return !collisions.isEmpty()&&collisions.stream().allMatch(box->box.maxY<=body.minY+.08&&box.minY<body.minY);
    }
    static Vec3 feet(BlockPos p){return BorerFlyPath.waypoint(p);}
    static boolean adjacentEdge(BlockPos from,BlockPos to){return from.distManhattan(to)==1;}
    // A player legitimately touching a floor must not acquire an invented
    // overlap below their feet. Retain the full actual vertical movement.
    static AABB stepSweep(AABB actualBody,Vec3 delta){
        return actualBody.expandTowards(delta).inflate(.005,0,.005);
    }
    private static AABB body(Vec3 p){return new AABB(p.x-.31,p.y+.01,p.z-.31,p.x+.31,p.y+1.81,p.z+.31);}
    private static void log(Minecraft c,String message){ChopperFileLog.append(c,AutoChopper.VERSION,message);}
}
