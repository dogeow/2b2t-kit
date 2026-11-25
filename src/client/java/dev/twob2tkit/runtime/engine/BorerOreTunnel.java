package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.SnowLayerBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.Vec3;
import java.util.*;

/** Prove a connected route before mining tunnels; recheck the actual next step before input. */
final class BorerOreTunnel {
	private static final int PLANNING_TICK_LIMIT = 300;
	private final DefaultTunnelBorerEngine engine;
	private final BorerMeteorInstant instant = new BorerMeteorInstant();
	private final BorerAreaPipeline clicks = new BorerAreaPipeline();
	private final Map<BlockPos,net.minecraft.world.level.block.state.BlockState> clickedStates = new HashMap<>();
	private boolean pairRejected;
	private BlockPos singleTap, slowFace;
	private net.minecraft.world.level.block.state.BlockState singleBefore;
	private int sentTick, airTicks, sampledTick;
	private boolean singleRepeat, singleRetried;

	private final BorerAreaFlightSession flight = new BorerAreaFlightSession();
	private BlockPos goal, mining;
	private OreTunnelSearch search;
	private final Map<BlockPos,Integer> observed = new HashMap<>();
	private List<BlockPos> path = List.of();
	private int index, idle, miningTicks, planningTicks;
	private Vec3 last;
	private boolean crossed, onFoot;
	BorerOreTunnel(DefaultTunnelBorerEngine engine) { this.engine=engine; }
	// The task HUD clips the right end of the line on narrower windows.
	static String planningStatus(int checked, int ticks, BlockPos ore) {
		int secondsLeft = (PLANNING_TICK_LIMIT - ticks + 19) / 20;
		return "已查 " + checked + " 个站位 · 规划剩余 " + secondsLeft + " 秒 · " + BorerText.block(ore);
	}

	boolean active() { return goal!=null; }
	void reset() {
		if (onFoot) flight.close(); else flight.closeKeepingFlight();
		onFoot=false;
		clearPlan();
	}
	private void clearPlan() {
		goal=mining=null; search=null; path=List.of(); observed.clear();
		index=idle=miningTicks=planningTicks=0; last=null; crossed=false;
	}
	private boolean floor(Minecraft c,BlockPos b) {
		if (!loaded(c,b) || b.equals(goal)) return false;
		var s=c.level.getBlockState(b);
		return s.getFluidState().isEmpty() && !s.is(Blocks.MAGMA_BLOCK) && !s.is(Blocks.CAMPFIRE)
			&& !s.is(Blocks.SOUL_CAMPFIRE) && s.isFaceSturdy(c.level,b,Direction.UP);
	}
	private boolean safeFeet(Minecraft c, BlockPos pos) {
		return loaded(c,pos.below()) && !BorerHazards.isMagma(c,pos.below());
	}
	/** Gravity can take over only just above a continuous, dry, load-bearing floor. */
	static boolean groundLane(net.minecraft.world.phys.AABB body, Vec3 end,
			java.util.function.Predicate<BlockPos> sturdyFloor) {
		int y = net.minecraft.util.Mth.floor(body.minY + .0001);
		if (body.minY-y > .18 || Math.abs(end.y-y) > .001) return false;
		var sweep=body.expandTowards(end.x-body.getCenter().x,0,end.z-body.getCenter().z);
		for (var b:BlockPos.betweenClosed(BlockPos.containing(sweep.minX+.0001,y-1,sweep.minZ+.0001),
				BlockPos.containing(sweep.maxX-.0001,y-1,sweep.maxZ-.0001))) {
			if (!sturdyFloor.test(b)) return false;
		}
		return true;
	}

	private boolean canWalkDown(Minecraft c, BlockPos from, BlockPos to) {
		var p=c.player;
		if (p.getY()>from.getY()+.18 || p.getY()<to.getY()-.01 || !floor(c,to.below())) return false;
		var body=p.getBoundingBox();
		var sweep=body.expandTowards(to.getX()+.5-p.getX(),0,to.getZ()+.5-p.getZ());
		return BorerLootPolicy.safeApproach(sweep,from.getY(),1,
			column -> BorerHazards.pickupFallDepth(c,column,engine.miningConfirmation));
	}

