package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import com.google.gson.JsonArray;
import dev.twob2tkit.*;
import dev.twob2tkit.cruise.CruiseScreenHud;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.tags.FluidTags;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.entity.EquipmentSlot;
import net.minecraft.world.entity.item.ItemEntity;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Native, bounded seafloor collection driven by the Kit button, without Python or fixed coordinates. */
public final class GravelCollector {
    private enum Step {TOOL,SCAN,CHOOSE,SETTLE_HIGH,SURFACE,SETTLE_SURFACE,DIVE,SETTLE_DIVE,
        ARM,CHECK_AIR,REFILL,FIND,STAND,HOVER,MINE,DROP,PICKUP,VERIFY,RETURN,PARK,FINISH}
    private static boolean running,stopping,footingFlightDisabled,minedUnderfoot;
    private static String status="在海面上方开始；需要水下装备和精准采集铲",stopReason="";
    private static NativeMaterialSession session;
    private static ClientLevel world;
    private static Step step,next;
    private static int ticks,phaseSince,stable,initialCount,collected,limit,radius,depth,
        scanIndex,scanChosenCount,patches,failures,pickupRetries,alignmentAttempts,driftAttempts;
    private static double returnY,parkY,routineY,diveY;
    private static Vec3 origin,settlePos,dropPose;
    private static BlockPos target,mined;
    private static UUID dropId;
    private static int beforeMine;
    private static final List<BlockPos> candidates=new ArrayList<>();
    private static final Set<BlockPos> visited=new HashSet<>();
    private static final Set<BlockPos> blockedTargets=new HashSet<>();
    private static final Set<BlockPos> standFailed=new HashSet<>();
    private static final Map<BlockPos,Integer> approaches=new HashMap<>();
    private static final Map<UUID,Integer> beforeDrops=new HashMap<>();
    private static JsonObject observed=new JsonObject();
    private GravelCollector() {}

    public static boolean isActive(){return running;}
    public static String status(){return status+(running||collected>0?" · 已收集 "+collected+(limit>0?"/"+limit:"")+" 块":"");}
    public static JsonObject snapshot(){var j=new JsonObject();j.addProperty("active",running);j.addProperty("collected",collected);j.addProperty("limit",limit);j.addProperty("status",status());j.addProperty("phase",step==null?"idle":step.name());j.addProperty("pickup_retries",pickupRetries);j.addProperty("skipped_pickups",failures);j.addProperty("pending_inventory_before",beforeMine);j.addProperty("scan_index",scanIndex);j.addProperty("scan_total",GravelScanOrder.size(Math.max(0,radius)));if(target!=null)j.add("selected_target",ints(target));if(mined!=null)j.add("pending_block",ints(mined));if(dropId!=null)j.addProperty("pending_drop",dropId.toString());return j;}

    public static boolean start(Minecraft c){
        if(running)return true;
        String problem=preflight(c);
        if(problem!=null){status=problem;return false;}
        KitClient.stopWork("开始采集沙砾");
        c.setScreen(null);
        origin=c.player.position();world=c.level;
        var config=KitClient.config();radius=Math.clamp(config.gravelRadius,4,64);
        depth=Math.clamp(config.gravelDepth,6,32);limit=Math.max(0,config.gravelLimit);
        returnY=c.level.getSeaLevel()+2;
        parkY=Math.max(origin.y,Math.max(returnY+20,c.level.getHeight(
            net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,
            (int)Math.floor(origin.x),(int)Math.floor(origin.z))+22));
        initialCount=count(c);collected=0;visited.clear();blockedTargets.clear();standFailed.clear();candidates.clear();approaches.clear();beforeDrops.clear();
        scanIndex=scanChosenCount=patches=failures=pickupRetries=alignmentAttempts=driftAttempts=ticks=stable=0;
        target=mined=null;dropId=null;dropPose=null;stopping=footingFlightDisabled=minedUnderfoot=false;
        try{
            session=NativeMaterialSession.open(c,new Vec3(origin.x,parkY,origin.z));
            running=true;step=Step.SCAN;status="扫描附近海床";
            var tool=args("item",toolId(c));tool.addProperty("slot",toolSlot(c));
            issue(c,"select_item",tool,Step.TOOL);
            KitClient.LOGGER.info("[Gravel] started radius={} depth={} limit={}",radius,depth,limit);
            return true;
        }catch(Exception e){
            var own=session;session=null;running=false;next=null;step=null;
            if(own!=null)try{own.cancel(c,"启动未完成");}catch(Exception ignored){}
            KitClient.LOGGER.warn("[Gravel] start failed: {}",message(e));
            status="无法开始："+friendly(message(e));return false;
        }
    }

