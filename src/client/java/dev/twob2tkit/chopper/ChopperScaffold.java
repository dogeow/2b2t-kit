package dev.twob2tkit.chopper;

import dev.twob2tkit.runtime.engine.BorerAreaFlightSession;
import dev.twob2tkit.runtime.engine.BorerAim;
import dev.twob2tkit.runtime.engine.BorerFlyPath;
import dev.twob2tkit.runtime.engine.BorerMiningConfirmation;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.Items;
import net.minecraft.world.item.ShovelItem;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.Vec3;
import java.nio.file.*;
import java.util.*;

/** Fly to one floating work platform, stand to mine, then hover to dismantle before returning safely. */
final class ChopperScaffold {
    enum Phase { READY, TRAVEL, PLACE, CONFIRM, LAND, CLEAN, BREAK, RETURN, RETURN_LAND }
    private Phase phase=Phase.READY, afterTravel=Phase.PLACE;
    private final BorerAreaFlightSession flight=new BorerAreaFlightSession();
    private final BorerMiningConfirmation confirmation=new BorerMiningConfirmation();
    private final LinkedHashSet<BlockPos> owned=new LinkedHashSet<>();
    private List<BlockPos> route=List.of(); private int node, idle, ticks;
    private double best=Double.POSITIVE_INFINITY;
    private int bodyWait, recoveryAttempts;
    private Vec3 recoveryOrigin;
    private Vec3 destination;
    private BlockPos cell, home, lastGround, lastWork;
    private Set<BlockPos> lastWorkLogs=Set.of();private final Set<BlockPos> excludedWork=new HashSet<>();
    private Set<BlockPos> pendingTree=Set.of();
    private String scope, status=""; private Path receipt;
    private boolean landingHome, naturalWork;
    String status(){return status;}
    boolean busy(){return phase!=Phase.READY;}
    boolean hasBlocks(){return !owned.isEmpty();}
    int count(){return owned.size();}
    boolean cleaning(){return phase==Phase.CLEAN||phase==Phase.BREAK||landingHome;}
    boolean workingAboveGround(){return home!=null;}
    BlockPos groundOrigin(){return lastGround;}
    private static String scope(Minecraft c){
        String server=c.getCurrentServer()!=null?c.getCurrentServer().ip:c.getSingleplayerServer()!=null?c.getSingleplayerServer().getWorldData().getLevelName():"local";
        if(server.endsWith(":25565"))server=server.substring(0,server.length()-6);
        return server+"|"+c.level.dimension().identifier();
    }
    void start(Minecraft c){
        scope=scope(c);owned.clear();home=lastGround=lastWork=null;lastWorkLogs=Set.of();excludedWork.clear();phase=Phase.READY;pendingTree=Set.of();landingHome=false;
        String id=UUID.nameUUIDFromBytes(scope.getBytes(java.nio.charset.StandardCharsets.UTF_8)).toString();
        receipt=c.gameDirectory.toPath().resolve("config/twob2tkit/chopper-supports/"+id+".txt");
        try {
            if(Files.exists(receipt))for(String row:Files.readAllLines(receipt)){
                if(row.isBlank())continue;
                String[] xyz=row.split(" ");
                if(xyz.length==4&&xyz[0].equals("home")){home=new BlockPos(Integer.parseInt(xyz[1]),Integer.parseInt(xyz[2]),Integer.parseInt(xyz[3]));continue;}
                if(xyz.length!=3)throw new IllegalStateException("垫脚块记录损坏，未开始砍树");
                owned.add(new BlockPos(Integer.parseInt(xyz[0]),Integer.parseInt(xyz[1]),Integer.parseInt(xyz[2])));
            }
            if(!owned.isEmpty())beginCleanup(); else home=null;
        }catch(Exception e){throw new IllegalStateException("无法读取上次工作平台记录",e);}
    }
    void stop(Minecraft c){
        ChopperKeys.holdStill(c);
        if(c.player!=null&&!c.player.onGround())flight.closeKeepingFlight();else flight.close();
        phase=Phase.READY;pendingTree=Set.of();ticks=bodyWait=0;route=List.of();
    }
    void beginCleanup(){pendingTree=Set.of();landingHome=true;phase=Phase.CLEAN;ticks=0;}
    void moveToTree(Minecraft c,Collection<BlockPos> logs){
        checkWorld(c);pendingTree=Set.copyOf(logs);landingHome=false;
        if(pendingTree.equals(lastWorkLogs)&&lastWork!=null)excludedWork.add(lastWork);else excludedWork.clear();
        if(excludedWork.size()>12)throw new IllegalStateException("这片树冠仍有 "+logs.size()+" 根无法到达，已停止，未计为完成");
        if(home==null)home=findGround(c,pendingTree.stream().mapToInt(BlockPos::getY).min().orElse(c.player.getBlockY()));
        if(home==null)throw new IllegalStateException("附近没有确认安全的落地点，尚未放置平台");
        lastGround=home;
        acquire(c);
        if(!owned.isEmpty()){phase=Phase.CLEAN;ticks=0;}else planWork(c);
    }
    private void acquire(Minecraft c){
        flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/chopper-flight-speed.bak"));
        String error=flight.acquire(c.player);if(error!=null)throw new IllegalStateException(error);flight.fly();flight.hover();
    }
    private void planWork(Minecraft c){
        acquire(c);
        var plan=ChopperPlatformPlan.choose(world(c),c.player.position(),pendingTree,BorerAim.breakReach(c.player),excludedWork);
        if(plan==null)throw new IllegalStateException("没有可安全到达的工作位，仍剩 "+pendingTree.size()+" 根原木；没有跳过当前树冠");
        lastWork=plan.feet();lastWorkLogs=pendingTree;
        cell=plan.feet().below();naturalWork=!plan.platform();
        if(!naturalWork&&!selectDirt(c))throw new IllegalStateException("背包需要至少一块泥土作为悬空工作平台");
        travel(c,plan.route(),Vec3.atBottomCenterOf(plan.feet()).add(0,.12,0),naturalWork?Phase.LAND:Phase.PLACE);
        log(c,"air-work-plan cell="+cell+" floating="+plan.platform()+" coverage="+plan.reachable()+" remaining="+pendingTree.size()+" nodes="+plan.route().size());
    }
    private void travel(Minecraft c,List<BlockPos> path,Vec3 to,Phase next){
        route=path;node=0;destination=to;afterTravel=next;phase=Phase.TRAVEL;idle=ticks=bodyWait=recoveryAttempts=0;recoveryOrigin=null;best=Double.POSITIVE_INFINITY;
    }
    private void travelTo(Minecraft c,Vec3 to,Phase next){
        var path=BorerFlyPath.findExact(world(c),c.player.blockPosition(),BlockPos.containing(to),24,12000);
        if(path.nodes().isEmpty())throw new IllegalStateException("工作平台之间的通道受阻，已保留清理记录");
        travel(c,path.nodes(),to,next);
    }
    boolean tick(Minecraft c){
        if(!busy())return false;
        checkWorld(c);var p=c.player;ChopperKeys.releaseWalk(c);
        if(phase!=Phase.BREAK)ChopperKeys.releaseMine(c);
        ticks++;
        if(phase!=Phase.TRAVEL&&ticks>160)throw new IllegalStateException("工作平台步骤超时："+status+"；清理记录已保留");
        if(phase==Phase.TRAVEL){
            status=landingHome?"沿畅通空间返回落地点":"飞向树冠旁的工作位";
            String error=flight.acquire(p);if(error!=null)throw new IllegalStateException(error);flight.fly();
            while(node<route.size()&&reached(p.position(),BorerFlyPath.waypoint(route.get(node)),.08)){node++;best=Double.POSITIVE_INFINITY;idle=0;}
            Vec3 target=node<route.size()?BorerFlyPath.waypoint(route.get(node)):destination;
            if(node==route.size()&&reached(p.position(),destination,.025)){
                flight.hover();phase=afterTravel;ticks=0;return true;
            }
            var input=BorerFlyPath.input(p.position(),target,p.getYRot());
            if(node==route.size()&&input.speed()==0&&!reached(p.position(),destination,.025)){
                double dy=destination.y-p.getY();
                if(Math.abs(dy)>.025){
                    double speed=Math.min(.02,Math.abs(dy)*.12);
                    input=new BorerFlyPath.Input(p.getYRot(),false,dy>0,dy<0,speed,new Vec3(0,Math.copySign(speed*5,dy),0));
                }else{flight.hover();phase=afterTravel;ticks=0;return true;}
            }
            if(!safeMove(c,input.delta()))return true;
            double distance=p.position().distanceTo(target);
            if(distance<best-.025){best=distance;idle=0;}else if(++idle>100)throw new IllegalStateException("工作位飞行无进展，原木未清完，已停止");
            dev.twob2tkit.runtime.api.RotationAim.apply(p,input.yaw(),0);ChopperKeys.lookAt(p,p.getEyePosition().add(-Math.sin(Math.toRadians(input.yaw())),0,Math.cos(Math.toRadians(input.yaw()))));
            flight.speed(input.speed());c.options.keyUp.setDown(input.forward());c.options.keyJump.setDown(input.up());c.options.keyShift.setDown(input.down());return true;
        }
        if(phase==Phase.PLACE){
            status="隔空放置一块泥土工作平台";flight.hover();
            if(!replaceable(c,cell))throw new IllegalStateException("工作位已有方块，未覆盖它");
            if(!selectDirt(c))throw new IllegalStateException("泥土用完，未继续飞行");
            owned.add(cell.immutable());save();ChopperKeys.lookAt(p,Vec3.atCenterOf(cell));meteorPlace(c,cell);
            phase=Phase.CONFIRM;ticks=0;return true;
        }
        if(phase==Phase.CONFIRM){
            status="等待服务器确认悬空平台";flight.hover();
            var result=ChopperSupportPolicy.placement(confirmation.pending(c.level,cell),c.level.getBlockState(cell).is(Blocks.DIRT),ticks);
            if(result==ChopperSupportPolicy.Confirmation.WAIT)return true;
            if(result==ChopperSupportPolicy.Confirmation.STOP)throw new IllegalStateException("服务器未确认隔空放置，保持悬停并停止");
            log(c,"air-platform-confirmed cell="+cell+" owned="+owned.size()+" gapBelow="+c.level.getBlockState(cell.below()).isAir());
            phase=Phase.LAND;ticks=0;
        }
        if(phase==Phase.LAND){
            status="站稳在工作平台上继续砍树";flight.digOnFoot();
            if(p.onGround()){phase=Phase.READY;ticks=0;}return true;
        }
        if(phase==Phase.CLEAN){
            acquire(c);status="先悬停，再回收悬空平台";
            if(owned.isEmpty()){
                if(!pendingTree.isEmpty()){planWork(c);return true;}
                if(home==null)home=findGround(c);
                if(home==null)throw new IllegalStateException("找不到安全落地点，已保持飞行");
                landingHome=true;travelTo(c,Vec3.atBottomCenterOf(home).add(0,.12,0),Phase.RETURN_LAND);return true;
            }
            cell=owned.iterator().next();
            if(confirmation.pending(c.level,cell))return true;
            if(!c.level.getBlockState(cell).is(Blocks.DIRT)){owned.remove(cell);save();ticks=0;return true;}
            travelTo(c,Vec3.atBottomCenterOf(cell.above()).add(0,.12,0),Phase.BREAK);return true;
        }
        if(phase==Phase.BREAK){
            status="悬停拆除本次放置的泥土";
            String error=flight.acquire(p);if(error!=null)throw new IllegalStateException(error);flight.hover();
            if(confirmation.pending(c.level,cell)){ChopperKeys.releaseMine(c);return true;}
            if(!c.level.getBlockState(cell).is(Blocks.DIRT)){
                owned.remove(cell);save();log(c,"air-platform-removed cell="+cell+" remaining="+owned.size());
                ChopperKeys.releaseMine(c);phase=Phase.CLEAN;ticks=0;return true;
            }
            var hit=BorerAim.firstMineable(c,p,cell,b->b.equals(cell));
            if(hit==null)throw new IllegalStateException("平台被遮挡，未挖其他方块");
            selectShovel(c);ChopperKeys.lookAt(p,BorerAim.lookAlongRay(p.getEyePosition(),hit));c.hitResult=hit;c.crosshairPickEntity=null;c.options.keyAttack.setDown(false);
            if(ticks==1)c.gameMode.startDestroyBlock(cell,hit.getDirection());else c.gameMode.continueDestroyBlock(cell,hit.getDirection());return true;
        }
        if(phase==Phase.RETURN_LAND){
            status="安全落地后拾取掉落物";
            if(!floor(c,home.below()))throw new IllegalStateException("原落地点已变化，保持悬停");
            flight.digOnFoot();if(p.onGround()){flight.close();home=null;landingHome=false;phase=Phase.READY;save();}return true;
        }
        return true;
    }
    /** Check only actual hazards here. Geometry uses the swept collision shape, not whole-block emptiness. */
    private boolean safeMove(Minecraft c,Vec3 delta){
        var p=c.player;var swept=p.getBoundingBox().expandTowards(delta).deflate(.001);
        BlockPos waitCell=null;ChopperFlightSafety.Kind waitKind=null;
        for(BlockPos b:BlockPos.betweenClosed(BlockPos.containing(swept.minX,swept.minY,swept.minZ),
            BlockPos.containing(swept.maxX,swept.maxY,swept.maxZ))){
            var kind=cellKind(c,b);
            var action=ChopperFlightSafety.action(kind,bodyWait);
            if(action==ChopperFlightSafety.Action.STOP){
                flight.hover();String detail=describeCell(c,b,kind);
                log(c,"air-travel-stop kind="+kind+" "+detail+" waitTicks="+bodyWait+" player="+p.position());
                throw new IllegalStateException((kind==ChopperFlightSafety.Kind.PENDING?"服务器尚未确认 ":kind==ChopperFlightSafety.Kind.UNLOADED?"区块尚未加载 ":"前方有 ")+detail+(kind==ChopperFlightSafety.Kind.PENDING||kind==ChopperFlightSafety.Kind.UNLOADED?"，等待超时，已停下":"，已停下"));
            }
            if(action==ChopperFlightSafety.Action.WAIT){waitCell=b.immutable();waitKind=kind;}
        }
        if(waitCell!=null){
            flight.hover();idle=0;
            status=(waitKind==ChopperFlightSafety.Kind.PENDING?"等待服务器确认 ":"等待区块加载 ")+describeCell(c,waitCell,waitKind);
            if(bodyWait++==0||bodyWait%40==0)log(c,"air-travel-wait kind="+waitKind+" "+describeCell(c,waitCell,waitKind)+" ticks="+bodyWait+" player="+p.position());
            return false;
        }
        if(bodyWait>0){log(c,"air-travel-resumed waited="+bodyWait);bodyWait=0;}
        if(!c.level.noCollision(p,swept)){
            return recoverCollision(c,delta);
        }
        return true;
    }
    private boolean safeBox(Minecraft c,net.minecraft.world.phys.AABB box){
        var interior=box.deflate(.001);
        if(!c.level.noCollision(c.player,interior))return false;
        for(BlockPos b:BlockPos.betweenClosed(BlockPos.containing(interior.minX,interior.minY,interior.minZ),BlockPos.containing(interior.maxX,interior.maxY,interior.maxZ)))
            if(cellKind(c,b)!=ChopperFlightSafety.Kind.CLEAR)return false;
        return true;
    }
    private boolean recoverCollision(Minecraft c,Vec3 wanted){
        var p=c.player;flight.hover();
        if(recoveryOrigin==null||p.position().distanceToSqr(recoveryOrigin)>1){recoveryOrigin=p.position();recoveryAttempts=0;}
        if(++recoveryAttempts>6)throw new IllegalStateException("同一处碰撞多次调整仍无法通过，已悬停；未跳过剩余原木");
        Vec3 lift=ChopperCollisionRecovery.clearanceLift(wanted,
            h->safeBox(c,p.getBoundingBox().expandTowards(0,h,0)),
            h->safeBox(c,p.getBoundingBox().move(0,h,0).expandTowards(wanted)));
        if(lift!=null){
            log(c,"air-travel-clearance-lift delta="+lift+" attempt="+recoveryAttempts+" node="+(node<route.size()?route.get(node):destination)+" player="+p.position());
            flight.speed(lift.y/5);c.options.keyJump.setDown(true);c.options.keyShift.setDown(false);
            status="稍微抬高，避开地形边缘";idle=0;return false;
        }
        var replanned=BorerFlyPath.findExact(world(c),p.blockPosition(),BlockPos.containing(destination),24,12000);
        if(!replanned.nodes().isEmpty()){
            // Preserve recovery attempts across replans; rebuilding the same path is not progress.
            route=replanned.nodes();node=0;idle=bodyWait=0;best=Double.POSITIVE_INFINITY;
            status="遇到障碍，正在换一条安全路线";
            log(c,"air-travel-replanned nodes="+route.size()+" attempt="+recoveryAttempts+" target="+destination+" player="+p.position());
            return false;
        }
        log(c,"air-travel-no-route target="+destination+" player="+p.position());
        throw new IllegalStateException("障碍周围没有可通行路线，已悬停；未跳过剩余原木");
    }
    private ChopperFlightSafety.Kind cellKind(Minecraft c,BlockPos b){
        boolean inside=b.getY()>=c.level.getMinY()&&b.getY()<c.level.getMaxY();
        boolean loaded=inside&&c.level.hasChunkAt(b);
        if(!loaded)return ChopperFlightSafety.classify(false,inside,false,false,false,false,false);
        var state=c.level.getBlockState(b);
        return ChopperFlightSafety.classify(true,true,confirmation.pending(c.level,b),!state.getFluidState().isEmpty(),
            state.is(Blocks.FIRE)||state.is(Blocks.SOUL_FIRE),state.is(Blocks.COBWEB),state.is(Blocks.POWDER_SNOW));
    }
    private String describeCell(Minecraft c,BlockPos b,ChopperFlightSafety.Kind kind){
        String label=c.level.hasChunkAt(b)?c.level.getBlockState(b).getBlock().getName().getString():"未加载方块";
        return label+"（"+b.getX()+"，"+b.getY()+"，"+b.getZ()+"）";
    }
    private void checkWorld(Minecraft c){if(!scope.equals(scope(c)))throw new IllegalStateException("世界已变化，原世界平台清理记录已保留");}
    private static boolean reached(Vec3 a,Vec3 b,double tolerance){return Math.abs(a.x-b.x)<tolerance&&Math.abs(a.y-b.y)<tolerance&&Math.abs(a.z-b.z)<tolerance;}
    private BlockPos findGround(Minecraft c){return findGround(c,Integer.MAX_VALUE);}
    private BlockPos findGround(Minecraft c,int maxFeet){
        var origin=c.player.blockPosition();List<BlockPos> choices=new ArrayList<>();
        for(int x=-6;x<=6;x++)for(int z=-6;z<=6;z++)for(int y=2;y>=-40;y--){
            BlockPos p=origin.offset(x,y,z);if(p.getY()<=maxFeet&&clear(c,p)&&clear(c,p.above())&&floor(c,p.below())){choices.add(p);break;}
        }
        choices.sort(Comparator.comparingDouble(b->c.player.position().distanceToSqr(Vec3.atBottomCenterOf(b))));
        return choices.isEmpty()?null:choices.getFirst();
    }
    private ChopperPlatformPlan.World world(Minecraft c){
        Map<BlockPos,Boolean> air=new HashMap<>(),floor=new HashMap<>();
        return new ChopperPlatformPlan.World(){
            public boolean clear(BlockPos p){return air.computeIfAbsent(p,b->ChopperScaffold.this.clear(c,b));}
            public boolean replaceable(BlockPos p){return ChopperScaffold.replaceable(c,p);}
            public boolean floor(BlockPos p){return floor.computeIfAbsent(p,b->ChopperScaffold.this.floor(c,b));}
        };
    }
    private boolean clear(Minecraft c,BlockPos p){
        if(!c.level.hasChunkAt(p)||p.getY()<c.level.getMinY()||p.getY()>=c.level.getMaxY()||confirmation.pending(c.level,p))return false;
        var s=c.level.getBlockState(p);return s.getCollisionShape(c.level,p).isEmpty()&&s.getFluidState().isEmpty()&&!s.is(Blocks.FIRE)&&!s.is(Blocks.SOUL_FIRE)&&!s.is(Blocks.COBWEB)&&!s.is(Blocks.POWDER_SNOW);
    }
    private boolean floor(Minecraft c,BlockPos p){
        if(!c.level.hasChunkAt(p))return false;var s=c.level.getBlockState(p);
        return s.isFaceSturdy(c.level,p,Direction.UP)&&s.getFluidState().isEmpty()&&!s.is(BlockTags.LEAVES)&&!ChopperTrees.isWood(s)&&!s.is(Blocks.MAGMA_BLOCK)&&!s.is(Blocks.CACTUS);
    }
    private static boolean replaceable(Minecraft c,BlockPos p){var s=c.level.getBlockState(p);return s.isAir()||s.is(Blocks.SHORT_GRASS)||s.is(Blocks.FERN);}

