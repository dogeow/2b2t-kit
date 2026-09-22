package dev.twob2tkit.builder;

import com.google.gson.JsonObject;
import dev.twob2tkit.runtime.api.BuildNavigation;
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
    private boolean active,autoMove,loading,defensePaused;
    private String session="",outcome="idle",lastSupervision="";
    private int lastSupervisionTick=-1000,supervisionCount,loadWait;
    private Iterator<BlockPos> rescan;
    private final Map<String,Integer> materialDeficits=new TreeMap<>(), materialNeeds=new TreeMap<>();
    private ClientLevel level;
    private Map<Item,Integer> stoppedInventory=Map.of();
    private LitematicaAccess.BuildSelection selection;
    private JsonObject navigationDebug=new JsonObject();
    private final Map<BlockPos,BlockState> expected=new LinkedHashMap<>(),actual=new HashMap<>();
    private final Map<BlockPos,Integer> blocked=new HashMap<>();
    private Iterator<BlockPos> iterator;
    private List<BlockPos> path=List.of();
    private BlockPos station;
    private BuildNavigation.Search pathSearch;
    private BuildNavigation navigation;
    private Vec3 searchOrigin;
    private int pathIndex,tick,matched,total,initial,blockedBlocks,printSince,lastGain,lastMatched,stall,scanSince;
    private double bestDistance=Double.POSITIVE_INFINITY;
    private String phase="未开始",reason="",missing="",name="";
    private RotationAim.Look look;
    public ProjectionBuildJob(KitConfig config){this.config=config;}
    public boolean isActive(){return active;}
    /** Main-thread handoff: keep the same task/lease, discard old search objects and rescan. */
    public void prepareRuntimeReload(Minecraft c){
        if(!active)return;
        if(ProfessionalPrinter.owned()&&!ProfessionalPrinter.readyForTravel())throw new IllegalStateException("等待服务器确认最后一次放置后再热更新");
        ProfessionalPrinter.stop(c,false);release(c);if(autoMove)flight.hover();discardSearch();path=List.of();station=null;look=null;departure.reset();
    }
    public void runtimeReloaded(){
        navigation=KitClient.borer().buildNavigation();
        if(active){rescan=new ArrayList<>(expected.keySet()).iterator();phase="热更新后复核";reason="保持原投影与任务，重新检查现场";}
    }

    public boolean supervisionScopeCurrent(Minecraft c) throws Exception {
        return c.player!=null && c.level!=null && c.level==level && !c.player.isDeadOrDying()
            && selection!=null && selection.key().equals(LitematicaAccess.buildSelection().key());
    }
    private boolean gainedNeededSupply(Minecraft c){
        if(c.player==null||c.level!=level)return false;
        for(var entry:inventory(c).entrySet())if(materialNeeds.containsKey(BuiltInRegistries.ITEM.getKey(entry.getKey()).toString()) && entry.getValue()>stoppedInventory.getOrDefault(entry.getKey(),0))return true;
        return false;
    }
    public boolean supplyResumeReady(Minecraft c){return BuildSupervisionPolicy.mayResumeSupply(outcome,gainedNeededSupply(c));}
    public String status(){return phase+(reason.isBlank()?"":"："+reason);}
    public String progress(){return total==0?"开始后读取图纸与现场":"已匹配 "+matched+" / "+total+" 格 · 本次新增 "+Math.max(0,matched-initial)+" 格";}
    public String missing(){return missing.isBlank()?"当前材料检查未发现缺口":missing;}
    public JsonObject snapshot(){var j=new JsonObject();if(navigation!=null)j.addProperty("navigation_version",navigation.version());j.add("navigation",navigationDebug.deepCopy());j.addProperty("path_step",pathIndex);j.addProperty("path_length",path.size());if(pathIndex<path.size())j.addProperty("next_waypoint",path.get(pathIndex).toShortString());j.addProperty("active",active);j.addProperty("session",session);j.addProperty("outcome",outcome);j.addProperty("supply_wait",!active&&Set.of("missing_materials","blocked").contains(outcome));j.addProperty("supply_resume_ready",supplyResumeReady(Minecraft.getInstance()));j.addProperty("name",name);j.addProperty("placement_key",selection==null?"":selection.key());j.addProperty("loading",loading||rescan!=null);j.addProperty("supervision_count",supervisionCount);j.addProperty("last_supervision",lastSupervision);j.addProperty("queue_settled",!ProfessionalPrinter.owned()||ProfessionalPrinter.queueIdleForTravel());var deficits=new JsonObject();materialDeficits.forEach(deficits::addProperty);j.add("material_deficits",deficits);var needsJson=new JsonObject();materialNeeds.forEach(needsJson::addProperty);j.add("material_needs",needsJson);j.addProperty("phase",phase);j.addProperty("reason",reason);j.addProperty("matched",matched);j.addProperty("total",total);j.addProperty("new_blocks",Math.max(0,matched-initial));j.addProperty("missing",missing);j.addProperty("blocked_blocks",blockedBlocks);j.addProperty("auto_move",autoMove);j.addProperty("last_departure_idle_ticks",lastDepartureIdleTicks);j.addProperty("last_departure_early",lastDepartureEarly);j.addProperty("idle_ticks",tick-lastGain);if(station!=null)j.addProperty("station",station.toShortString());return j;}
    public boolean start(Minecraft c){
        try{
            if(c.player==null||c.level==null)return fail("请先进入世界");
            navigation=KitClient.borer().buildNavigation();selection=LitematicaAccess.buildSelection();name=selection.name();ProfessionalPrinter.clearFailure();
            if(selection.volume()>300000)return fail("投影范围过大，请拆成较小的独立放置");
            if(c.player.position().distanceTo(Vec3.atCenterOf(selection.min()))>150)return fail("请先走近选中的投影");
            var printer=ProfessionalPrinter.status();
            if(!printer.has("rotate") || !printer.get("rotate").getAsBoolean() || printer.get("in_air").getAsBoolean() || printer.get("air_place").getAsBoolean())return fail("打印器需开启自动朝向，关闭悬空打印及 Meteor Air Place");
            defensePaused=false;autoMove=config.projectionAutoMove;level=c.level;active=true;loading=true;session=UUID.randomUUID().toString();outcome="running";lastSupervisionTick=-1000;supervisionCount=0;loadWait=0;rescan=null;tick=matched=total=initial=0;
            discardSearch();departure.reset();lastDepartureIdleTicks=-1;lastDepartureEarly=false;expected.clear();actual.clear();blocked.clear();path=List.of();station=null;look=null;
            iterator=BlockPos.betweenClosed(selection.min(),selection.max()).iterator();
            if(autoMove){flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/build-flight-speed.bak"));String error=flight.acquire(c.player);if(error!=null){finishJob(c,error,"dependency_error");return false;}flight.hover();}
            phase="检查投影";reason=name;return true;
        }catch(Exception e){finishJob(c,e.getMessage(),"error");return fail(e.getMessage());}
    }
    private boolean fail(String why){outcome="error";phase="无法开始";reason=why==null?"读取依赖失败":why;return false;}
    public void stop(Minecraft c,String why){finishJob(c,why,"manual_stop");}
    private void finishJob(Minecraft c,String why,String outcome){
        if(!active)return;
        discardSearch();this.outcome=outcome;rescan=null;if(c.player!=null&&Set.of("missing_materials","blocked").contains(outcome))stoppedInventory=Map.copyOf(inventory(c));
        ProfessionalPrinter.stop(c,false);release(c);look=null;
        if(autoMove){if(c.player!=null&&!c.player.onGround())flight.closeKeepingFlight();else flight.close();}
        active=false;phase="已停止";reason=why==null?"未知错误":why;path=List.of();
        if(c.player!=null)c.player.sendSystemMessage(net.minecraft.network.chat.Component.literal("[投影建造] "+reason+" · "+progress()));
    }
    private boolean supplySafe(Minecraft c,String expectedSession) throws Exception {
        boolean safe=c.player!=null && c.level==level && c.screen==null && c.player.getHealth()>=14 && !KitKeys.manualMovementDown(c)
            && !KitClient.borer().isActive() && !KitClient.planter().isActive() && !KitClient.feeder().isActive() && !KitClient.chopper().isActive() && !KitClient.controller().isActive()
            && !dev.twob2tkit.automation.AutomationBridge.guardBusy();
        return c.player!=null && selection!=null && c.player.position().distanceTo(Vec3.atCenterOf(selection.min()))<=150 && BuildSupervisionPolicy.maySupply(session.equals(expectedSession),active,outcome,safe) && selection.key().equals(LitematicaAccess.buildSelection().key());
    }
    public JsonObject plankRecipe(Minecraft c,String expectedSession,String output) throws Exception {
        if(!supplySafe(c,expectedSession) || !output.matches("minecraft:(oak|spruce|birch|jungle|acacia|dark_oak|mangrove|cherry|pale_oak)_planks"))throw new IllegalStateException("Supply recipe scope changed");
        int needed=materialNeeds.getOrDefault(output,0),stock=0,logs=0;String log=output.replace("_planks","_log");
        for(int i=0;i<36;i++){var item=c.player.getInventory().getItem(i);String id=BuiltInRegistries.ITEM.getKey(item.getItem()).toString();if(id.equals(output))stock+=item.getCount();if(id.equals(log))logs+=item.getCount();}
        if(needed<=stock || logs==0)throw new IllegalStateException("No verified plank deficit or logs");
        int capacity=dev.twob2tkit.automation.BuildSupplyTask.room(c,output);if(capacity<4)throw new IllegalStateException("No free inventory room for planks");
        var result=new JsonObject();result.addProperty("width",2);result.addProperty("output",output);result.addProperty("produces",4);result.addProperty("repetitions",Math.min(capacity/4,Math.min(16,Math.min(logs,(needed-stock+3)/4))));
        var grid=new JsonObject();grid.addProperty("1",log);result.add("ingredients",grid);return result;
    }
    public void supervise(Minecraft c,String action,String expectedSession) throws Exception {
        if(action.equals("resume_after_supply")){
            if(!supplySafe(c,expectedSession) || !supplyResumeReady(c) || available(c).isEmpty())throw new IllegalStateException("Supply resume requires the same missing-material job and actual usable items");
            String oldSession=session;int oldCount=supervisionCount;
            if(!start(c))throw new IllegalStateException("Build could not resume: "+reason);
            session=oldSession;supervisionCount=oldCount+1;lastSupervision="resume_after_supply";return;
        }
        boolean safe=c.player!=null && c.level==level && c.screen==null && c.player.getHealth()>=14 && !KitKeys.manualMovementDown(c)
            && !dev.twob2tkit.automation.AutomationBridge.guardBusy();
        if(!BuildSupervisionPolicy.mayApply(action,session.equals(expectedSession),active,loading||rescan!=null,!ProfessionalPrinter.owned()||ProfessionalPrinter.queueIdleForTravel(),safe,tick-lastSupervisionTick))
            throw new IllegalStateException("Build supervision rejected: task, input, cooldown or server queue changed");
        if(!selection.key().equals(LitematicaAccess.buildSelection().key()))throw new IllegalStateException("Projection changed during supervision");
        lastSupervisionTick=tick;supervisionCount++;lastSupervision=action;
        switch(action){
            case "replan" -> replan(c,"Jev 请求重新规划施工站位");
            case "rescan" -> {discardSearch();rescan=new ArrayList<>(expected.keySet()).iterator();ProfessionalPrinter.pause();release(c);}
            case "pause_and_report" -> finishJob(c,"托管已暂停，现场已记录", "needs_review");
            default -> throw new IllegalArgumentException("Unsupported build supervision action");
        }
    }
    public void pauseForDefense(Minecraft c){
        if(!active)return;discardSearch();defensePaused=true;departure.reset();ProfessionalPrinter.pause();look=null;phase="防护中";reason="让出移动与飞行控制";
    }
    public void pause(Minecraft c){
        if(!active)return;
        discardSearch();departure.reset();ProfessionalPrinter.pause();release(c);look=null;if(autoMove)flight.hover();
        phase="已暂停";reason=c.screen!=null?"界面已打开，关闭后继续":"等待防御或进食结束";
    }
    public void serverBlock(BlockPos pos,BlockState state){
        // Collision caches cannot survive authoritative changes inside the search volume.
        if(active&&pathSearch!=null&&selection!=null
            &&pos.getX()>=selection.min().getX()-5&&pos.getX()<=selection.max().getX()+5
            &&pos.getZ()>=selection.min().getZ()-5&&pos.getZ()<=selection.max().getZ()+5
            &&pos.getY()>=selection.min().getY()-2&&pos.getY()<=selection.max().getY()+7)discardSearch();
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
            if(ProfessionalPrinter.consumeRecheck()){discardSearch();ProfessionalPrinter.stop(c,false);recount(c);path=List.of();station=null;look=null;return;}
            if(!ProfessionalPrinter.failure().isEmpty()){finishJob(c,ProfessionalPrinter.failure(),"printer_error");return;}
            if(c.player==null||c.level!=level||c.player.isDeadOrDying()){finishJob(c,"离开原世界","world_changed");return;}
            if(c.screen!=null){pause(c);return;}
            if(c.player.getHealth()<14){pause(c);reason="血量不足，等待恢复";return;}
            tick++;
            if(tick%20==0&&!selection.key().equals(LitematicaAccess.buildSelection().key())){finishJob(c,"投影位置或范围已改变，请重新检查后开始","placement_changed");return;}
            if(loading){load(c);return;}
            if(rescan!=null){for(int n=0;n<2048&&rescan.hasNext();n++){BlockPos p=rescan.next();if(!c.level.hasChunkAt(p))throw new IllegalStateException("Rescan chunk not loaded");actual.put(p,c.level.getBlockState(p));}if(!rescan.hasNext()){rescan=null;recount(c);}return;}
            if(tick-scanSince>=20){recount(c);scanSince=tick;}
            if(matched==total){finishJob(c,"当前投影范围全部匹配","complete");return;}
            if(defensePaused){defensePaused=false;ProfessionalPrinter.stop(c,false);path=List.of();station=null;look=null;}
            if(autoMove){String e=flight.acquire(c.player);if(e!=null){finishJob(c,e,"dependency_error");return;}}
            if(pathSearch!=null){advanceSearch(c);return;}
            if(!path.isEmpty()){move(c);return;}
            if(ProfessionalPrinter.owned()){
                ProfessionalPrinter.resume();
                phase="打印中";reason=station==null?"当前位置":station.toShortString();
                if(matched>lastMatched){lastGain=tick;lastMatched=matched;departure.reset();}
                // Poll twice per four ticks; an authoritative gain resets the quiet period immediately.
                if(tick%2!=0)return;
                boolean settled=ProfessionalPrinter.readyForTravel();
                boolean localWork=settled&&reachable(c,c.player.position(),available(c),true)>0;
                boolean completed=departure.observe(tick,settled,localWork,navigation.policy().quietTicks());
                if(!completed&&(tick-lastGain<navigation.policy().retryTicks()||!ProfessionalPrinter.queueIdleForTravel()))return;
                lastDepartureIdleTicks=tick-lastGain;lastDepartureEarly=completed;
                KitClient.LOGGER.info("[Build] station-complete idle_ticks={} confirmed_local_completion={} station={}",lastDepartureIdleTicks,completed,station);
                ProfessionalPrinter.stop(c,false);look=null;recount(c);
                if(!autoMove){if(available(c).isEmpty()&&!missing.isBlank())finishJob(c,missing,"missing_materials");else finishJob(c,"附近暂时没有可放方块；移动到下一处后继续","needs_reposition");return;}
                if(station!=null)blocked.put(station,tick+600);
                station=null;
            }
            if(!autoMove || blocked.getOrDefault(stationKey(c.player.position()),0)<=tick && reachable(c,c.player.position(),available(c),true)>0){beginPrinting(c);return;}
            plan(c);
        }catch(Exception e){finishJob(c,e.getMessage(),"error");}
    }
    private void load(Minecraft c){
        String waiting=LitematicaAccess.loadingReason(selection);
        if(!waiting.isEmpty()){
            expected.clear();actual.clear();iterator=BlockPos.betweenClosed(selection.min(),selection.max()).iterator();
            phase="等待图纸加载";reason=waiting;
            if(++loadWait>600)finishJob(c,"图纸区块未完成加载，请先检查投影："+waiting,"schematic_not_ready");
            return;
        }
        phase="检查投影";
        var world=LitematicaAccess.schematicWorld();if(world==null)throw new IllegalStateException("投影世界不可用");
        for(int n=0;n<2048&&iterator.hasNext();n++){
            var p=iterator.next().immutable();if(!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p))continue;
            if(!c.level.hasChunkAt(p))throw new IllegalStateException("投影部分区块尚未加载，请走近或缩小放置范围");
            var state=world.getBlockState(p);if(state.isAir()||state.is(Blocks.STRUCTURE_VOID))continue;
            expected.put(p,state);actual.put(p,c.level.getBlockState(p));
        }
        if(iterator.hasNext())return;
        loading=false;total=expected.size();if(total==0){finishJob(c,"可见层没有可建造方块","empty_projection");return;}
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
        materialNeeds.clear();needs.forEach((item,count)->materialNeeds.put(BuiltInRegistries.ITEM.getKey(item).toString(),count));
        materialDeficits.clear();needs.forEach((item,count)->{int n=count-inv.getOrDefault(item,0);if(n>0)materialDeficits.put(BuiltInRegistries.ITEM.getKey(item).toString(),n);});
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
    static BlockPos stationKey(Vec3 pos){return new BlockPos((int)Math.floor(pos.x),(int)Math.round(pos.y-.02),(int)Math.floor(pos.z));}
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
        var targets=available(c);navigationDebug=new JsonObject();navigationDebug.addProperty("targets",targets.size());navigationDebug.addProperty("player",c.player.position().toString());if(targets.isEmpty()){finishJob(c,missing.isBlank()?"剩余方块需要支撑面或已有方块需要人工修正":missing,missing.isBlank()?"blocked":"missing_materials");return;}
        var clearCache=new HashMap<BlockPos,Boolean>();var goals=new HashSet<BlockPos>();
        for(var p:targets.stream().limit(80).toList())for(var q:navigation.stations(p)){
            if(blocked.getOrDefault(q,0)>tick||!clearCache.computeIfAbsent(q,k->clear(c,k)))continue;
            if(reachable(c,feet(q),List.of(p),true)>0)goals.add(q);
        }
        BlockPos start=null;double distance=Double.POSITIVE_INFINITY;
        for(var p:BlockPos.betweenClosed(c.player.blockPosition().offset(-1,-1,-1),c.player.blockPosition().offset(1,1,1))){var q=p.immutable();if(!clearCache.computeIfAbsent(q,k->clear(c,k)))continue;
            var delta=feet(q).subtract(c.player.position());if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(delta)))continue;
            if(delta.lengthSqr()<distance){distance=delta.lengthSqr();start=q;}
        }
        navigationDebug.addProperty("goals",goals.size());navigationDebug.addProperty("start",start==null?"none":start.toShortString());
        if(start==null){finishJob(c,"当前站位太窄，请移到通道中间再开始","blocked");return;}
        pathSearch=navigation.search(new BuildNavigation.World(){public boolean clear(BlockPos p){return clearCache.computeIfAbsent(p,k->ProjectionBuildJob.this.clear(c,k));}public boolean edge(BlockPos a,BlockPos b){return c.level.noCollision(c.player,body(feet(a)).expandTowards(feet(b).subtract(feet(a))));}},start,goals);
        searchOrigin=c.player.position();advanceSearch(c);
    }
    private void discardSearch(){pathSearch=null;searchOrigin=null;navigationDebug.addProperty("search_pending",false);}
    private void advanceSearch(Minecraft c){
        release(c);flight.hover();look=null;
        if(c.player.position().distanceToSqr(searchOrigin)>.75*.75){discardSearch();return;}
        var result=pathSearch.advance(Math.min(navigation.policy().sliceNodes(),navigation.policy().totalNodes()-pathSearch.expanded()),System.nanoTime()+navigation.policy().sliceNanos());
        navigationDebug.addProperty("expanded",pathSearch.expanded());
        navigationDebug.addProperty("search_pending",result==null);
        if(result==null){
            phase="规划走位";reason="继续搜索可通行路线 · "+pathSearch.expanded()+" 个位置";
            if(pathSearch.expanded()>=navigation.policy().totalNodes()){navigationDebug.addProperty("budget_exhausted",true);finishJob(c,"路线搜索达到预算上限，尚不能确认是否有路","needs_review");}
            return;
        }
        discardSearch();navigationDebug.addProperty("path_length",result.nodes().size());
        if(result.nodes().isEmpty()){finishJob(c,"找不到可通行路线；请检查门口、支撑或剩余材料。"+missing,"blocked");return;}
        path=result.nodes();pathIndex=0;station=path.getLast();stall=0;bestDistance=Double.POSITIVE_INFINITY;
    }
    private void move(Minecraft c){
        ProfessionalPrinter.pause();
        if(pathIndex>=path.size()){path=List.of();beginPrinting(c);return;}
        var dest=feet(path.get(pathIndex));var delta=dest.subtract(c.player.position());double dist=delta.length();
        var motion=navigation.motion(delta);
        if(motion.arrived()){pathIndex++;stall=0;bestDistance=Double.POSITIVE_INFINITY;release(c);flight.hover();return;}
        if(!clear(c,path.get(pathIndex))){replan(c,"通道变化");return;}
        if(dist<bestDistance-.015){bestDistance=dist;stall=0;}else if(++stall>navigation.policy().stallTicks()){replan(c,"走位没有进展");return;}
        release(c);boolean vertical=motion.vertical();
        Vec3 probe=motion.probe();
        if(!c.level.noCollision(c.player,c.player.getBoundingBox().expandTowards(probe))){
            navigationDebug.addProperty("blocked_from",c.player.position().toString());navigationDebug.addProperty("blocked_destination",dest.toString());
            navigationDebug.addProperty("blocked_probe",probe.toString());replan(c,"身体前方有障碍");return;
        }
        if(vertical){flight.speed(motion.speed());c.options.keyJump.setDown(delta.y>0);c.options.keyShift.setDown(delta.y<0);}
        else{look=new RotationAim.Look((float)(Math.toDegrees(Math.atan2(delta.z,delta.x))-90),0);RotationAim.apply(c.player,look);flight.speed(motion.speed());c.options.keyUp.setDown(true);}
        phase="自动走位";reason=(pathIndex+1)+" / "+path.size()+" · "+station.toShortString();
    }
    private void replan(Minecraft c,String why){discardSearch();release(c);flight.hover();if(station!=null)blocked.put(station,tick+600);path=List.of();station=null;reason=why;}
    private void beginPrinting(Minecraft c){
        departure.reset();release(c);look=null;if(autoMove){flight.hover();flight.allowPlacementSneak(true);}if(!ProfessionalPrinter.owned())ProfessionalPrinter.start();if(station==null)station=stationKey(c.player.position());lastMatched=matched;lastGain=tick;printSince=tick;phase="打印中";reason="由 Litematica Printer 放置与校正朝向";
    }
    private static void release(Minecraft c){if(c.options==null)return;c.options.keyUp.setDown(false);c.options.keyDown.setDown(false);c.options.keyLeft.setDown(false);c.options.keyRight.setDown(false);c.options.keyJump.setDown(false);c.options.keyShift.setDown(false);c.options.keySprint.setDown(false);}
}