    public static void stop(Minecraft c,String reason){
        if(!running)return;
        stopping=true;stopReason=reason;status="停止采集，返回安全高度";
        restoreFootingFlight();
        KitClient.LOGGER.info("[Gravel] stop reason={} step={} pending={} before={} current={} retry={} air={}",
            reason,step,mined,beforeMine,c.player==null?-1:count(c),pickupRetries,c.player==null?-1:c.player.getAirSupply());
        if(c.screen instanceof KitHudScreen)c.setScreen(null);
        try{session.interrupt(c,reason);session.poll(c);next=null;step=Step.RETURN;}
        catch(Exception e){cancel(c,reason);}
    }

    /** Emergency stop/manual takeover always wins over automatic surfacing. */
    public static void cancel(Minecraft c,String reason){
        if(!running)return;
        running=false;next=null;status="已停止："+reason;
        restoreFootingFlight();
        var own=session;session=null;
        if(own!=null)try{own.cancel(c,reason);}catch(Exception ignored){}
        CruiseScreenHud.hide();
    }

    public static void tick(Minecraft c){
        if(!running)return;
        if(c.player==null||c.level!=world||c.player.isDeadOrDying()) {cancel(c,"离开原世界");return;}
        if(KitKeys.manualMovementDown(c)){cancel(c,"手动移动接管");return;}
        ticks++;
        try{
            observed=session.snapshot(c);
            collected=GravelCollectionPolicy.credited(initialCount,count(c));
            if(observed.has("air_return_active")&&observed.get("air_return_active").getAsBoolean()){
                status="氧气不足，正在自动返气";return;
            }
            if(c.player.getHealth()<19||nearThreat(c)){
                if(!stopping)stop(c,"附近威胁或生命变化");
            }
            if(session.busy()){
                JsonObject reply=session.poll(c);if(reply==null)return;
                String phase=text(reply,"phase");
                if(!phase.equals("done")){
                    if(next==Step.DROP&&mined!=null&&GravelCollectionPolicy.skipUnstartedMine(
                            text(reply,"detail"),c.level.getBlockState(mined).is(Blocks.GRAVEL),count(c)-beforeMine)){
                        blockedTargets.add(mined);mined=null;next=null;step=Step.FIND;phaseSince=ticks;
                    }else if(next==Step.STAND && c.player.getHealth()>=19
                            && c.player.getAirSupply()>=number(observed,"air_return_floor",240)){
                        restoreFootingFlight();standFailed.add(target);next=null;step=Step.FIND;phaseSince=ticks;
                    }else if(mined!=null&&GravelCollectionPolicy.recoverableDescentAirStop(
                            text(reply,"detail"),c.player.getHealth())){
                        KitClient.LOGGER.info("[Gravel] pickup needs air; pending={} air={} floor={}",
                            mined,c.player.getAirSupply(),number(observed,"air_pickup_floor",260));
                        next=null;step=Step.RETURN;phaseSince=ticks;
                        status="拾取前氧气不足，换气后继续";
                    }else if(next==Step.SETTLE_HIGH&&target!=null&&c.player.getHealth()>=19
                            &&!c.player.isUnderWater()&&text(reply,"detail").contains("时间上限")){
                        KitClient.LOGGER.warn("[Gravel] skip unreachable target={} current={}",target,c.player.position());
                        blockedTargets.add(target);next=null;step=Step.CHOOSE;phaseSince=ticks;
                        status="跳过暂时无法到达的海床";
                    }else if(text(reply,"air_return_phase").equals("recovered")){
                        next=null;stopping=true;stopReason="已自动返气，任务暂停";step=Step.RETURN;
                    }else if(!stopping){KitClient.LOGGER.warn("[Gravel] child failed: {}",text(reply,"detail"));stop(c,friendly(text(reply,"detail")));}
                    else {safeExit(c,"返程未完成："+text(reply,"detail"));return;}
                }else if(next!=null){step=next;next=null;phaseSince=ticks;stable=0;settlePos=null;}
            }
            if(next!=null)return;
            if(c.screen!=null&&!stopping){status="界面打开，采集暂停";return;}
            if(!stopping&&(room(c)<=0||mined==null&&GravelCollectionPolicy.complete(collected,limit,room(c)))){stop(c,room(c)<=0?"背包已满":"达到采集数量");}
            switch(step){
                case TOOL -> {
                    if(!usableShovel(c.player.getMainHandItem())){stop(c,"未选中可用的精准采集铲子");break;}
                    step=Step.SCAN;
                }
                case SCAN -> scan(c);
                case CHOOSE -> choose(c);
                case SETTLE_HIGH -> {
                    if(settled(c)){
                        if(target==null||!exposed(c,target)||!clearWater(c,target)){
                            if(target!=null)blockedTargets.add(target);
                            step=Step.CHOOSE;break;
                        }
                        if(!GravelCollectionPolicy.sameColumn(c.player.getX(),c.player.getZ(),target.getX(),target.getZ())){
                            if(++alignmentAttempts>2){blockedTargets.add(target);step=Step.CHOOSE;break;}
                            navigate(c,new Vec3(target.getX()+.5,routineY,target.getZ()+.5),Step.SETTLE_HIGH,.35);break;
                        }
                        step=Step.SURFACE;
                    }
                }
                case SURFACE -> navigate(c,new Vec3(target.getX()+.5,returnY,target.getZ()+.5),Step.SETTLE_SURFACE,.7);
                case SETTLE_SURFACE -> {if(settled(c))step=Step.DIVE;}
                case DIVE -> {
                    if(c.player.getAirSupply()<c.player.getMaxAirSupply()-2){status="等待氧气补满";break;}
                    if(mined!=null&&dropPose!=null){
                        diveY=dropPose.y+2;
                        navigate(c,new Vec3(dropPose.x,diveY,dropPose.z),Step.SETTLE_DIVE,.35);break;
                    }
                    if(target==null||!exposed(c,target)||!clearWater(c,target)){
                        if(target!=null)blockedTargets.add(target);
                        step=Step.PARK;break;
                    }
                    if(!GravelCollectionPolicy.sameColumn(c.player.getX(),c.player.getZ(),target.getX(),target.getZ())){
                        if(++alignmentAttempts>2){blockedTargets.add(target);step=Step.PARK;break;}
                        navigate(c,new Vec3(target.getX()+.5,returnY,target.getZ()+.5),Step.SETTLE_SURFACE,.35);break;
                    }
                    diveY=target.getY()+2;
                    navigate(c,new Vec3(target.getX()+.5,diveY,target.getZ()+.5),Step.SETTLE_DIVE,.7);
                }
                case SETTLE_DIVE -> {if(settled(c))step=Step.ARM;}
                case ARM -> {
                    if(!c.player.isUnderWater()){stop(c,"水位较浅，请使用陆地找矿");break;}
                    issue(c,"air_return_set",target(new Vec3(c.player.getX(),returnY,c.player.getZ())),Step.CHECK_AIR);
                }
                case CHECK_AIR -> {
                    // Collect with conservative fallback limits; real ascents calibrate over time.
                    status=text(observed,"air_budget_source").equals("observed")
                        ?"返气时间已校准，开始采集":"使用保守氧气余量开始采集";
                    step=Step.FIND;
                }
                case REFILL -> {
                    if(c.player.isUnderWater()){step=Step.RETURN;break;}
                    if(mined!=null&&pickupReceived(c)){pickupComplete(c);break;}
                    status="水面换气";
                    if(c.player.getAirSupply()>=c.player.getMaxAirSupply()-2){
                        if(mined!=null&&dropPose!=null){
                            diveY=dropPose.y+2;
                            navigate(c,new Vec3(dropPose.x,diveY,dropPose.z),Step.SETTLE_DIVE,.35);
                        }else if(target!=null){
                            navigate(c,new Vec3(target.getX()+.5,diveY,target.getZ()+.5),Step.SETTLE_DIVE,.35);
                        }else step=Step.PARK;
                    }
                }
                case FIND -> find(c);
                case STAND -> {
                    if(c.player.onGround()&&c.player.blockPosition().below().equals(target)
                            &&GravelFootingPolicy.stableFloor(c.level,target))step=Step.ARM;
                    else if(ticks-phaseSince>20){restoreFootingFlight();standFailed.add(target);step=Step.FIND;}
                }
                case HOVER -> {if(settled(c))step=Step.ARM;}
                case MINE -> mine(c);
                case DROP -> drop(c);
                case PICKUP -> {
                    if(pickupReceived(c)){pickupComplete(c);break;}
                    if(c.player.getAirSupply()<GravelCollectionPolicy.pickupStartFloor(
                            number(observed,"air_pickup_floor",260))){
                        navigate(c,new Vec3(c.player.getX(),returnY,c.player.getZ()),Step.REFILL);break;
                    }
                    var p=target(dropPose);p.addProperty("arrival",.35);p.addProperty("water_descend",true);
                    p.addProperty("restore_flight",true);p.addProperty("seconds",6);
                    issue(c,"walk",p,Step.VERIFY);
                }
                case VERIFY -> {
                    if(pickupReceived(c)){pickupComplete(c);}
                    else switch(GravelCollectionPolicy.pickupAction(ticks-phaseSince,pickupRetries,failures,
                            freshDrop(c)!=null,c.player.getAirSupply()>=GravelCollectionPolicy.pickupStartFloor(
                                number(observed,"air_pickup_floor",260)))){
                        case RETRY -> {pickupRetries++;phaseSince=ticks;step=Step.DROP;status="重新靠近掉落物";}
                        case SKIP -> skipPickup(c);
                        case STOP -> stop(c,"连续三次未确认入包，请检查网络后再试");
                        case WAIT -> status="等待入包确认";
                    }
                }
                case RETURN -> {
                    if(c.player.isUnderWater()||c.player.getY()<returnY-1)
                        navigate(c,new Vec3(c.player.getX(),returnY,c.player.getZ()),stopping?Step.PARK:Step.REFILL);
                    else step=stopping?Step.PARK:Step.REFILL;
                }
                case PARK -> navigate(c,new Vec3(c.player.getX(),stopping?parkY:
                    routineTravelY(c,c.player.getX(),c.player.getZ()),c.player.getZ()),
                    stopping?Step.FINISH:Step.CHOOSE);
                case FINISH -> {
                    session.finish(c,true);session=null;running=false;status="已结束："+stopReason;
                    CruiseScreenHud.finish("采集沙砾 · 已收集 "+collected+" 块");
                }
            }
            if(running&&!KitClient.controller().isActive())
                CruiseScreenHud.show("采沙砾 · "+collected+(limit>0?"/"+limit:"")+" · "+shortStatus(c));
        }catch(Exception error){
            KitClient.LOGGER.warn("[Gravel] {}",message(error));
            if(stopping){safeExit(c,"安全收尾失败："+message(error));}
            else stop(c,friendly(message(error)));
        }
    }

