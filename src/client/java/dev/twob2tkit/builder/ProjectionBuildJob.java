package dev.twob2tkit.builder;

import com.google.gson.JsonObject;
import dev.twob2tkit.*;
import dev.twob2tkit.automation.ProfessionalPrinter;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerAreaFlightSession;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.*;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.item.*;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.*;
import java.util.*;

/** GUI-owned scan / travel / print / verify loop. Placement is exclusively Litematica Printer. */
public final class ProjectionBuildJob {
    private final KitConfig config;
    private final BuildDeparturePolicy departure=new BuildDeparturePolicy();
    private int lastDepartureIdleTicks=-1;
    private boolean lastDepartureEarly;
    private final BorerAreaFlightSession flight=new BorerAreaFlightSession();
    private boolean active,autoMove,loading;
    private ClientLevel level;
    private LitematicaAccess.BuildSelection selection;
    private final Map<BlockPos,BlockState> expected=new LinkedHashMap<>(),actual=new HashMap<>();
    private final Map<BlockPos,Integer> blocked=new HashMap<>();
    private Iterator<BlockPos> iterator;
    private List<BlockPos> path=List.of();
    private BlockPos station;
    private int pathIndex,tick,matched,total,initial,blockedBlocks,printSince,lastGain,lastMatched,stall,scanSince;
    private double bestDistance=Double.POSITIVE_INFINITY;
    private String phase="未开始",reason="",missing="",name="";
    private RotationAim.Look look;
    public ProjectionBuildJob(KitConfig config){this.config=config;}
    public boolean isActive(){return active;}
    public String status(){return phase+(reason.isBlank()?"":"："+reason);}
    public String progress(){return total==0?"开始后读取图纸与现场":"已匹配 "+matched+" / "+total+" 格 · 本次新增 "+Math.max(0,matched-initial)+" 格";}
    public String missing(){return missing.isBlank()?"当前材料检查未发现缺口":missing;}
    public JsonObject snapshot(){var j=new JsonObject();j.addProperty("active",active);j.addProperty("phase",phase);j.addProperty("reason",reason);j.addProperty("matched",matched);j.addProperty("total",total);j.addProperty("new_blocks",Math.max(0,matched-initial));j.addProperty("missing",missing);j.addProperty("blocked_blocks",blockedBlocks);j.addProperty("auto_move",autoMove);j.addProperty("last_departure_idle_ticks",lastDepartureIdleTicks);j.addProperty("last_departure_early",lastDepartureEarly);j.addProperty("idle_ticks",tick-lastGain);if(station!=null)j.addProperty("station",station.toShortString());return j;}
    public boolean start(Minecraft c){
        try{
            if(c.player==null||c.level==null)return fail("请先进入世界");
            selection=LitematicaAccess.buildSelection();name=selection.name();ProfessionalPrinter.clearFailure();
            if(selection.volume()>300000)return fail("投影范围过大，请拆成较小的独立放置");
            if(c.player.position().distanceTo(Vec3.atCenterOf(selection.min()))>150)return fail("请先走近选中的投影");
            var printer=ProfessionalPrinter.status();
            if(!printer.has("rotate") || !printer.get("rotate").getAsBoolean() || printer.get("in_air").getAsBoolean() || printer.get("air_place").getAsBoolean())return fail("打印器需开启自动朝向，关闭悬空打印及 Meteor Air Place");
            autoMove=config.projectionAutoMove;level=c.level;active=true;loading=true;tick=matched=total=initial=0;
            departure.reset();lastDepartureIdleTicks=-1;lastDepartureEarly=false;expected.clear();actual.clear();blocked.clear();path=List.of();station=null;look=null;
            iterator=BlockPos.betweenClosed(selection.min(),selection.max()).iterator();
            if(autoMove){flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/build-flight-speed.bak"));String error=flight.acquire(c.player);if(error!=null){stop(c,error);return false;}flight.hover();}
            phase="检查投影";reason=name;return true;
        }catch(Exception e){stop(c,e.getMessage());return fail(e.getMessage());}
    }
    private boolean fail(String why){phase="无法开始";reason=why==null?"读取依赖失败":why;return false;}
    public void stop(Minecraft c,String why){
        if(!active)return;
        ProfessionalPrinter.stop(c,false);release(c);look=null;
        if(autoMove){if(c.player!=null&&!c.player.onGround())flight.closeKeepingFlight();else flight.close();}
        active=false;phase="已停止";reason=why==null?"未知错误":why;path=List.of();
        if(c.player!=null)c.player.sendSystemMessage(net.minecraft.network.chat.Component.literal("[投影建造] "+reason+" · "+progress()));
    }
    public void pause(Minecraft c){
        if(!active)return;
        departure.reset();ProfessionalPrinter.pause();release(c);look=null;if(autoMove)flight.hover();
        phase="已暂停";reason=c.screen!=null?"界面已打开，关闭后继续":"等待防御或进食结束";
    }
    public void serverBlock(BlockPos pos,BlockState state){
        if(!active||Minecraft.getInstance().level!=level||!expected.containsKey(pos))return;
        var previous=actual.put(pos.immutable(),state);var wanted=expected.get(pos);
        if(wanted.equals(state)&&!wanted.equals(previous)){
            matched++;lastGain=tick;lastMatched=matched;departure.reset();
        }else if(!wanted.equals(state)&&wanted.equals(previous)){matched--;departure.reset();}
    }
    public void reapply(Minecraft c){if(active&&look!=null&&c.screen==null)RotationAim.apply(c.player,look);}
    public void tick(Minecraft c){
        if(!active)return;
        try{
            if(!ProfessionalPrinter.failure().isEmpty()){stop(c,ProfessionalPrinter.failure());return;}
            if(c.player==null||c.level!=level||c.player.isDeadOrDying()){stop(c,"离开原世界");return;}
            if(c.screen!=null){pause(c);return;}
            if(c.player.getHealth()<14){pause(c);reason="血量不足，等待恢复";return;}
            tick++;
            if(tick%20==0&&!selection.key().equals(LitematicaAccess.buildSelection().key())){stop(c,"投影位置或范围已改变，请重新检查后开始");return;}
            if(loading){load(c);return;}
            if(tick-scanSince>=20){recount(c);scanSince=tick;}
            if(matched==total){stop(c,"当前投影范围全部匹配");return;}
            if(autoMove){String e=flight.acquire(c.player);if(e!=null){stop(c,e);return;}}
            if(!path.isEmpty()){move(c);return;}
            if(ProfessionalPrinter.owned()){
                ProfessionalPrinter.resume();
                phase="打印中";reason=station==null?"当前位置":station.toShortString();
                if(matched>lastMatched){lastGain=tick;lastMatched=matched;departure.reset();}
                // Poll twice per four ticks; an authoritative gain resets the quiet period immediately.
                if(tick%2!=0)return;
                boolean settled=ProfessionalPrinter.readyForTravel();
                boolean localWork=settled&&reachable(c,c.player.position(),available(c),true)>0;
                boolean completed=departure.observe(tick,settled,localWork);
                if(!completed&&(tick-lastGain<BuildDeparturePolicy.RETRY_TICKS||!ProfessionalPrinter.queueIdleForTravel()))return;
                lastDepartureIdleTicks=tick-lastGain;lastDepartureEarly=completed;
                KitClient.LOGGER.info("[Build] station-complete idle_ticks={} confirmed_local_completion={} station={}",lastDepartureIdleTicks,completed,station);
                ProfessionalPrinter.stop(c,false);look=null;recount(c);
                if(!autoMove){stop(c,"附近暂时没有可放方块；移动到下一处后继续");return;}
                if(station!=null)blocked.put(station,tick+600);
                station=null;
            }
            if(!autoMove || blocked.getOrDefault(c.player.blockPosition(),0)<=tick && reachable(c,c.player.position(),available(c),true)>0){beginPrinting(c);return;}
            plan(c);
        }catch(Exception e){stop(c,e.getMessage());}
    }
    private void load(Minecraft c){
        var world=LitematicaAccess.schematicWorld();if(world==null)throw new IllegalStateException("投影世界不可用");
        for(int n=0;n<2048&&iterator.hasNext();n++){
            var p=iterator.next().immutable();if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p))continue;
            if(!c.level.hasChunkAt(p))throw new IllegalStateException("投影部分区块尚未加载，请走近或缩小放置范围");
            var state=world.getBlockState(p);if(state.isAir()||state.is(Blocks.STRUCTURE_VOID))continue;
            expected.put(p,state);actual.put(p,c.level.getBlockState(p));
        }
        if(iterator.hasNext())return;
        loading=false;total=expected.size();if(total==0){stop(c,"可见层没有可建造方块");return;}
        recount(c);initial=matched;lastMatched=matched;lastGain=tick;
    }
    private Map<Item,Integer> inventory(Minecraft c){var result=new HashMap<Item,Integer>();for(int i=0;i<36;i++){var s=c.player.getInventory().getItem(i);if(!s.isEmpty())result.merge(s.getItem(),s.getCount(),Integer::sum);}return result;}
    private void recount(Minecraft c){
        matched=blockedBlocks=0;var needs=new HashMap<Item,Integer>();var inv=inventory(c);
        for(var e:expected.entrySet()){
            var state=actual.get(e.getKey());if(e.getValue().equals(state)){matched++;continue;}
            if(state!=null&&!state.canBeReplaced()&&!state.isAir())blockedBlocks++;
            var item=e.getValue().getBlock().asItem();String s=e.getValue().toString();
            if(item!=Items.AIR&&!s.contains("half=upper")&&!s.contains("part=head"))needs.merge(item,1,Integer::sum);
        }
        var text=new ArrayList<String>();needs.entrySet().stream().sorted(Comparator.<Map.Entry<Item,Integer>>comparingInt(e->e.getValue()-inv.getOrDefault(e.getKey(),0)).reversed()).forEach(e->{int n=e.getValue()-inv.getOrDefault(e.getKey(),0);if(n>0&&text.size()<4)text.add(new ItemStack(e.getKey()).getHoverName().getString()+" ×"+n);});
        missing=text.isEmpty()?"":"待补材料："+String.join("、",text);
    }
    private List<BlockPos> available(Minecraft c){
        var inv=inventory(c);var result=new ArrayList<BlockPos>();
        for(var e:expected.entrySet()){
            var p=e.getKey();if(e.getValue().equals(actual.get(p))||inv.getOrDefault(e.getValue().getBlock().asItem(),0)==0)continue;
            if(!LitematicaAccess.inVisibleLayer(p)||!c.level.getBlockState(p).canBeReplaced())continue;
            boolean support=false;for(Direction d:Direction.values()){var s=c.level.getBlockState(p.relative(d));if(!s.isAir()&&!s.canBeReplaced()&&s.getFluidState().isEmpty()){support=true;break;}}
            if(support)result.add(p);
        }
        result.sort(Comparator.comparingDouble(p->c.player.distanceToSqr(Vec3.atCenterOf(p))));return result;
    }
    private int reachable(Minecraft c,Vec3 feet,List<BlockPos> targets,boolean stopAtFirst){
        int count=0;var eye=feet.add(0,c.player.getEyeHeight(),0);
        for(var p:targets){var aim=Vec3.atCenterOf(p);if(eye.distanceTo(aim)>4.15 || body(feet).intersects(new AABB(p)))continue;
            var hit=c.level.clip(new ClipContext(eye,aim,ClipContext.Block.COLLIDER,ClipContext.Fluid.NONE,c.player));
            if(hit.getType()==HitResult.Type.MISS||hit.getBlockPos().equals(p)){count++;if(stopAtFirst)return count;}
        }return count;
    }
    private static Vec3 feet(BlockPos p){return new Vec3(p.getX()+.5,p.getY()+.02,p.getZ()+.5);}
    private static AABB body(Vec3 p){return new AABB(p.x-.31,p.y+.01,p.z-.31,p.x+.31,p.y+1.82,p.z+.31);}
    private boolean clear(Minecraft c,BlockPos p){
        if(p.getX()<selection.min().getX()-5||p.getX()>selection.max().getX()+5||p.getZ()<selection.min().getZ()-5||p.getZ()>selection.max().getZ()+5||p.getY()<selection.min().getY()-2||p.getY()>selection.max().getY()+5)return false;
        if(!c.level.hasChunkAt(p)||!c.level.noCollision(c.player,body(feet(p))))return false;
        for(int y=0;y<2;y++){var s=c.level.getBlockState(p.above(y));if(!s.getFluidState().isEmpty()||s.is(Blocks.FIRE)||s.is(Blocks.LAVA)||s.is(Blocks.COBWEB)||s.is(Blocks.POWDER_SNOW))return false;}
        return true;
    }
    private void plan(Minecraft c){
        release(c);flight.hover();flight.allowPlacementSneak(false);look=null;phase="规划走位";reason="寻找有支撑且可接近的施工位置";
        var targets=available(c);if(targets.isEmpty()){stop(c,missing.isBlank()?"剩余方块需要支撑面或已有方块需要人工修正":missing);return;}
        var clearCache=new HashMap<BlockPos,Boolean>();var goals=new HashSet<BlockPos>();
        for(var p:targets.stream().limit(80).toList())for(var d:Direction.Plane.HORIZONTAL)for(int down=0;down<=2;down++){
            var q=p.relative(d,2).below(down);if(blocked.getOrDefault(q,0)>tick||!clearCache.computeIfAbsent(q,k->clear(c,k)))continue;
            if(reachable(c,feet(q),List.of(p),true)>0)goals.add(q);
        }
        BlockPos start=null;double distance=Double.POSITIVE_INFINITY;
        for(var p:BlockPos.betweenClosed(c.player.blockPosition().offset(-1,-1,-1),c.player.blockPosition().offset(1,1,1))){var q=p.immutable();if(!clearCache.computeIfAbsent(q,k->clear(c,k)))continue;
            var delta=feet(q).subtract(c.player.position());if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(delta)))continue;
            if(delta.lengthSqr()<distance){distance=delta.lengthSqr();start=q;}
        }
        if(start==null){stop(c,"当前站位太窄，请移到通道中间再开始");return;}
        var result=BuildPath.find(new BuildPath.World(){public boolean clear(BlockPos p){return clearCache.computeIfAbsent(p,k->ProjectionBuildJob.this.clear(c,k));}public boolean edge(BlockPos a,BlockPos b){return c.level.noCollision(c.player,body(feet(a)).expandTowards(feet(b).subtract(feet(a))));}},start,goals::contains,10000);
        if(result.nodes().isEmpty()){stop(c,"找不到可通行路线；请检查门口、支撑或剩余材料。"+missing);return;}
        path=result.nodes();pathIndex=0;station=path.getLast();stall=0;bestDistance=Double.POSITIVE_INFINITY;
    }
    private void move(Minecraft c){
        ProfessionalPrinter.pause();
        if(pathIndex>=path.size()){path=List.of();beginPrinting(c);return;}
        var dest=feet(path.get(pathIndex));var delta=dest.subtract(c.player.position());double dist=delta.length();
        if(Math.hypot(delta.x,delta.z)<.12&&Math.abs(delta.y)<.12){pathIndex++;stall=0;bestDistance=Double.POSITIVE_INFINITY;release(c);flight.hover();return;}
        if(!clear(c,path.get(pathIndex))){replan(c,"通道变化");return;}
        if(dist<bestDistance-.015){bestDistance=dist;stall=0;}else if(++stall>50){replan(c,"走位没有进展");return;}
        release(c);boolean vertical=Math.abs(delta.y)>.12;
        Vec3 probe=vertical?new Vec3(0,Math.copySign(Math.min(.12,Math.abs(delta.y)),delta.y),0):new Vec3(delta.x,0,delta.z).normalize().scale(.12);
        if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(probe))){replan(c,"身体前方有障碍");return;}
        if(vertical){flight.speed(Math.abs(delta.y)>.3?.024:.008);c.options.keyJump.setDown(delta.y>0);c.options.keyShift.setDown(delta.y<0);}
        else{look=new RotationAim.Look((float)(Math.toDegrees(Math.atan2(delta.z,delta.x))-90),0);RotationAim.apply(c.player,look);flight.speed(Math.hypot(delta.x,delta.z)>.3?.012:.004);c.options.keyUp.setDown(true);}
        phase="自动走位";reason=(pathIndex+1)+" / "+path.size()+" · "+station.toShortString();
    }
    private void replan(Minecraft c,String why){release(c);flight.hover();if(station!=null)blocked.put(station,tick+600);path=List.of();station=null;reason=why;}
    private void beginPrinting(Minecraft c){
        departure.reset();release(c);look=null;if(autoMove){flight.hover();flight.allowPlacementSneak(true);}if(!ProfessionalPrinter.owned())ProfessionalPrinter.start();station=c.player.blockPosition();lastMatched=matched;lastGain=tick;printSince=tick;phase="打印中";reason="由 Litematica Printer 放置与校正朝向";
    }
    private static void release(Minecraft c){if(c.options==null)return;c.options.keyUp.setDown(false);c.options.keyDown.setDown(false);c.options.keyLeft.setDown(false);c.options.keyRight.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);c.options.keySprint.setDown(false);}
}
