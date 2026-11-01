package dev.twob2tkit.runtime.engine;

import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.ai.attributes.Attributes;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.effect.MobEffects;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;

/** Yield only movement avoidance for current, calm, physically enclosed ground mobs. */
final class BorerEnclosedThreats {
    private static final Set<String> GROUND_MOBS=Set.of("minecraft:creeper","minecraft:zombie","minecraft:zombie_villager",
        "minecraft:husk","minecraft:drowned","minecraft:skeleton","minecraft:stray","minecraft:bogged");
    private static final BorerMiningConfirmation PREDICTIONS=new BorerMiningConfirmation();
    private static EnclosedHostileGeometry.Box box(AABB a){return new EnclosedHostileGeometry.Box(a.minX,a.minY,a.minZ,a.maxX,a.maxY,a.maxZ);}
    private static boolean loaded(Minecraft c,BlockPos p){return !c.level.isOutsideBuildHeight(p)
        &&LoadedServerChunkEvidence.isServerChunk(c.level,c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false))
        &&!PREDICTIONS.pending(c.level,p);}
    static boolean permits(Minecraft c,Collection<LivingEntity> targets){
        try{return proven(c,targets);}catch(RuntimeException unreadable){return false;}
    }
    private static boolean proven(Minecraft c,Collection<LivingEntity> targets){
        if(c.player==null||c.level==null||targets.isEmpty()||c.gui.screen()!=null||!(c.player.getHealth()>=19)
            ||c.player.getFoodData().getFoodLevel()<8||c.player.isUnderWater()||c.player.isOnFire()
            ||!c.level.noBlockCollision(c.player,c.player.getBoundingBox(),true))return false;
        if(!c.level.getEntities(c.player,c.player.getBoundingBox().inflate(12),e->e instanceof Projectile&&e.isAlive()).isEmpty())return false;
        if(c.player.getLastHurtByMob()!=null&&c.player.tickCount-c.player.getLastHurtByMobTimestamp()<100)return false;
        var all=new LinkedHashSet<LivingEntity>(targets);boolean creeper=false;
        for(var mob:all){
            if(c.level.getEntity(mob.getId())!=mob||mob.level()!=c.level||!mob.isAlive()||mob.isDeadOrDying()
                ||!GROUND_MOBS.contains(BuiltInRegistries.ENTITY_TYPE.getKey(mob.getType()).toString())
                ||c.player.hasLineOfSight(mob)||BorerThreats.currentReceivedMobHit(mob,c.player)
                ||mob.getDeltaMovement().y>.430001||mob.noPhysics||mob.isNoGravity()||mob.hasEffect(MobEffects.JUMP_BOOST)||mob.hasEffect(MobEffects.LEVITATION)
                ||!EnclosedHostileGeometry.ordinaryMovement(mob.getAttributeValue(Attributes.JUMP_STRENGTH),
                    mob.getAttributeValue(Attributes.STEP_HEIGHT),mob.getAttributeValue(Attributes.GRAVITY)))return false;
            if(mob instanceof Creeper a){
                if(a.isPowered()||a.isIgnited()||a.getSwellDir()>0||a.getSwelling(1)>0)return false;
                creeper=true;
            }
            var world=new EnclosedHostileGeometry.World(){
                public boolean wall(int x,int y,int z){var p=new BlockPos(x,y,z);if(!loaded(c,p))return false;
                    var s=c.level.getBlockState(p);return s.getFluidState().isEmpty()&&c.level.getBlockEntity(p)==null&&s.isCollisionShapeFullBlock(c.level,p);}
                public boolean floor(int x,int z,double feet){var p=new BlockPos(x,(int)Math.floor(feet-1e-5),z);if(!loaded(c,p))return false;
                    var s=c.level.getBlockState(p);if(!s.getFluidState().isEmpty()||c.level.getBlockEntity(p)!=null
                        ||s.is(Blocks.MAGMA_BLOCK)||s.is(Blocks.SLIME_BLOCK)||s.is(Blocks.HONEY_BLOCK))return false;
                    double top=s.isCollisionShapeFullBlock(c.level,p)?p.getY()+1:
                        s.getBlock()instanceof SlabBlock&&s.getValue(SlabBlock.TYPE)==SlabType.BOTTOM?p.getY()+.5:Double.NaN;
                    return Double.isFinite(top)&&Math.abs(top-feet)<.0001;}
                public boolean clear(int x,int z,int w,int d,double feet,double top){
                    for(var p:BlockPos.betweenClosed(x,(int)Math.floor(feet),z,x+w-1,(int)Math.ceil(top),z+d-1))
                        if(!loaded(c,p)||!c.level.getBlockState(p).getFluidState().isEmpty())return false;
                    return c.level.noBlockCollision(null,new AABB(x,feet+.0001,z,x+w,top,z+d),true);
                }
            };
            if(!EnclosedHostileGeometry.sealed(world,box(mob.getBoundingBox()),box(c.player.getBoundingBox())))return false;
        }
        return creeper;
    }
}