    private static void scan(Minecraft c){
        int total=GravelScanOrder.size(radius);
        for(int n=0;n<32&&scanIndex<total;n++,scanIndex++){
            var offset=GravelScanOrder.at(scanIndex);
            int x=(int)Math.floor(origin.x)+offset.x();
            int z=(int)Math.floor(origin.z)+offset.z();
            BlockPos p=below(c,x,z);if(p!=null)candidates.add(p);
        }
        status="扫描海床：已搜索 "+Math.min(radius,GravelScanOrder.at(Math.max(0,scanIndex-1)).ring())+"/"+radius+" 格";
        // A wide search should not delay the first dive until every outer ring is loaded.
        if(scanIndex>=total||scanIndex>=GravelScanOrder.size(Math.min(radius,8))&&candidates.size()>scanChosenCount){
            step=Step.CHOOSE;status="发现 "+candidates.size()+" 处沙砾";
        }
    }
    private static void choose(Minecraft c){
        patches++;
        target=candidates.stream().filter(p->!visited.contains(p)&&!blockedTargets.contains(p)&&approaches.getOrDefault(p,0)<3&&exposed(c,p))
            .min(Comparator.comparingDouble(p->horizontal(c.player.position(),Vec3.atCenterOf(p)))).orElse(null);
        if(target==null){
            if(scanIndex<GravelScanOrder.size(radius)){
                scanChosenCount=candidates.size();step=Step.SCAN;status="继续搜索外圈海床";return;
            }
            stop(c,"当前范围内没有更多安全沙砾，可扩大范围或换位置");return;
        }
        approaches.merge(target,1,Integer::sum);alignmentAttempts=0;status="前往下一片海床";
        routineY=routineTravelY(c,target.getX()+.5,target.getZ()+.5);
        KitClient.LOGGER.info("[Gravel] choose target={} from={} routineY={} scan={}/{}",
            target,c.player.position(),routineY,scanIndex,GravelScanOrder.size(radius));
        navigate(c,new Vec3(target.getX()+.5,routineY,target.getZ()+.5),Step.SETTLE_HIGH,.7);
    }
    private static void find(Minecraft c){
        if(mined!=null){step=Step.DROP;phaseSince=ticks;return;}
        if(c.player.getAirSupply()<number(observed,"air_work_floor",260)&&!breathing(c)){
            status="预留返气氧气";navigate(c,new Vec3(c.player.getX(),returnY,c.player.getZ()),Step.REFILL);return;
        }
        target=reachableNeighbor(c);
        if(target==null){mined=null;step=Step.RETURN;stopping=false;
            // A new patch is selected at high altitude only when this local chain is exhausted.
            navigate(c,new Vec3(c.player.getX(),returnY,c.player.getZ()),Step.PARK);return;}
        double d=horizontal(c.player.position(),Vec3.atCenterOf(target));
        boolean alreadyStanding=c.player.onGround()&&c.player.blockPosition().below().equals(target);
        if(!alreadyStanding&&!standFailed.contains(target)&&GravelFootingPolicy.mayStand(
                GravelFootingPolicy.stableFloor(c.level,target),clearWater(c,target),d,
                c.player.getY()-(target.getY()+1),c.player.getAirSupply(),number(observed,"air_pickup_floor",260))){
            var p=target(Vec3.atBottomCenterOf(target.above()));p.addProperty("arrival",.2);
            p.addProperty("water_descend",true);p.addProperty("restore_flight",false);p.addProperty("seconds",5);
            footingFlightDisabled=MeteorModules.isActive(MeteorModules.FLIGHT);
            status="靠近沙砾表面";issue(c,"walk",p,Step.STAND);return;
        }
        step=Step.MINE;
    }
    private static BlockPos reachableNeighbor(Minecraft c){
        Vec3 pos=c.player.position();BlockPos best=null;double score=Double.MAX_VALUE;
        BlockPos base=c.player.blockPosition();
        for(int x=base.getX()-2;x<=base.getX()+2;x++)for(int z=base.getZ()-2;z<=base.getZ()+2;z++)
            for(int y=base.getY()-4;y<=base.getY()-1;y++){
                BlockPos p=new BlockPos(x,y,z);Vec3 aim=Vec3.atCenterOf(p).add(0,.499,0);
                double d=horizontal(pos,Vec3.atCenterOf(p));
                if(!blockedTargets.contains(p)&&exposed(c,p)&&supported(c,p)
                        &&(!(c.player.onGround()&&c.player.blockPosition().below().equals(p))
                            ||GravelFootingPolicy.stableFloor(c.level,p))
                        &&GravelCollectionPolicy.reachable(pos.y,y,d,
                        c.player.getEyePosition().distanceTo(aim),c.player.blockInteractionRange()-.35)&&d<score){
                    var hit=c.level.clip(new net.minecraft.world.level.ClipContext(c.player.getEyePosition(),aim,
                        net.minecraft.world.level.ClipContext.Block.OUTLINE,net.minecraft.world.level.ClipContext.Fluid.NONE,c.player));
                    if(hit.getBlockPos().equals(p)){best=p;score=d;}
                }
            }
        return best;
    }
    private static void mine(Minecraft c){
        if(!exposed(c,target)||!supported(c,target)){step=Step.FIND;return;}
        minedUnderfoot=c.player.onGround()&&c.player.blockPosition().below().equals(target)
            &&GravelFootingPolicy.stableFloor(c.level,target);
        if(!minedUnderfoot)restoreFootingFlight();
        beforeMine=count(c);mined=target;dropId=null;dropPose=null;pickupRetries=driftAttempts=0;
        beforeDrops.clear();for(var e:c.level.getEntitiesOfClass(ItemEntity.class,
            new net.minecraft.world.phys.AABB(mined).inflate(6),e->e.isAlive()&&e.getItem().is(Items.GRAVEL)))
            beforeDrops.put(e.getUUID(),e.getItem().getCount());
        var p=new JsonObject();p.add("pos",ints(target));p.addProperty("face","up");
        p.addProperty("expected_state",c.level.getBlockState(target).toString());
        p.addProperty("underwater_gravel",true);p.addProperty("seconds",4);
        if(minedUnderfoot)p.addProperty("footing_gravel",true);
        status="挖掘沙砾";issue(c,"mine_block",p,Step.DROP);
    }
    private static void drop(Minecraft c){
        if(pickupReceived(c)){pickupComplete(c);return;}
        if(mined==null){step=Step.FIND;return;}
        if(c.level.getBlockState(mined).is(Blocks.GRAVEL)){
            if(ticks-phaseSince>30)stop(c,"服务器未确认挖除，已停止重试");return;
        }
        if(minedUnderfoot&&ticks-phaseSince<20){status="等待脚下沙砾自然入包";return;}
        restoreFootingFlight();minedUnderfoot=false;
        ItemEntity item=freshDrop(c);
        if(item==null){if(ticks-phaseSince>100)skipPickup(c);return;}
        BlockPos cell=item.blockPosition();BlockPos floor=null;
        for(int y=cell.getY();y>=cell.getY()-3;y--){BlockPos p=new BlockPos(cell.getX(),y,cell.getZ());
            if(c.level.hasChunkAt(p)&&!c.level.getBlockState(p).getCollisionShape(c.level,p).isEmpty()){floor=p;break;}}
        if(floor==null){stop(c,"掉落物下方没有安全落脚点");return;}
        dropPose=Vec3.atBottomCenterOf(floor.above());dropId=item.getUUID();
        double distance=horizontal(c.player.position(),item.position());
        if(distance>1.5){
            boolean clear=MaterialAirRoute.clearColumn(c,item.getX(),item.getZ(),returnY);
            if(GravelCollectionPolicy.recenterDriftingDrop(distance,driftAttempts,clear,
                    c.player.getAirSupply(),number(observed,"air_return_floor",240))){
                driftAttempts++;
                KitClient.LOGGER.info("[Gravel] recenter drifting drop={} distance={} attempt={} air={}",
                    dropId,distance,driftAttempts,c.player.getAirSupply());
                status="掉落物随水漂移，水面重新定位";
                navigate(c,new Vec3(c.player.getX(),returnY,c.player.getZ()),Step.REFILL);return;
            }
            stop(c,"掉落物离安全拾取位置过远");return;
        }
        double fall=c.player.getY()-dropPose.y;
        if(fall<.5){
            diveY=dropPose.y+2;status="调整拾取高度";
            navigate(c,new Vec3(c.player.getX(),diveY,c.player.getZ()),Step.HOVER);return;
        }
        if(fall>5){stop(c,"掉落物进入较深孔洞，保留安全余量");return;}
        status="拾取沙砾";step=Step.PICKUP;
    }