	private boolean standToMine(Minecraft c) {
		var p=c.player;
		if (!groundLane(p.getBoundingBox(),new Vec3(p.getX(),p.blockPosition().getY(),p.getZ()),b->floor(c,b))) return false;
		if (BorerFlight.isFlying(p)) {
			flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/ore-route-flight-speed.bak"));
			String error=flight.acquire(p);
			if (error!=null) throw new BorerAreaFlightSession.Interrupted(error);
			flight.digOnFoot();
		}
		onFoot=true;
		c.options.keyJump.setDown(false);
		c.options.keyShift.setDown(false);
		return true;
	}

	private void useFlight(Minecraft c) {
		flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/ore-route-flight-speed.bak"));
		String error=flight.acquire(c.player);
		if (error!=null) throw new BorerAreaFlightSession.Interrupted(error);
		flight.fly();
		onFoot=false;
	}
	private boolean loaded(Minecraft c,BlockPos b) {
		return b.getY()>=c.level.getMinY() && b.getY()<c.level.getMaxY() && c.level.hasChunkAt(b)
			&& !engine.miningConfirmation.pending(c.level,b);
	}
    static boolean openRouteCell(BlockState state) {
        // A single snow layer has no player collision. Powder snow is a separate hazard.
        return state.isAir() || state.is(Blocks.SNOW) && state.getValue(SnowLayerBlock.LAYERS) == 1;
    }

	private int cell(Minecraft c,BlockPos b) {
		if (!loaded(c,b)) return -1;
		var s=c.level.getBlockState(b);
		if (openRouteCell(s)) return 0;
		if (s.hasBlockEntity() || s.getBlock() instanceof FallingBlock || !s.getFluidState().isEmpty()
			|| s.is(Blocks.FIRE) || s.is(Blocks.SOUL_FIRE) || s.is(Blocks.POWDER_SNOW)
			|| s.is(Blocks.CACTUS) || s.is(Blocks.MAGMA_BLOCK) || c.level.getBlockState(b.above()).getBlock() instanceof FallingBlock) return -1;
		for (Direction d:Direction.values()) if (!loaded(c,b.relative(d))) return -1;
		return engine.canPlanMine(c,b) ? 1 : -1;
	}
	private boolean fail(Minecraft c,String reason) {
		engine.releaseMine(c); engine.ores.skipActive(c,reason); reset(); return true;
	}

	boolean awaitClicks(Minecraft c) {
		if (singleTap!=null) {
			var p=c.player;
			engine.releaseMine(c);
			boolean loaded=c.level.hasChunkAt(singleTap);
			boolean pending=engine.miningConfirmation.pending(c.level,singleTap);
			var state=c.level.getBlockState(singleTap);
			if (sampledTick!=p.tickCount) {
				sampledTick=p.tickCount;
				airTicks=loaded && !pending && state.isAir() ? airTicks+1 : 0;
			}
			if (airTicks>=2) { singleTap=null; return false; }
			if (resumeSingleFace(p.tickCount-sentTick,loaded,pending,state.equals(singleBefore))) {
				slowFace=singleTap;
				singleTap=null;
				return false;
			}
			if (singleRepeat && !singleRetried && engine.miningModules.instantRebreakRequested()
					&& instant.repeatAllows(p.getMainHandItem().is(net.minecraft.tags.ItemTags.PICKAXES))
					&& p.tickCount-sentTick>=20 && loaded
					&& state.equals(singleBefore) && engine.canPlanMine(c,singleTap)
					&& !engine.isUnsafeFloorMine(c,p,singleTap)) {
				var hit = BorerAim.clipView(c,p);
				if (hit != null && singleTap.equals(hit.getBlockPos()) && BorerAim.hitInReach(p,hit)) {
					singleRetried = true;
					try { instant.finishRepeat(singleTap,hit.getDirection()); }
					catch (IllegalStateException error) {
						engine.stop(c,"单格点挖已暂停："+error.getMessage()); return true;
					}
					engine.fileLog(c,"single-tap-retry block="+singleTap);
				}
			}
			if (p.tickCount-sentTick>=100) engine.stop(c,"单格点挖未获确认，已停挖");
			else engine.overlay(c,"已点一次，正在核对方块",0x55FFFF);
			return true;
		}
		if (!clicks.active()) return false;
		var p=c.player;
		clicks.update(p.tickCount,b->new BorerAreaPipeline.Observation(
			c.level.hasChunkAt(b) && c.level.getBlockState(b).isAir(),engine.miningConfirmation.pending(c.level,b)));
		if (!clicks.active()) { clickedStates.clear(); return false; }
		// These entries all had a registered local break prediction. A solid original
		// state after the prediction is released is a correction, not a pending break.
		for (var b:clicks.positions()) {
			if (c.level.hasChunkAt(b) && !engine.miningConfirmation.pending(c.level,b)
					&& c.level.getBlockState(b).equals(clickedStates.get(b))) {
				clicks.discardCorrected(b);
				pairRejected=true;
				engine.fileLog(c,"tunnel-click-corrected block="+b+"; resume normal mining");
			}
		}
		if (!clicks.active()) { clickedStates.clear(); return false; }
		engine.releaseMine(c);
		if (clicks.expired(p.tickCount)!=null) engine.stop(c,"通道点挖未获确认，已停挖");
		else engine.overlay(c,"通道点挖 · 等待确认 "+clicks.size()+" 格",0x55FFFF);
		return true;
	}

