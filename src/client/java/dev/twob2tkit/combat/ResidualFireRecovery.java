package dev.twob2tkit.combat;

import com.google.gson.JsonObject;
import dev.twob2tkit.KitKeys;
import dev.twob2tkit.MeteorModules;
import dev.twob2tkit.automation.AutomationBridge;
import dev.twob2tkit.runtime.engine.BorerThreats;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.component.DataComponents;
import net.minecraft.world.damagesource.DamageTypes;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.CampfireBlock;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;

/** Client-thread observation only. Never changes health, damage sources or safety holds. */
public final class ResidualFireRecovery {
    private static final ResidualFireWaitPolicy.Window window=new ResidualFireWaitPolicy.Window();
    private static Object world,player,connection;
    private static float previous=Float.NaN,lastHealth;
    private static long mobHitAt=-1;
    private static boolean burning,suspensionDisabled;
    private ResidualFireRecovery(){}
    public static boolean active(){return window.active();}
    public static boolean burning(){return active()&&burning;}
    public static void cancel(){window.reset();}
    public static void suspensionUnavailable(){suspensionDisabled=true;cancel();}
    public static String status(){return burning()?"安全高处等待余火熄灭":active()?"余火已灭，进食恢复后继续":"";}
    public static JsonObject snapshot(){
        var j=new JsonObject();j.addProperty("protocol",1);j.addProperty("active",active());
        j.addProperty("phase",burning()?"waiting_for_fire":active()?"recovering":"idle");
        j.addProperty("started_at",window.started());j.addProperty("maximum_wait_ms",20000);
        j.addProperty("context_supported",!suspensionDisabled);
        j.addProperty("health",lastHealth);return j;
    }
    public static boolean observe(Minecraft c,boolean automated,long now){
        if(c.player==null||c.level==null||c.getConnection()==null){cancel();world=player=connection=null;previous=Float.NaN;mobHitAt=-1;return false;}
        if(world!=c.level||player!=c.player||connection!=c.getConnection()){
            cancel();suspensionDisabled=false;world=c.level;player=c.player;connection=c.getConnection();previous=Float.NaN;mobHitAt=-1;
        }
        var p=c.player;var source=p.getLastDamageSource();lastHealth=p.getHealth();
        if(Float.isFinite(previous)&&lastHealth<previous-.05f&&source!=null&&!BorerThreats.isEnvironmental(source)
                &&source.getEntity() instanceof Enemy)mobHitAt=now;
        previous=lastHealth;burning=p.isOnFire();
        boolean known=mobHitAt>=0&&now>=mobHitAt&&now-mobHitAt<=5000;
        boolean owned=automated&&!suspensionDisabled&&AutomationBridge.guardArmed()&&AutomationBridge.pveOnly()
            &&dev.twob2tkit.KitClient.borer()!=null&&!dev.twob2tkit.KitClient.borer().isActive()
            &&!p.isDeadOrDying()&&c.gui.screen()==null&&!KitKeys.manualMovementDown(c)
            &&MeteorModules.isActive(MeteorModules.FLIGHT);
        boolean safe=owned&&bodySafe(c);
        boolean wasActive=active();
        boolean result=window.observe(now,new ResidualFireWaitPolicy.Sample(owned,safe,safe&&threatsClear(c),
            burning,source!=null&&source.is(DamageTypes.ON_FIRE),known,
            !p.isUsingItem()||!p.getUseItem().has(DataComponents.FOOD),lastHealth,p.getMaxHealth(),p.getFoodData().getFoodLevel()));
        if(result&&!wasActive)dev.twob2tkit.KitClient.LOGGER.info("[Protection] safe residual fire wait started; no health hold cleared");
        return result;
    }
    private static boolean bodySafe(Minecraft c){
        var p=c.player;
        if(p.isInWater()||p.isUnderWater()||p.isInLava()||!c.level.noCollision(p,p.getBoundingBox()))return false;
        var box=p.getBoundingBox().inflate(.4);
        for(var q:BlockPos.betweenClosed(BlockPos.containing(box.minX,box.minY,box.minZ),BlockPos.containing(box.maxX,box.maxY,box.maxZ))){
            var chunk=c.level.getChunkSource().getChunk(q.getX()>>4,q.getZ()>>4,ChunkStatus.FULL,false);
            if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))return false;
            var s=c.level.getBlockState(q);
            if(!s.getFluidState().isEmpty()||s.is(Blocks.FIRE)||s.is(Blocks.SOUL_FIRE)||s.is(Blocks.MAGMA_BLOCK)
                    ||s.is(Blocks.CACTUS)||s.is(Blocks.POWDER_SNOW)||s.is(Blocks.SWEET_BERRY_BUSH)||s.is(Blocks.COBWEB)
                    ||s.getBlock() instanceof CampfireBlock&&s.getValue(CampfireBlock.LIT))return false;
        }
        return true;
    }
    private static double gap(double a,double b,double c,double d){return Math.max(0,Math.max(a-d,c-b));}
    private static double distanceSquared(AABB a,AABB b){
        double x=gap(a.minX,a.maxX,b.minX,b.maxX),y=gap(a.minY,a.maxY,b.minY,b.maxY),z=gap(a.minZ,a.maxZ,b.minZ,b.maxZ);
        return x*x+y*y+z*z;
    }
    private static boolean threatsClear(Minecraft c){
        var p=c.player;
        for(var e:c.level.getEntities(p,p.getBoundingBox().inflate(64),e->e.isAlive())){
            if(e instanceof Enemy&&e instanceof LivingEntity living){
                double radius=e instanceof net.minecraft.world.entity.monster.Creeper?8:6;
                if(distanceSquared(p.getBoundingBox(),e.getBoundingBox())<radius*radius)return false;
                String type=net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();
                if(BorerThreats.isRangedCombatThreat(e)&&p.distanceTo(e)<=ResidualFireWaitPolicy.rangedRadius(type)
                        &&p.hasLineOfSight(e))return false;
                if(living instanceof net.minecraft.world.entity.monster.EnderMan&&p.hasLineOfSight(e)){
                    var delta=living.getEyePosition().subtract(p.getEyePosition());double d=delta.length();
                    if(d>0&&p.getViewVector(1).normalize().dot(delta.normalize())>1-.025/d)return false;
                }
            }
            if(e instanceof Projectile projectile&&projectile.getOwner()!=p&&p.distanceTo(e)<24){
                var v=e.getDeltaMovement();
                if(v.lengthSqr()>.0001&&p.getEyePosition().subtract(e.position()).dot(v)>0)return false;
            }
        }
        return true;
    }
}