    private static void pickupComplete(Minecraft c){
        restoreFootingFlight();minedUnderfoot=false;
        KitClient.LOGGER.info("[Gravel] pickup block={} gained={} collected={} air={} retries={}",
            mined,count(c)-beforeMine,count(c)-initialCount,c.player.getAirSupply(),pickupRetries);
        int floor=mined==null?c.player.blockPosition().getY():mined.getY();
        if(mined!=null){visited.add(mined);BlockPos lower=below(c,mined.getX(),mined.getZ());
            if(lower!=null&&!candidates.contains(lower))candidates.add(lower);}
        mined=null;dropId=null;dropPose=null;
        collected=GravelCollectionPolicy.credited(initialCount,count(c));
        if(GravelCollectionPolicy.complete(collected,limit,room(c))){
            stop(c,room(c)<=0?"背包已满":"达到采集数量");return;
        }
        if(reachableNeighbor(c)!=null){step=Step.ARM;return;}
        diveY=floor+1.65;
        navigate(c,new Vec3(c.player.getX(),diveY,c.player.getZ()),Step.HOVER);
    }
    private static void skipPickup(Minecraft c){
        restoreFootingFlight();minedUnderfoot=false;
        failures++;KitClient.LOGGER.warn("[Gravel] unconfirmed pickup block={} before={} current={} drop={} failures={}",
            mined,beforeMine,count(c),dropId,failures);
        if(failures>=3){stop(c,"连续三次未确认入包，请检查网络后再试");return;}
        if(mined!=null)blockedTargets.add(mined);
        mined=null;dropId=null;dropPose=null;step=Step.FIND;status="跳过未确认掉落，检查下一块";
    }