	static boolean resumeSingleFace(int elapsed, boolean loaded, boolean pending, boolean originalSolid) {
		return elapsed>=8 && loaded && !pending && originalSolid;
	}

	static boolean shouldFinishSingleRepeat(boolean repeat, boolean predictedAir) {
		return repeat && !predictedAir;
	}

	boolean trySingleTap(Minecraft c, BlockPos b) {
		var p=c.player;
		if (clicks.active() || singleTap!=null || b.equals(slowFace) || !engine.canPlanMine(c,b)
				|| engine.isUnsafeFloorMine(c,p,b) || engine.miningConfirmation.pending(c.level,b)) return false;
		var state=c.level.getBlockState(b);
		boolean repeat=engine.miningModules.instantRebreakRequested()
			&& instant.repeatAllows(p.getMainHandItem().is(net.minecraft.tags.ItemTags.PICKAXES));
		if (!repeat && !engine.miningModules.hasPausedSpeedMine()
				&& state.getDestroyProgress(p,c.level,b)<1) return false;
		var hit=BorerAim.clipView(c,p);
		if (hit==null || !b.equals(hit.getBlockPos()) || !BorerAim.hitInReach(p,hit)) return false;
		try {
			return engine.miningModules.withSpeedMine(()->{
				if (!repeat && !instant.allows(state.getBlock(),state.getDestroyProgress(p,c.level,b))) return false;
				c.options.keyAttack.setDown(false);
				singleTap=b.immutable(); singleBefore=state; sentTick=p.tickCount; sampledTick=sentTick; airTicks=0;
				singleRepeat=repeat; singleRetried=false;
				engine.miningConfirmation.startObservedBreak(c,b,hit.getDirection());
				if (shouldFinishSingleRepeat(repeat, c.level.getBlockState(b).isAir()))
					instant.finishRepeat(b,hit.getDirection());
				p.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
				engine.fileLog(c,"single-tap block="+b+" repeat="+repeat);
				return true;
			});
		} catch (IllegalStateException error) {
			engine.stop(c,"单格点挖已暂停："+error.getMessage()); return true;
		}
	}

	void clearClicks() { singleTap=slowFace=null; singleBefore=null; clicks.clear(); clickedStates.clear(); pairRejected=false; }

	boolean tryStraightPair(Minecraft c, BlockPos planned) {
		BlockPos from=c.player.blockPosition(), to=from.relative(engine.forward);
		if (planned==null || !(planned.equals(to) || planned.equals(to.above()))) return false;
		if (mining!=null && !mining.equals(to) && !mining.equals(to.above())) mining=null;
		return tryPair(c,from,to);
	}

