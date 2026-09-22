package dev.twob2tkit.combat;

import com.google.gson.*;
import dev.twob2tkit.*;
import dev.twob2tkit.automation.AutomationBridge;
import dev.twob2tkit.builder.BuildPath;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerAreaFlightSession;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.*;
import java.util.*;

/** Native low-health escape, independent of the remote script and its heartbeat. */
public final class EmergencyExit {
    public static final String AUTO_RECONNECT="meteordevelopment.meteorclient.systems.modules.misc.AutoReconnect";
    private static final BorerAreaFlightSession flight=new BorerAreaFlightSession();
    private static boolean escaping,memoryHold,restoreAutoLog;
    private static Object level,connection;
    private static long started,lastMoved;
    private static double startY;
    private static Vec3 lastPosition;
    private static List<BlockPos> route=List.of();
    private static int index;
    private static String reason="";
    private static SafetyHoldStore cachedStore;
    private static RotationAim.Look escapeLook;
    private static SafetyHoldStore store(Minecraft c){if(cachedStore==null)cachedStore=new SafetyHoldStore(c.gameDirectory.toPath().resolve("config/twob2tkit/automation/safety-hold.json"));return cachedStore;}
    public static boolean held(Minecraft c){return memoryHold||store(c).active();}
    public static boolean active(){return escaping;}
    public static JsonObject snapshot(Minecraft c){var stored=store(c).read();var j=new JsonObject();
        for(String key:List.of("reason","time","health","escape_result","rise"))if(stored.has(key))j.add(key,stored.get(key));
        j.addProperty("active",held(c));j.addProperty("escaping",escaping);j.addProperty("detail",reason);return j;}
    public static void joined(Minecraft c){if(held(c))MeteorModules.disable(AUTO_RECONNECT);}
    public static void acknowledge(Minecraft c){
        // Only the in-game button calls this. No bridge command can clear the lock.
        if(c.player==null||c.player.isDeadOrDying()||c.player.getHealth()<18||escaping)return;
        try{store(c).clearByUser();memoryHold=false;c.player.sendSystemMessage(net.minecraft.network.chat.Component.literal("[保护] 已手动解除离线锁；请自行启动需要的功能。"));}
        catch(Exception e){memoryHold=true;}
    }
    public static void begin(Minecraft c,String why){
        if(escaping||c.player==null||c.level==null)return;
        memoryHold=true;reason=why;
        var j=new JsonObject();j.addProperty("active",true);j.addProperty("reason",why);j.addProperty("time",System.currentTimeMillis());j.addProperty("health",c.player.getHealth());
        j.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);j.addProperty("dimension",c.level.dimension().identifier().toString());j.addProperty("player",c.player.getUUID().toString());
        j.add("pos",new Gson().toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));
        var inventory=new JsonArray();
        for(int slot=0;slot<c.player.getInventory().getContainerSize();slot++){
            var stack=c.player.getInventory().getItem(slot);if(stack.isEmpty())continue;
            var entry=new JsonObject();entry.addProperty("slot",slot);entry.addProperty("item",net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(stack.getItem()).toString());entry.addProperty("count",stack.getCount());
            if(stack.isDamageableItem())entry.addProperty("durability",stack.getMaxDamage()-stack.getDamageValue());inventory.add(entry);
        }
        j.add("inventory_checkpoint",inventory);
        try{store(c).write(j);}catch(Exception e){KitClient.LOGGER.error("Cannot persist low-health lock",e);}
        KitClient.emergencyStop("血量不足，停止工作并撤离");
        if(c.player.containerMenu!=c.player.inventoryMenu)c.player.closeContainer();
        else if(c.screen!=null)c.setScreen(null);
        level=c.level;connection=c.getConnection();startY=c.player.getY();started=lastMoved=System.currentTimeMillis();lastPosition=c.player.position();index=0;escaping=true;
        try{
            MeteorModules.disable(AUTO_RECONNECT);restoreAutoLog=MeteorModules.disable(MeteorModules.AUTO_LOG);
            GuardFoodLease.acquire(c);MeteorModules.enablePveAura();MeteorModules.enable("meteordevelopment.meteorclient.systems.modules.player.AutoEat");
            if(c.player.getHealth()<=6){finish(c,"血量危急，不等待起飞");return;}
            flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/emergency-flight.bak"));
            if(flight.acquire(c.player)!=null){finish(c,"无法启飞");return;}
            route=findRoute(c);
            if(route.isEmpty()){finish(c,"没有可通行的上升路线");return;}
            c.player.sendSystemMessage(net.minecraft.network.chat.Component.literal("[保护] 血量不足：先升高撤离，再离线锁定，等你手动回来。"));
        }catch(Exception e){finish(c,"飞行不可用");}
    }
    public static void observeHealth(Minecraft c){
        if(!held(c)&&!escaping&&c.player!=null&&c.level!=null&&c.player.getHealth()<14
            &&(AutomationBridge.guardArmed()||KitClient.anyAfkAuto()))begin(c,"低血量紧急撤离");
    }
    public static boolean tick(Minecraft c){
        if(held(c))MeteorModules.disable(AUTO_RECONNECT);
        if(!escaping){
            if(held(c)){if(AutomationBridge.guardArmed()||KitClient.anyAfkAuto())KitClient.emergencyStop("安全锁未解除，等待手动确认");return true;}
            observeHealth(c);
            return escaping;
        }
        if(c.level!=level||c.getConnection()!=connection||c.player==null){cancel(c);return false;}
        if(KitKeys.manualMovementDown(c)||c.screen!=null){cancel(c);KitKeys.restorePhysicalMovement(c);return true;}
        MeteorModules.disable(AUTO_RECONNECT);MeteorModules.disable(MeteorModules.AUTO_LOG);
        long now=System.currentTimeMillis();double rise=c.player.getY()-startY;
        if(EmergencyExitPolicy.decide(c.player.getHealth(),rise,now-started,index<route.size())==EmergencyExitPolicy.Decision.DISCONNECT){finish(c,rise>=11.7?"已升高约 12 格":c.player.getHealth()<=6?"血量危急，不再等待升高":"撤离时间已到");return true;}
        if(c.player.position().distanceToSqr(lastPosition)>.01){lastMoved=now;lastPosition=c.player.position();}
        if(now-lastMoved>1000){finish(c,"持续没有实际位移");return true;}
        try{
            Vec3 delta=feet(route.get(index)).subtract(c.player.position());
            release(c);escapeLook=null;
            if(Math.abs(delta.y)<.12&&Math.hypot(delta.x,delta.z)<.15){index++;flight.hover();return true;}
            boolean vertical=Math.abs(delta.y)>.12;
            Vec3 probe=vertical?new Vec3(0,Math.copySign(.6,delta.y),0):new Vec3(delta.x,0,delta.z).normalize().scale(.6);
            if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(probe))||!clear(c,route.get(index))||!awayFromThreats(c,c.player.position(),feet(route.get(index)))){finish(c,"撤离通道出现障碍");return true;}
            if(vertical){flight.speed(Math.abs(delta.y)>.3?.04:.006);c.options.keyJump.setDown(delta.y>0);c.options.keyShift.setDown(delta.y<0);}
            else{escapeLook=new RotationAim.Look(RotationAim.yawToward(delta.x,delta.z),0);RotationAim.apply(c.player,escapeLook);flight.speed(Math.hypot(delta.x,delta.z)>.3?.024:.004);c.options.keyUp.setDown(true);}
        }catch(Exception e){finish(c,"飞行状态变化");}
        return true;
    }
    private static List<BlockPos> findRoute(Minecraft c){
        BlockPos origin=c.player.blockPosition();var cache=new HashMap<BlockPos,Boolean>();BlockPos start=null;double best=Double.POSITIVE_INFINITY;
        for(var p:BlockPos.betweenClosed(origin.offset(-1,0,-1),origin.offset(1,1,1))){var q=p.immutable();Vec3 d=feet(q).subtract(c.player.position());
            if(clear(c,q)&&c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(d))&&d.lengthSqr()<best){best=d.lengthSqr();start=q;}}
        if(start==null)return List.of();int y=(int)Math.ceil(startY+12);
        return BuildPath.find(new BuildPath.World(){public boolean clear(BlockPos p){return Math.abs(p.getX()-origin.getX())<=8&&Math.abs(p.getZ()-origin.getZ())<=8&&p.getY()>=origin.getY()&&p.getY()<=y&&cache.computeIfAbsent(p,q->EmergencyExit.clear(c,q));}
            public boolean edge(BlockPos a,BlockPos b){return b.getY()>=a.getY()&&awayFromThreats(c,feet(a),feet(b))&&c.level.noCollision(c.player,body(feet(a)).expandTowards(feet(b).subtract(feet(a))));}},start,p->p.getY()==y,6000).nodes();
    }
    private static boolean awayFromThreats(Minecraft c,Vec3 from,Vec3 to){
        for(var e:c.level.getEntities(c.player,body(to).inflate(8))){
            if(!(e instanceof net.minecraft.world.entity.monster.Enemy)||!e.isAlive())continue;
            double radius=e instanceof net.minecraft.world.entity.monster.Creeper?6:3.5;
            if(!EmergencyExitPolicy.safeStep(from.x,from.y,from.z,to.x,to.y,to.z,e.getX(),e.getY(),e.getZ(),radius))return false;
        }
        return true;
    }
    private static boolean clear(Minecraft c,BlockPos p){
        for(int i=0;i<2;i++){var q=p.above(i);if(!c.level.hasChunkAt(q))return false;var s=c.level.getBlockState(q);if(!s.getFluidState().isEmpty()||s.is(Blocks.FIRE)||s.is(Blocks.SOUL_FIRE)||s.is(Blocks.COBWEB)||s.is(Blocks.POWDER_SNOW))return false;}
        return c.level.noCollision(c.player,body(feet(p)));
    }
    private static Vec3 feet(BlockPos p){return new Vec3(p.getX()+.5,p.getY(),p.getZ()+.5);}
    private static AABB body(Vec3 p){return new AABB(p.x-.31,p.y+.01,p.z-.31,p.x+.31,p.y+1.8,p.z+.31);}
    private static void release(Minecraft c){if(c.options==null)return;c.options.keyUp.setDown(false);c.options.keyDown.setDown(false);c.options.keyLeft.setDown(false);c.options.keyRight.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);}
    private static void finish(Minecraft c,String outcome){
        reason=outcome+"；已锁定自动重连，等待手动确认";
        var j=store(c).read();j.addProperty("active",true);j.addProperty("escape_result",outcome);j.addProperty("rise",c.player==null?0:c.player.getY()-startY);
        if(c.player!=null){j.addProperty("last_observed_health",c.player.getHealth());j.add("last_observed_pos",new Gson().toJsonTree(new double[]{c.player.getX(),c.player.getY(),c.player.getZ()}));}
        try{store(c).write(j);}catch(Exception e){KitClient.LOGGER.error("Cannot persist escape outcome",e);}
        cancel(c);KitClient.controller().requestLogout(reason);
    }
    public static boolean reapply(Minecraft c){if(!escaping)return false;if(escapeLook!=null&&c.player!=null)RotationAim.apply(c.player,escapeLook);return true;}
    public static void cancel(Minecraft c){
        if(!escaping)return;escaping=false;escapeLook=null;GuardFoodLease.release();release(c);flight.closeKeepingFlight();route=List.of();
        if(restoreAutoLog)MeteorModules.enable(MeteorModules.AUTO_LOG);restoreAutoLog=false;
    }
    private EmergencyExit(){}
}