    private static ItemEntity freshDrop(Minecraft c){
        if(mined==null)return null;
        return c.level.getEntitiesOfClass(ItemEntity.class,new net.minecraft.world.phys.AABB(mined).inflate(6),
            e->e.isAlive()&&e.getItem().is(Items.GRAVEL)
                &&e.getItem().getCount()>beforeDrops.getOrDefault(e.getUUID(),0))
            .stream().min(Comparator.comparingDouble(e->e.distanceToSqr(c.player))).orElse(null);
    }
    private static boolean pickupReceived(Minecraft c){
        if(mined==null)return false;
        ItemEntity remaining=freshDrop(c);
        if(dropId!=null&&remaining!=null&&remaining.getUUID().equals(dropId))return false;
        return GravelCollectionPolicy.confirmedPickup(!c.level.getBlockState(mined).is(Blocks.GRAVEL),
            count(c)-beforeMine,remaining!=null);
    }

    private static BlockPos below(Minecraft c,int x,int z){
        int sea=c.level.getSeaLevel();
        for(int y=sea-6;y>=sea-depth;y--){BlockPos p=new BlockPos(x,y,z);
            if(!c.level.hasChunkAt(p))return null;
            if(exposed(c,p)&&supported(c,p)&&clearWater(c,p))return p;
        }return null;
    }
    private static boolean clearWater(Minecraft c,BlockPos p){
        for(int y=p.getY()+1;y<c.level.getSeaLevel();y++){
            BlockPos q=new BlockPos(p.getX(),y,p.getZ());
            if(!c.level.hasChunkAt(q)||!c.level.getFluidState(q).is(FluidTags.WATER)
                    ||!c.level.getBlockState(q).getCollisionShape(c.level,q).isEmpty())return false;
        }
        for(int y=c.level.getSeaLevel();y<=returnY+1;y++){
            BlockPos q=new BlockPos(p.getX(),y,p.getZ());
            if(!c.level.hasChunkAt(q)||!c.level.getFluidState(q).isEmpty()
                    ||!c.level.getBlockState(q).getCollisionShape(c.level,q).isEmpty())return false;
        }return true;
    }
    private static boolean exposed(Minecraft c,BlockPos p){return p!=null
        &&p.getY()>=c.level.getSeaLevel()-depth
        &&Math.abs(p.getX()+.5-origin.x)<=radius+.75&&Math.abs(p.getZ()+.5-origin.z)<=radius+.75
        &&c.level.hasChunkAt(p)
        &&c.level.getBlockState(p).is(Blocks.GRAVEL)&&c.level.getFluidState(p.above()).is(FluidTags.WATER);}
    private static boolean supported(Minecraft c,BlockPos p){
        for(int x=-1;x<=1;x++)for(int z=-1;z<=1;z++){
            boolean floor=false;
            for(int d=1;d<=2;d++){BlockPos q=p.offset(x,-d,z);
                if(!c.level.hasChunkAt(q)||c.level.getFluidState(q).is(FluidTags.LAVA))return false;
                if(!c.level.getBlockState(q).getCollisionShape(c.level,q).isEmpty()){floor=true;break;}}
            if(!floor)return false;
        }return true;
    }
    private static double routineTravelY(Minecraft c,double x,double z){
        if(nearThreat(c))return parkY;
        double dx=x-c.player.getX(),dz=z-c.player.getZ();
        int steps=Math.max(1,(int)Math.ceil(Math.hypot(dx,dz)));
        for(int i=0;i<=steps;i++){
            int cx=(int)Math.floor(c.player.getX()+dx*i/steps);
            int cz=(int)Math.floor(c.player.getZ()+dz*i/steps);
            BlockPos sample=new BlockPos(cx,c.level.getSeaLevel()+2,cz);
            if(!c.level.hasChunkAt(sample)||c.level.getHeight(
                    net.minecraft.world.level.levelgen.Heightmap.Types.MOTION_BLOCKING,cx,cz)>c.level.getSeaLevel()+1)
                return parkY;
        }
        return returnY+1;
    }
    private static boolean settled(Minecraft c){
        Vec3 now=c.player.position();stable=settlePos!=null&&horizontal(now,settlePos)<.025
            &&Math.abs(now.y-settlePos.y)<.08&&Math.abs(c.player.getDeltaMovement().y)<.12?stable+1:0;settlePos=now;
        if(stable>=6)return true;
        if(ticks-phaseSince>100)stop(c,"移动未稳定，先回到安全高度");
        return false;
    }
    private static void navigate(Minecraft c,Vec3 point,Step after){
        navigate(c,point,after,1);
    }
    private static void navigate(Minecraft c,Vec3 point,Step after,double arrival){
        var p=target(point);p.addProperty("arrival",arrival);p.addProperty("seconds",30);
        issue(c,"navigate",p,after);
    }
    private static void issue(Minecraft c,String op,JsonObject p,Step after){session.submit(c,op,p);next=after;phaseSince=ticks;}
    private static void safeExit(Minecraft c,String reason){
        restoreFootingFlight();
        if(c.player!=null&&c.player.isUnderWater()){
            running=false;status=reason;
            var own=session;session=null;
            if(own!=null)try{own.safeLogout(c,"沙砾采集安全退出："+reason);}
            catch(Exception error){
                KitClient.LOGGER.warn("[Gravel] safe exit failed: {}",message(error));
                try{own.snapshot(c);own.safeLogout(c,"沙砾采集安全退出重试");}
                catch(Exception handedOff){
                    status="采集已停止，控制已交还；请注意水下氧气";
                    if(c.player!=null&&c.player.isUnderWater())c.gui.setOverlayMessage(
                        net.minecraft.network.chat.Component.literal(status).withColor(0xFFAA66),false);
                }
            }
        }else cancel(c,reason);
    }
    private static String preflight(Minecraft c){
        if(c.player==null||c.level==null)return "请先进入世界";
        if(c.gameMode==null||c.gameMode.getPlayerMode()!=net.minecraft.world.level.GameType.SURVIVAL)return "请在生存模式使用采集功能";
        if(!KitClient.config().gravelWaterMode)return "请切换到水下采集方式，或打开陆地找矿设置";
        if(!c.level.dimension().identifier().toString().equals("minecraft:overworld"))return "水下沙砾采集仅用于主世界海床";
        String server=c.getCurrentServer()==null?"":c.getCurrentServer().ip;
        if(!GravelCollectionPolicy.allowedWorld(c.getSingleplayerServer()!=null,server))return "当前服务器尚未确认允许自动采集，请使用本地世界";
        if(dev.twob2tkit.combat.EmergencyExit.held(c))return "请先解除安全离线锁";
        if(c.player.isUnderWater()||c.player.getY()<c.level.getSeaLevel()+1)return "请先到海面上方再开始";
        if(c.player.getHealth()<20||c.player.getFoodData().getFoodLevel()<18)return "请先恢复满血并吃饱";
        ItemStack head=c.player.getItemBySlot(EquipmentSlot.HEAD),feet=c.player.getItemBySlot(EquipmentSlot.FEET);
        if(enchantment(head,"respiration")<3||enchantment(head,"aqua_affinity")<1)return "需要水下呼吸 III、水下速掘头盔";
        if(enchantment(feet,"depth_strider")<3)return "需要深海探索者 III 靴子";
        if(toolId(c)==null)return "需要耐久至少 100、带精准采集的铲子";
        boolean food=false;for(int i=0;i<36;i++)if(c.player.getInventory().getItem(i).has(net.minecraft.core.component.DataComponents.FOOD)){food=true;break;}
        if(!food)return "请带上食物，供自动保护补充饥饿值";
        if(room(c)<=0)return "背包没有沙砾空间";
        return null;
    }
    private static boolean usableShovel(ItemStack s){return s.is(ItemTags.SHOVELS)
        &&s.getMaxDamage()-s.getDamageValue()>=100&&enchantment(s,"silk_touch")>0;}
    private static int toolSlot(Minecraft c){int selected=c.player.getInventory().getSelectedSlot();
        if(usableShovel(c.player.getMainHandItem()))return selected;
        for(int i=0;i<36;i++)if(usableShovel(c.player.getInventory().getItem(i)))return i;return -1;}
    private static String toolId(Minecraft c){int slot=toolSlot(c);return slot<0?null:
        net.minecraft.core.registries.BuiltInRegistries.ITEM.getKey(c.player.getInventory().getItem(slot).getItem()).toString();}
    private static int enchantment(ItemStack s,String name){for(var h:s.getEnchantments().keySet())
        if(h.unwrapKey().map(k->k.identifier().toString()).orElse("").equals("minecraft:"+name))return s.getEnchantments().getLevel(h);return 0;}
    private static int count(Minecraft c){int n=0;for(int i=0;i<36;i++){var s=c.player.getInventory().getItem(i);if(s.is(Items.GRAVEL))n+=s.getCount();}return n;}
    private static int room(Minecraft c){int n=0;for(int i=0;i<36;i++){var s=c.player.getInventory().getItem(i);if(s.isEmpty())n+=64;else if(s.is(Items.GRAVEL))n+=Math.max(0,s.getMaxStackSize()-s.getCount());}return n;}
    private static boolean nearThreat(Minecraft c){return c.level.getEntities(c.player,c.player.getBoundingBox().inflate(12),e->e instanceof Enemy&&e.isAlive()).stream().anyMatch(c.player::hasLineOfSight);}
    private static boolean breathing(Minecraft c){return c.player.hasEffect(net.minecraft.world.effect.MobEffects.WATER_BREATHING)||c.player.hasEffect(net.minecraft.world.effect.MobEffects.CONDUIT_POWER);}
    private static void restoreFootingFlight(){
        if(footingFlightDisabled){MeteorModules.enable(MeteorModules.FLIGHT);footingFlightDisabled=false;}
    }
    private static double horizontal(Vec3 a,Vec3 b){return Math.hypot(a.x-b.x,a.z-b.z);}
    private static int number(JsonObject j,String k,int fallback){return j.has(k)?j.get(k).getAsInt():fallback;}
    private static String text(JsonObject j,String k){return j.has(k)?j.get(k).getAsString():"";}
    private static String message(Exception e){return e.getMessage()==null?e.getClass().getSimpleName():e.getMessage();}
    private static String friendly(String detail){
        if(detail.codePoints().anyMatch(v->v>=0x4e00&&v<=0x9fff))return detail;
        String s=detail.toLowerCase(Locale.ROOT);
        if(s.contains("interface")||s.contains("controller")||s.contains("control"))return "其他操作已接管，请停稳后再开始";
        if(s.contains("air")||s.contains("oxygen")||s.contains("water"))return "返气或拾取条件发生变化，先返回安全位置";
        if(s.contains("guard")||s.contains("health"))return "防护正在处理威胁，请恢复后再开始";
        if(s.contains("loaded")||s.contains("chunk"))return "附近区域尚未加载，请稍后再试";
        if(s.contains("item")||s.contains("shovel"))return "铲子或背包物品发生变化，请检查装备";
        return "当前动作未能完成，已停止继续采集";
    }
    private static JsonObject args(String k,String v){var j=new JsonObject();j.addProperty(k,v);return j;}
    private static JsonArray ints(BlockPos p){var a=new JsonArray();a.add(p.getX());a.add(p.getY());a.add(p.getZ());return a;}
    private static JsonObject target(Vec3 p){var j=new JsonObject();var a=new JsonArray();a.add(p.x);a.add(p.y);a.add(p.z);j.add("target",a);return j;}
    private static String shortStatus(Minecraft c){return c.player.isUnderWater()?"氧气 "+(int)Math.ceil(10.0*c.player.getAirSupply()/c.player.getMaxAirSupply())+"/10":status;}
}