	private boolean tryPair(Minecraft c, BlockPos from, BlockPos to) {
		var p=c.player;
		if (pairRejected || mining!=null || from.getY()!=to.getY() || from.distManhattan(to)!=1
				|| !clicks.canClick(p.tickCount) || !p.onGround()) return false;
		var pair=List.of(to.above(),to);
		for (var b:pair) {
			if (cell(c,b)!=1 || engine.wantedBlock(c.level.getBlockState(b))
					|| engine.isStandingSupport(c,p,b) || engine.isUnsafeFloorMine(c,p,b)
					|| engine.visibleHitResult(c,p,b)==null) return false;
		}
		if (!engine.place.selectMiningTool(c,p,pair.getFirst())) return true;
		if (!engine.miningModules.hasPausedSpeedMine()
				&& c.level.getBlockState(to).getDestroyProgress(p,c.level,to)<1) return false;
		try {
			return engine.miningModules.withSpeedMine(()->{
				engine.releaseMine(c);
				for (var b:pair) {
					var state=c.level.getBlockState(b);
					if (!engine.canPlanMine(c,b) || engine.miningConfirmation.pending(c.level,b)
							|| !instant.allows(state.getBlock(),state.getDestroyProgress(p,c.level,b))) break;
					var hit=engine.visibleHitResult(c,p,b);
					if (hit==null || !BorerAim.hitInReach(p,hit)) break;
					engine.lookAtMiningHit(c,p,hit);
					var actual=BorerAim.clipView(c,p);
					if (actual==null || !actual.getBlockPos().equals(b) || !BorerAim.hitInReach(p,actual)
							|| clicks.blocksRay(p.getEyePosition(),actual.getLocation(),b)) break;
					engine.miningConfirmation.startObservedBreak(c,b,actual.getDirection());
					if (!c.level.getBlockState(b).isAir() && !engine.miningConfirmation.pending(c.level,b)) {
						// Vanilla started normal progressive mining. Keep this face for the ordinary cadence.
						mining=b; miningTicks=0;
						engine.status="此格需要持续开挖";
						return true;
					}
					if (!engine.miningConfirmation.pending(c.level,b))
						throw new IllegalStateException("通道点挖未登记服务器确认");
					clicks.submitTunnelClick(b,p.tickCount);
					clickedStates.put(b.immutable(),state);
					p.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
				}
				if (clicks.active()) engine.overlay(c,"通道点挖 · 已点 "+clicks.size()+" 格",0x55FFFF);
				return clicks.active();
			});
		} catch (IllegalStateException error) {
			engine.stop(c,"通道点挖已暂停："+error.getMessage());
			return true;
		}
	}

	/** Stay at the current stance while a visible face on this straight, planned run is reachable. */
	static int clearanceIndex(List<BlockPos> route, int cursor, int maxSteps,
			java.util.function.ToIntFunction<BlockPos> inspectSlice) {
		int start=Math.max(1,cursor);
		BlockPos heading=null;
		for (int i=start; i<route.size() && i-start<maxSteps; i++) {
			BlockPos delta=route.get(i).subtract(route.get(i-1));
			if (delta.getY()!=0 || delta.distManhattan(BlockPos.ZERO)!=1
					|| heading!=null && !heading.equals(delta)) break;
			heading=delta;
			int state=inspectSlice.applyAsInt(route.get(i));
			if (state>0) return i;
			if (state<0) break;
		}
		return cursor;
	}

	private int inspectSlice(Minecraft c, BlockPos feet) {
		boolean occupied=false, reachable=false;
		for (BlockPos b:List.of(feet.above(),feet)) {
			int kind=cell(c,b);
			if (kind<0) return -1;
			if (kind==0) continue;
			occupied=true;
			if (engine.isStandingSupport(c,c.player,b) || engine.isUnsafeFloorMine(c,c.player,b)) return -1;
			if (BorerAim.inReach(c.player,b) && engine.visibleHitResult(c,c.player,b)!=null) reachable=true;
		}
		return reachable ? 1 : occupied ? -1 : 0;
	}

    boolean tick(Minecraft c, BlockPos ore) {
        return handleFlightInterruption(() -> tickRoute(c,ore),
            reason -> engine.stop(c,"找矿已暂停："+reason));
    }

    static boolean handleFlightInterruption(java.util.function.BooleanSupplier routeTick,
            java.util.function.Consumer<String> stop) {
        try {
            return routeTick.getAsBoolean();
        } catch (BorerAreaFlightSession.Interrupted interrupted) {
            stop.accept(interrupted.getMessage());
            return true;
        }
    }