	private void save(){
		try{
			Files.createDirectories(receipt.getParent());Path temp=receipt.resolveSibling(receipt.getFileName()+".tmp");
			StringBuilder b=new StringBuilder();if(home!=null)b.append("home ").append(home.getX()).append(' ').append(home.getY()).append(' ').append(home.getZ()).append('\n');for(BlockPos p:owned)b.append(p.getX()).append(' ').append(p.getY()).append(' ').append(p.getZ()).append('\n');
			Files.writeString(temp,b.toString());Files.move(temp,receipt,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
		}catch(Exception e){throw new IllegalStateException("无法保存垫脚块记录，已停下",e);}
	}
	private static boolean selectDirt(Minecraft c){
		var inv=c.player.getInventory();
		for(int i=0;i<36;i++)if(inv.getItem(i).is(Items.DIRT)){
			if(i<9)inv.setSelectedSlot(i);else c.gameMode.handleContainerInput(c.player.containerMenu.containerId,i,inv.getSelectedSlot(),ContainerInput.SWAP,c.player);
			return c.player.getMainHandItem().is(Items.DIRT);
		}return false;
	}
	private static void selectShovel(Minecraft c){
		var inv=c.player.getInventory();for(int i=0;i<36;i++)if(inv.getItem(i).getItem() instanceof ShovelItem){
			if(i<9)inv.setSelectedSlot(i);else c.gameMode.handleContainerInput(c.player.containerMenu.containerId,i,inv.getSelectedSlot(),ContainerInput.SWAP,c.player);return;
		}
	}
	/** Meteor's normal BlockUtils placement includes its Air Place fallback when no neighbour exists. */
	private static void meteorPlace(Minecraft c,BlockPos p){
		try{
			Class<?> utils=Class.forName("meteordevelopment.meteorclient.utils.world.BlockUtils");
			Object result=utils.getMethod("place",BlockPos.class,InteractionHand.class,int.class,boolean.class,int.class,boolean.class,boolean.class,boolean.class)
				.invoke(null,p,InteractionHand.MAIN_HAND,c.player.getInventory().getSelectedSlot(),false,0,true,true,false);
			if(!Boolean.TRUE.equals(result))throw new IllegalStateException("Meteor 无法在这个位置放置泥土");
		}catch(ReflectiveOperationException e){throw new IllegalStateException("Meteor 放置接口不可用，未模拟成功",e);}
	}
	private static void log(Minecraft c,String s){ChopperFileLog.append(c,AutoChopper.VERSION,s);}
}
