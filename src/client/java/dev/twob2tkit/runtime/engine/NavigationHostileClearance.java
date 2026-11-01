package dev.twob2tkit.runtime.engine;

import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.monster.EnderMan;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.*;

/** Read-only construction clearance around currently loaded threats. Never fights or unlocks. */
final class NavigationHostileClearance {
    enum Kind { CREEPER, CHARGED_CREEPER, RANGED, MELEE }
    record Threat(Kind kind,AABB box,Vec3 eye,boolean current) {}
    @FunctionalInterface interface Visibility { boolean clear(Vec3 from,Vec3 to); }
    private static final Set<String> RANGED=Set.of("minecraft:skeleton","minecraft:stray","minecraft:bogged",
        "minecraft:pillager","minecraft:witch","minecraft:drowned","minecraft:blaze","minecraft:ghast",
        "minecraft:shulker","minecraft:evoker","minecraft:illusioner");
    private static Object cachedLevel,cachedConnection;
    private static int cachedTick=Integer.MIN_VALUE;
    private static List<Threat> cached=List.of();
    private static boolean valid;
    private static final Map<BlockPos,Boolean> grid=new HashMap<>();
    private NavigationHostileClearance() {}

    static boolean permit(Kind kind,boolean current,double distanceSquared,boolean attackVisible) {
        if(!current||kind==null||!Double.isFinite(distanceSquared)||distanceSquared<0)return false;
        return switch(kind) {
            case CREEPER -> distanceSquared>64;
            case CHARGED_CREEPER -> distanceSquared>144;
            case RANGED -> distanceSquared>400||!attackVisible;
            case MELEE -> distanceSquared>9||!attackVisible;
        };
    }
    static double distanceSquared(AABB a,AABB b) {
        double x=Math.max(0,Math.max(a.minX-b.maxX,b.minX-a.maxX));
        double y=Math.max(0,Math.max(a.minY-b.maxY,b.minY-a.maxY));
        double z=Math.max(0,Math.max(a.minZ-b.maxZ,b.minZ-a.maxZ));
        return x*x+y*y+z*z;
    }
    static boolean safe(AABB body,List<Threat> threats,Visibility visibility) {
        for(var threat:threats) {
            double distance=distanceSquared(body,threat.box());
            if(distance>24*24)continue;
            boolean visible=false;
            if(threat.kind()==Kind.RANGED&&distance<=400||threat.kind()==Kind.MELEE&&distance<=9) {
                double x=(body.minX+body.maxX)*.5,z=(body.minZ+body.maxZ)*.5;
                // A wall hiding the eyes alone does not protect exposed legs or torso.
                for(double h:new double[]{.1,.9,1.62})
                    if(visibility.clear(threat.eye(),new Vec3(x,body.minY+h,z))){visible=true;break;}
            }
            if(!permit(threat.kind(),threat.current(),distance,visible))return false;
        }
        return true;
    }
    private static void refresh(Minecraft c) {
        if(c.level==cachedLevel&&c.getConnection()==cachedConnection&&c.player.tickCount==cachedTick)return;
        cachedLevel=c.level;cachedConnection=c.getConnection();cachedTick=c.player.tickCount;grid.clear();
        var list=new ArrayList<Threat>();valid=true;
        for(var e:c.level.entitiesForRendering()) {
            if(!(e instanceof Enemy)||!e.isAlive()||e instanceof EnderMan a&&!a.isCreepy())continue;
            if(list.size()>=256){valid=false;break;}
            var p=e.blockPosition();var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
            boolean current=e.level()==c.level&&c.level.getEntity(e.getId())==e&&LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
            Kind kind=e instanceof Creeper a?(a.isPowered()?Kind.CHARGED_CREEPER:Kind.CREEPER)
                :RANGED.contains(BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString())?Kind.RANGED:Kind.MELEE;
            list.add(new Threat(kind,e.getBoundingBox(),e.getEyePosition(),current));
        }
        cached=List.copyOf(list);
    }
    private static boolean bodySafe(Minecraft c,AABB body) {
        refresh(c);if(!valid)return false;
        return safe(body,cached,(from,to)->c.level.clip(new ClipContext(from,to,ClipContext.Block.COLLIDER,
            ClipContext.Fluid.NONE,c.player)).getType()==HitResult.Type.MISS);
    }
    static boolean current(BlockPos feet) {
        var c=Minecraft.getInstance();if(c==null)return true; // Pure World fixtures.
        if(c.level==null||c.player==null)return false;refresh(c);
        return grid.computeIfAbsent(feet.immutable(),p->bodySafe(c,new AABB(p.getX()+.2,p.getY()+.02,p.getZ()+.2,
            p.getX()+.8,p.getY()+1.82,p.getZ()+.8)));
    }
    static boolean currentStep(Vec3 probe) {
        var c=Minecraft.getInstance();if(c==null)return true;
        if(c.level==null||c.player==null)return false;
        var body=c.player.getBoundingBox();
        return bodySafe(c,body.expandTowards(probe))&&bodySafe(c,body.move(probe));
    }
}