    private boolean tickRoute(Minecraft c, BlockPos ore) {
		var p=c.player;
		if (ore==null) { if (active() || onFoot) reset(); return false; }
		if (!engine.wantedBlock(c.level.getBlockState(ore))) return fail(c,"目标矿石已经变化，重新选矿");
		if (engine.inMiningReach(p,ore) && engine.canSeeBlock(c,p,ore) && cell(c,ore)==1
			&& !engine.isUnsafeFloorMine(c,p,ore) && floor(c,ore.below()) && !ore.equals(p.blockPosition().below())) {
			if (standToMine(c)) {
				if (active()) clearPlan();
				if (!p.onGround()) { engine.releaseMine(c); return true; }
			} else if (active()) reset();
			if (!ore.equals(engine.currentTarget)) engine.setMiningTarget(c,p,ore,"verified-ore-face");
			return false;
		}
		if (!ore.equals(goal)) {
			if (onFoot) clearPlan(); else reset();
            BlockPos start = p.blockPosition();
            for (BlockPos b : OreTunnelSearch.clearance(start, start)) {
                if (cell(c,b) == 0) continue;
                engine.stop(c,"当前站位受阻 "+BorerText.block(b)+"，请移到安全空位后继续挖矿");
                return true;
            }
            goal=ore.immutable(); search=new OreTunnelSearch(start,goal);
            engine.clearMiningTarget(c,"plan-full-ore-route");
			if (cell(c,goal)!=1 || !floor(c,goal.below())) return fail(c,"矿石或掉落点未通过安全预检");
		}
		if (search!=null) {
			standToMine(c);
			engine.releaseMine(c);
			if (Runtime.getRuntime().maxMemory()-(Runtime.getRuntime().totalMemory()-Runtime.getRuntime().freeMemory())<32L*1024*1024)
				return fail(c,"规划内存不足，未确认完整路线");
			if (++planningTicks > PLANNING_TICK_LIMIT) {
				engine.ores.skipActive(c,"完整路线规划已用 300 拍，暂缓此矿脉，两分钟后可重试",2400);
				reset();
				return true;
			}
			search.advance(new OreTunnelSearch.World() {
				public int cell(BlockPos b) { return observed.computeIfAbsent(b,k->BorerOreTunnel.this.cell(c,k)); }
				public boolean floor(BlockPos b) { return BorerOreTunnel.this.floor(c,b); }
				public boolean safeFeet(BlockPos b) { return BorerOreTunnel.this.safeFeet(c,b); }
			},96,System.nanoTime()+2_000_000);
			engine.overlay(c, planningStatus(search.expanded(), planningTicks, goal), 0x55FFFF);
			if (!search.done) return true;
			path=search.path; search=null; observed.clear();
			if (path.isEmpty()) return fail(c,"已加载地形内没有到矿石的安全路线");
			engine.fileLog(c,"full-ore-route goal="+goal+" steps="+path.size());
		}
		if (index>=path.size()) return fail(c,"到达计划工位后，矿面视线未通过复核");
		BlockPos to=path.get(index), from=index==0 ? to : path.get(index-1);
		int cutIndex=clearanceIndex(path,index,(int)Math.ceil(BorerAim.breakReach(p))+1,b->inspectSlice(c,b));
		BlockPos cutTo=path.get(cutIndex), cutFrom=cutIndex==0 ? cutTo : path.get(cutIndex-1);
		if (mining!=null && loaded(c,mining) && c.level.getBlockState(mining).isAir()) mining=null;
		if (cutIndex>0 && tryPair(c,cutFrom,cutTo)) return true;
		if (cutIndex>0) for (var b:OreTunnelSearch.clearance(cutFrom,cutTo)) {
			int kind=cell(c,b);
			if (kind<0) return fail(c,"路线方块已变化或靠近危险物");
			if (kind==0) continue;
			c.options.keyUp.setDown(false);
			if (standToMine(c)) {
				if (!p.onGround()) { engine.releaseMine(c); return true; }
			} else { useFlight(c); flight.hover(); }
			if (engine.isStandingSupport(c,p,b) || engine.isUnsafeFloorMine(c,p,b)) return fail(c,"路线开挖会破坏立足点");
			var hit=engine.visibleHitResult(c,p,b);
			if (hit==null || !BorerAim.hitInReach(p,hit)) continue; // Try another visible face in this step.
			if (!engine.place.selectMiningTool(c,p,b)) return true;
			engine.lookAtMiningHit(c,p,hit);
			var actual=BorerAim.clipView(c,p);
			if (actual==null || !actual.getBlockPos().equals(b) || !BorerAim.hitInReach(p,actual)) return fail(c,"路线方块瞄准未确认");
			boolean changed=!b.equals(mining);
			if (changed) { engine.releaseMine(c); mining=b; miningTicks=0; }
			if (++miningTicks>200) return fail(c,"路线方块开挖超时");
			c.hitResult=actual; c.crosshairPickEntity=null;
			engine.applyMineCadence(c,p,b,changed,miningTicks%40==0);
			engine.status="按完整路线开路 "+index+"/"+path.size(); return true;
		}
		for (var b:OreTunnelSearch.clearance(from,to)) if (cell(c,b)!=0) return fail(c,"下一步的开挖面不可达");
		engine.releaseMine(c); mining=null;
		boolean diagonalDown=to.getY()<from.getY() && (to.getX()!=from.getX() || to.getZ()!=from.getZ());
		boolean walkDown = diagonalDown && !crossed && !BorerFlight.isFlying(p)
			&& canWalkDown(c,from,to);
		BlockPos waypoint=diagonalDown && !crossed && !walkDown ? to.above() : to;
		if (!safeFeet(c,waypoint)) return fail(c,"路线下方出现岩浆块或区块未加载");
		Vec3 groundTarget=Vec3.atBottomCenterOf(waypoint);
		boolean walk=walkDown || groundLane(p.getBoundingBox(),groundTarget,b->floor(c,b));
		Vec3 dest=walk ? groundTarget : BorerFlyPath.waypoint(waypoint);
		if (walk) {
			if (!walkDown) {
				standToMine(c);
				if (!p.onGround()) return true;
			} else {
				onFoot=true;
				c.options.keyJump.setDown(false);
				c.options.keyShift.setDown(false);
			}
		} else useFlight(c);
		double dx=dest.x-p.getX(), dz=dest.z-p.getZ();
		if (walk ? BorerCenterPolicy.reachedWaypoint(dx,dest.y-p.getY(),dz) : BorerHomeFlight.reached(p.position(),dest)) {
			if (!walk) flight.hover();
			if (!waypoint.equals(to)) crossed=true; else { index++; crossed=false; }
			last=null; idle=0; return true;
		}
		if (last==null || p.position().distanceToSqr(last)>.001) { idle=0;last=p.position(); }
		else if (++idle>80) return fail(c,"路线移动未取得进展");
		if (walk) {
			var input=BorerCenterPolicy.walkInput(dx,dz);
			var swept=p.getBoundingBox().expandTowards(input.probeX(),0,input.probeZ()).deflate(.0001);
			if (!c.level.noCollision(p,swept)) return fail(c,"步行通道已被阻挡");
			for (var b:BlockPos.betweenClosed(BlockPos.containing(swept.minX,swept.minY,swept.minZ),
					BlockPos.containing(swept.maxX,swept.maxY,swept.maxZ))) {
				if (cell(c,b)!=0) return fail(c,"步行通道已变化");
			}
			RotationAim.apply(p,input.yaw(),0);
			engine.rememberOreMove(p);
			c.options.keyUp.setDown(input.forward());
			c.options.keySprint.setDown(false); p.setSprinting(false);
			engine.status="沿地面接近矿石 "+index+"/"+path.size(); return true;
		}
		var input=BorerHomeFlight.clearanceInput(p.position(),dest,p.getYRot(),delta->{
			var box=p.getBoundingBox().expandTowards(delta).deflate(.0001);
			if (!c.level.noCollision(p,box)) return false;
			for (var b:BlockPos.betweenClosed(BlockPos.containing(box.minX,box.minY,box.minZ),BlockPos.containing(box.maxX,box.maxY,box.maxZ)))
				if (cell(c,b)!=0) return false;
			return true;
		});
		if (input==null) return fail(c,"路线身体空间已变化");
		RotationAim.apply(p,input.yaw(),0); flight.speed(input.speed());
		c.options.keyUp.setDown(input.forward()); c.options.keyJump.setDown(input.up()); c.options.keyShift.setDown(input.down());
		engine.status="沿完整路线接近矿石 "+index+"/"+path.size(); return true;
	}
}
