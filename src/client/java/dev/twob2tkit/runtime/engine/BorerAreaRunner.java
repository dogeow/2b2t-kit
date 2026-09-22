package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

import java.util.Objects;
import java.nio.file.Path;

/** The sole owner of AREA inputs. Does not invoke ore/corridor/Think fallback navigation. */
final class BorerAreaRunner {
	private final DefaultTunnelBorerEngine engine;
	private final BorerAreaFlightSession flight = new BorerAreaFlightSession();
	private BorerAreaPlan plan;
	private BorerAreaPlan.Command command;
	private RotationAim.Look look;
	private BlockPos mining;
	private int aimFailures, mineIdleTicks, lastStage = -1, moveIdleTicks, diagnostics;
	private double bestDistance = Double.POSITIVE_INFINITY;
	private String progressKey = "", lastLogged = "";
	private boolean attacking;
	private final BorerAreaPipeline pipeline = new BorerAreaPipeline();
	private final BorerMeteorInstant instant = new BorerMeteorInstant();
	private BlockPos failedFastTarget;
	private String pipelineGate = "";
	private int pipelineGateTick;
	private int confirmationTicks;
	private Path progressPath;
	private String progressWorld;
	private int saveTicks;
	private boolean naturalDescent;
	private int rescueTicks;
	private final BorerAreaTorch torch = new BorerAreaTorch();
	private final BorerAreaCargo cargo;
	private final BorerAreaWater water;

	BorerAreaRunner(DefaultTunnelBorerEngine engine) { this.engine = engine; cargo = new BorerAreaCargo(engine); water = new BorerAreaWater(engine); }
	boolean managingInventory() { return cargo.active(); }
	private boolean directMiningSupported(){try{return engine.host.supportsDirectAreaMining();}catch(LinkageError oldHost){return false;}}
	boolean ownsMining(){return attacking && directMiningSupported();}
	boolean ownsInventoryScreen(Minecraft c) { return cargo.ownsScreen(c); }
	void stopInventory(Minecraft c) { cargo.reset(c); water.reset(c); }

	void prepareFlight(Minecraft client) {
		String restored = flight.prepare(client.gameDirectory.toPath().resolve("config/twob2tkit/area-flight-speed.bak"));
		if (restored != null) {
			engine.fileLog(client, "area-flight-recover " + restored);
			DefaultTunnelBorerEngine.message(client, restored);
		}
	}

	/** At the top of an excavated shaft, restoring gravity would drop the player into it. */
	void releaseFlight(Minecraft client) {
		pipeline.clear(); // Vanilla retains and corrects any unacknowledged predictions independently.
		checkpoint();
		if (client.player != null && client.level != null && !client.player.onGround()) {
			if (flight.closeKeepingFlight()) engine.stopSafetyNote="已保留飞行";
		} else flight.close();
	}

	void reset() {
		pipeline.clear();
		failedFastTarget = null;
		checkpoint();
		cargo.reset(Minecraft.getInstance());
		water.reset(Minecraft.getInstance());
		flight.close();
		plan = null;
		command = null;
		look = null;
		mining = null;
		attacking = false;
		aimFailures = mineIdleTicks = moveIdleTicks = diagnostics = confirmationTicks = 0;
		lastStage = -1;
		progressKey = lastLogged = "";
		bestDistance = Double.POSITIVE_INFINITY;
		naturalDescent = false;
		rescueTicks = 0;
		torch.reset();
	}

	void suspend(Minecraft client) {
		cargo.pause(client);
		checkpoint();
		look = null;
		stopAttack(client);
		releaseMovement(client);
		try { flight.hover(); } catch (IllegalStateException error) {
			engine.fileLog(client, "area-v2-pause-flight " + error.getMessage());
		}
		progressKey = "";
		bestDistance = Double.POSITIVE_INFINITY;
		moveIdleTicks = 0;
	}
	void suspendForCombat(Minecraft client) {
		cargo.pause(client);
		look = null;
		stopAttack(client);
		releaseMovement(client);
		try {
			prepareFlight(client);
			String error = flight.acquire(client.player);
			if (error == null) flight.hover();
			else engine.fileLog(client, "area-defense-hover " + error);
		} catch (IllegalStateException error) { engine.fileLog(client, "area-defense-hover " + error.getMessage()); }
	}

	/** Unlike ordinary suspend, never releases Use or changes the selected food slot. */
	void suspendForEating(Minecraft client, boolean entering) {
		if (entering) { cargo.pause(client); checkpoint(); }
		look = null;
		stopAttack(client);
		prepareFlight(client);
		String error = flight.acquire(client.player);
		if (error != null) throw new IllegalStateException(error);
		flight.hover();
		// Pause safely if a delayed server block update dropped us into liquid while eating.
		if (client.player.isInWater() || client.player.isInLava()) {
			flight.speed(0.2);
			client.options.keyJump.setDown(true);
		}
		progressKey = ""; bestDistance = Double.POSITIVE_INFINITY;
		moveIdleTicks = mineIdleTicks = aimFailures = 0; lastStage = -1;
	}

	String diagnosticState() {
		return plan == null ? "INIT" : plan.phase() + ":col=" + BorerText.block(plan.column())
			+ ",strategy=" + (plan.horizontal() ? "SHALLOW_HORIZONTAL" : "VERTICAL_SHAFT")
			+ ",next=" + (plan.pending() == null ? "-" : BorerText.block(plan.pending()))
			+ ",cursorY=" + plan.cursorY() + ",done=" + plan.completed() + "/" + plan.total()
			+ ",skipped=" + plan.skipped() + ",bedrock=" + plan.bedrockColumns()
			+ ",transferY=" + plan.transferY()
			+ ",emptyVerified=" + plan.confirmedEmptyColumns()
			+ ",action=" + (command == null ? "-" : command.action())
			+ ",aimWait=" + aimFailures + ",mineWait=" + mineIdleTicks + ",moveWait=" + moveIdleTicks;
	}

	boolean allowsMiningTarget(BlockPos pos) {
		return command != null && (command.action() == BorerAreaPlan.Action.MINE || command.action() == BorerAreaPlan.Action.MINE_DOWN)
			&& Objects.equals(pos, command.block());
	}

	void tick(Minecraft client, LocalPlayer player) {
		releaseMovement(client);
		look = null;
		try {
			prepareFlight(client);
			String flightError = flight.acquire(player);
			if (flightError != null) { stop(client, flightError); return; }
			if (plan == null) {
				int bottom = engine.areaBoundedDown ? engine.areaMin.getY() : client.level.getMinY();
				if (bottom < client.level.getMinY() || engine.areaMax.getY() >= client.level.getMaxY() - 3) {
					stop(client, "区域 Y 超出世界可用高度"); return;
				}
				progressPath = client.gameDirectory.toPath().resolve("config/twob2tkit/area-progress.json");
				progressWorld = worldKey(client);
				BlockPos min = new BlockPos(engine.areaMin.getX(), bottom, engine.areaMin.getZ());
				boolean shallow = BorerAreaHorizontal.enabled(min, engine.areaMax);
				plan = BorerAreaPlan.restore(min, engine.areaMax, pose(player), BorerAreaProgress.read(progressPath, progressWorld), shallow);
				boolean resumed = plan != null;
				if (plan == null) {
					plan = new BorerAreaPlan(min, engine.areaMax, pose(player), shallow);
				}
				if (resumed) engine.fileLog(client, "area-v3-resume " + diagnosticState() + " pos=" + BorerText.precise(player));
				engine.fileLog(client, "area-v2-start bounds=" + BorerText.block(engine.areaMin) + ".." + BorerText.block(engine.areaMax)
					+ " columns=" + plan.total() + " bottom=" + bottom + " strategy=" + (shallow ? "SHALLOW_HORIZONTAL" : "VERTICAL_SHAFT")
					+ " height=" + (engine.areaMax.getY() - bottom + 1) + " breakReach=" + BorerAim.breakReach(player));
				engine.status=shallow ? "浅层区域：水平清挖" : "深层区域：逐列清挖";
			}
			if (player.isInWater() || player.isInLava()) { rescue(client, player); return; }
			rescueTicks = 0;
			if (pipeline.active()) { tickPipeline(client, player); return; }
			if (water.active()) { sealSideWater(client); return; }
			if (torch.tick(client, engine)) { flight.fly(); flight.speed(0); stopAttack(client); return; }
			if(mining!=null && engine.miningConfirmation.pending(client.level,mining)){
				stopAttack(client);flight.fly();flight.speed(0);naturalDescent=false;
				show(client,"等待服务器确认方块更新 "+BorerText.block(mining));
				if(++confirmationTicks>=100)stop(client,"方块更新连续 5 秒未获确认 "+BorerText.block(mining)+"；当前列未完成");
				return;
			}
			confirmationTicks=0;
			if (plan.phase() != BorerAreaPlan.Phase.SURVEY && plan.phase() != BorerAreaPlan.Phase.DONE && plan.phase() != BorerAreaPlan.Phase.BLOCKED
				&& !cargo.active() && cargo.shouldStart(client)) {
				checkpoint(); stopAttack(client); flight.fly(); flight.speed(0);
				cargo.start(client, progressWorld, engine.areaMin, engine.areaMax);
				progressKey = "";
			}
			if (cargo.active()) {
				flight.fly(); naturalDescent = false;
				command = cargo.tick(client, world(client), engine.areaMin, engine.areaMax);
				BlockPos chest = cargo.storageBlock();
				if (chest != null) {
					boolean changed = plan.reserveStorageColumn(chest);
					var state = client.level.getBlockState(chest);
					if (state.is(Blocks.CHEST) && state.getValue(net.minecraft.world.level.block.ChestBlock.TYPE) != net.minecraft.world.level.block.state.properties.ChestType.SINGLE)
						changed |= plan.reserveStorageColumn(chest.relative(net.minecraft.world.level.block.ChestBlock.getConnectedDirection(state)));
					if (changed) checkpoint();
				}
				if (command.action() == BorerAreaPlan.Action.BLOCKED) { stop(client, command.reason()); return; }
				if (cargo.finished()) { plan.resumeAfterStorage(pose(player)); cargo.reset(client); checkpoint(); progressKey = ""; stopAttack(client); flight.speed(0); return; }
				if (command.action() == BorerAreaPlan.Action.MINE) mine(client, player, command.block());
				else if (command.action() == BorerAreaPlan.Action.WAIT) {
					stopAttack(client); flight.speed(0); show(client, command.reason());
					watchProgress(client, player, 0);
				} else move(client, player);
				return;
			}
			boolean surveying = plan.phase() == BorerAreaPlan.Phase.SURVEY;
			int beforeEmpty = plan.confirmedEmptyColumns();
			double beforeTransferY = plan.transferY();
			int beforeBedrock = plan.bedrockColumns();
			command = plan.step(world(client), pose(player));
			if (plan.transferY() != beforeTransferY) engine.fileLog(client, "area-transfer-height " + diagnosticState()
				+ " previousY=" + beforeTransferY + " reason=" + command.reason());
			if (plan.bedrockColumns() != beforeBedrock) {
				engine.fileLog(client, "area-bedrock-columns " + diagnosticState() + " reason=" + command.reason());
				checkpoint();
			}
			if ((surveying && plan.phase() != BorerAreaPlan.Phase.SURVEY) || plan.confirmedEmptyColumns() > beforeEmpty) {
				engine.fileLog(client, "area-v4-survey " + diagnosticState() + " reason=" + command.reason());
				checkpoint();
			}
			naturalDescent = plan.phase() == BorerAreaPlan.Phase.DIG
				&& command.action() != BorerAreaPlan.Action.SEAL_WATER
				&& command.action() != BorerAreaPlan.Action.UP && command.action() != BorerAreaPlan.Action.X
				&& command.action() != BorerAreaPlan.Action.Z;
			if (plan.cursorY() < plan.bottomY() && player.getY() + player.getDeltaMovement().y * 2 <= plan.bottomY() + 2.0
				&& !engine.hasCollision(client, new BlockPos(plan.column().getX(), plan.bottomY() - 1, plan.column().getZ()))) {
				naturalDescent = false; // Brake over an open cave at the requested bottom instead of falling below it.
			}
			// A deep open shaft needs the user's NoFall; otherwise use controlled flight descent.
			if (canGroundForMining(client,player) && (command.action() == BorerAreaPlan.Action.MINE || command.action() == BorerAreaPlan.Action.WAIT)) {
				naturalDescent = false; flight.speed(0); flight.digOnFoot();
			} else if (naturalDescent && BorerFlight.meteorNoFallActive()) flight.digOnFoot();
			else { naturalDescent = false; flight.fly(); }
			if (plan.reachedBottomThisStep()) {
				stopAttack(client);
				flight.fly(); flight.speed(0);
				torch.begin(new BlockPos(plan.column().getX(), plan.bottomY(), plan.column().getZ()));
				if (torch.tick(client, engine)) return;
			}
			engine.areaShaftColumn = plan.column();
			engine.areaRelocating = plan.phase() != BorerAreaPlan.Phase.DIG;
			String change = plan.phase() + ":" + plan.column() + ":" + command.action() + ":" + command.block();
			if (!change.equals(lastLogged)) {
				engine.fileLog(client, "area-v2-step " + diagnosticState() + " reason=" + command.reason());
				lastLogged = change;
				if (plan.phase() == BorerAreaPlan.Phase.RETURN || plan.phase() == BorerAreaPlan.Phase.DONE) checkpoint();
			}
			if (++saveTicks >= 20) { saveTicks = 0; checkpoint(); }
			if (++diagnostics >= 40) { diagnostics = 0; engine.logDiagnostic(client, player, "area-v2"); }
			switch (command.action()) {
				case BLOCKED -> stop(client, command.reason() + blockSuffix(command.block()));
				case DONE -> stop(client, plan.skipped() == 0 ? "区域已复核挖完：" + plan.total() + " 列；" + (plan.horizontal() ? "浅层保留当前位置" : "已返回顶部")
					: "可挖部分已结束：挖空 " + plan.completed() + " 列，基岩止挖 " + plan.bedrockColumns()
						+ " 列，挡水 / 存储保留 " + (plan.skipped() - plan.bedrockColumns()) + " 列；" + (plan.horizontal() ? "浅层保留当前位置" : "已返回顶部"));
				case MINE, MINE_DOWN -> mine(client, player, command.block());
				case SEAL_WATER -> beginSideWater(client, command.block());
				case WAIT -> {
					flight.speed(0);
					stopAttack(client);
					if (!watchProgress(client, player, plan.distanceRemaining(pose(player)))) return;
					show(client, command.reason());
				}
				default -> move(client, player);
			}
		} catch (RuntimeException | java.io.IOException error) {
			engine.fileLog(client, "area-v2-failure " + error.getClass().getSimpleName() + ": " + error.getMessage());
			stop(client, "区域控制已停止：" + error.getMessage());
		}
	}

	private BorerAreaPlan.World world(Minecraft client) {
		return new BorerAreaPlan.World() {
			public BorerAreaPlan.Cell cell(BlockPos p) { return BorerAreaRunner.this.cell(client, p); }
			public boolean opensLiquid(BlockPos p) {
				return BorerHazards.wouldOpenWater(client, p) || BorerHazards.wouldOpenLava(client, p);
			}
			public BlockPos sealableSideWater(BlockPos p) { return water.candidate(client, p); }
			public boolean canMine(BlockPos p) { return BorerAim.visibleHit(client, client.player, p, p::equals) != null; }
		};
	}
	private void checkpoint() {
		if (plan == null || progressPath == null || progressWorld == null) return;
		try { BorerAreaProgress.write(progressPath, progressWorld, plan.snapshot()); }
		catch (java.io.IOException ignored) { /* The current in-memory run remains valid. */ }
	}
	private static String worldKey(Minecraft client) {
		String server = client.getCurrentServer() != null ? client.getCurrentServer().ip
			: client.getSingleplayerServer() != null
				? client.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toString() : "unknown";
		return server + "|" + client.level.dimension().identifier();
	}
	boolean canResumeHere(Minecraft client) {
		if (client.player == null || client.level == null || !engine.host.borerAreaSet()) return false;
		int ay = engine.host.borerAreaAy(), by = engine.host.borerAreaBy();
		BlockPos min = new BlockPos(Math.min(engine.host.borerAreaAx(), engine.host.borerAreaBx()),
			ay == by ? client.level.getMinY() : Math.min(ay, by), Math.min(engine.host.borerAreaAz(), engine.host.borerAreaBz()));
		BlockPos max = new BlockPos(Math.max(engine.host.borerAreaAx(), engine.host.borerAreaBx()),
			Math.max(ay, by), Math.max(engine.host.borerAreaAz(), engine.host.borerAreaBz()));
		return BorerAreaPlan.restore(min, max, pose(client.player), BorerAreaProgress.read(
			client.gameDirectory.toPath().resolve("config/twob2tkit/area-progress.json"), worldKey(client)), BorerAreaHorizontal.enabled(min, max)) != null;
	}

	private BorerAreaPlan.Cell cell(Minecraft client, BlockPos pos) {
		if (!client.level.hasChunkAt(pos) || engine.miningConfirmation.pending(client.level,pos)) return BorerAreaPlan.Cell.UNLOADED;
		if (pos.getY() < client.level.getMinY() || pos.getY() >= client.level.getMaxY()) return BorerAreaPlan.Cell.PROTECTED;
		var state = client.level.getBlockState(pos);
		if (state.isAir()) return BorerAreaPlan.Cell.AIR;
		if (state.is(Blocks.BEDROCK)) return BorerAreaPlan.Cell.BEDROCK;
		if (state.is(Blocks.TORCH) || state.is(Blocks.WALL_TORCH)) return BorerAreaPlan.Cell.AIR;
		if (!state.getFluidState().isEmpty()) return BorerAreaPlan.Cell.LIQUID;
		if (plan != null && plan.isWaterSeal(pos)) return BorerAreaPlan.Cell.PROTECTED;
		// Remaining volume is never filtered by temporary aim failure, ore selection or suppression.
		if (state.getDestroySpeed(client.level, pos) < 0 || client.level.getBlockEntity(pos) != null
			|| state.is(Blocks.NETHER_PORTAL) || state.is(Blocks.END_PORTAL) || state.is(Blocks.END_PORTAL_FRAME)
			|| engine.isProtectedSealBlock(client, pos)
			|| client.player.blockActionRestricted(client.level, pos, client.gameMode.getPlayerMode())) {
			return BorerAreaPlan.Cell.PROTECTED;
		}
		return BorerAreaPlan.Cell.SOLID;
	}

	private void mine(Minecraft client, LocalPlayer player, BlockPos target) {
		if (!Objects.equals(target, mining)) {
			stopAttack(client);
			mining = target;
			aimFailures = mineIdleTicks = 0;
			lastStage = -1;
			engine.setMiningTarget(client, player, target, "area-v2");
		}
		BlockPos liquid = BorerHazards.waterOpenedByMining(client, target);
		if (liquid == null) liquid = BorerHazards.lavaOpenedByMining(client, target);
		if (liquid != null) {
			if (cargo.active()) { stop(client, "卸货路线头顶有液体，保留挡块并暂停"); return; }
			if (water.candidate(client, target) != null) { beginSideWater(client, target); return; }
			engine.fileLog(client, "area-liquid-unsealable barrier=" + target + " liquid=" + liquid
				+ " water=" + BorerHazards.isWater(client, liquid) + " enabled=" + engine.host.borerSealLiquids()
				+ " inReach=" + BorerAim.inReach(player, liquid));
			stopAttack(client);
			flight.speed(0);
			command = plan.skipLiquid(pose(player), target);
			checkpoint();
			if (command.action() == BorerAreaPlan.Action.BLOCKED) stop(client, command.reason());
			else show(client, "保留隔水块 " + BorerText.block(target) + "，重新选择安全通路");
			return;
		}
		if (!engine.place.selectMiningTool(client, player, target)) return;
		// Keep the ray that was verified; aiming at the block centre again can hit its neighbour.
		BlockHitResult visible = BorerAim.visibleHit(client, player, target, target::equals);
		Vec3 aim = visible == null ? Vec3.atCenterOf(target) : BorerAim.lookAlongRay(player.getEyePosition(), visible);
		look = RotationAim.lookAt(player, aim);
		if (target.getX() == player.blockPosition().getX() && target.getZ() == player.blockPosition().getZ()) {
			float pitch = target.getY() + 0.5 < player.getEyeY() ? 90 : -90;
			RotationAim.apply(player, player.getYRot(), pitch);
			BlockHitResult vertical = BorerAim.clipView(client, player);
			if (vertical != null && target.equals(vertical.getBlockPos())) look = new RotationAim.Look(player.getYRot(), pitch);
		}
		RotationAim.apply(player, look);
		BlockHitResult actual = BorerAim.clipView(client, player);
		boolean valid = actual != null && target.equals(actual.getBlockPos())
			&& player.getEyePosition().distanceTo(actual.getLocation()) <= BorerAim.breakReach(player);
		if (!valid) {
			flight.speed(0);
			stopAttack(client);
			if (++aimFailures == 1 || aimFailures % 20 == 0) engine.fileLog(client,
				"area-v2-aim target=" + BorerText.block(target) + " actual=" + (actual == null ? "-" : BorerText.block(actual.getBlockPos()))
				+ " wait=" + aimFailures + " pose=" + BorerText.precise(player));
			if (aimFailures >= 80) { stop(client, "当前层真实射线持续被挡 " + BorerText.block(target) + "；未换列"); return; }
			show(client, "稳定对准当前层 " + BorerText.block(target));
			return;
		}
		aimFailures = 0;
		int stage = client.gameMode.getDestroyStage();
		if (stage > lastStage) { lastStage = stage; mineIdleTicks = 0; }
		else mineIdleTicks++;
		if (mineIdleTicks >= 240) { stop(client, "当前方块连续 12 秒没有挖掘进展 " + BorerText.block(target) + "；当前列未完成"); return; }
		client.hitResult = actual;
		client.crosshairPickEntity = null;
		logPipelineGate(client, "repeat=" + repeatClick(client) + " onGround=" + player.onGround()
			+ " progress=" + client.level.getBlockState(target).getDestroyProgress(player,client.level,target));
		if (!cargo.active() && directMiningSupported() && (plan.phase() == BorerAreaPlan.Phase.DIG || plan.phase() == BorerAreaPlan.Phase.HORIZONTAL)
			&& !target.equals(failedFastTarget) && fastClick(client, target) && pipeline.canClick(player.tickCount)) {
			if (clickPipeline(client, player, target, actual)) { advanceWhileMining(client,player); return; }
		}
		boolean retry = mineIdleTicks > 0 && mineIdleTicks % 40 == 0;
		if(directMiningSupported()){
			client.options.keyAttack.setDown(false);
			if(!attacking||retry){
				if(retry)client.gameMode.stopDestroyBlock();
				engine.miningConfirmation.startObservedBreak(client,target,actual.getDirection());
			}else client.gameMode.continueDestroyBlock(target,actual.getDirection());
		}else{
			if (!attacking || retry) {
				if (retry) client.gameMode.stopDestroyBlock();
				KeyMapping.click(com.mojang.blaze3d.platform.InputConstants.getKey(client.options.keyAttack.saveString()));
			}
			client.options.keyAttack.setDown(true);
		}
		attacking = true;
		BorerAreaMotion.Input input = BorerAreaMotion.of(command, pose(player), look.yaw());
		flight.speed(naturalDescent ? 0 : input.speed());
		client.options.keyShift.setDown(!naturalDescent && input.down());
		progressKey = "";
		moveIdleTicks = 0;
		show(client, (plan.phase() == BorerAreaPlan.Phase.HORIZONTAL ? "浅层水平清挖 " : "挖第 ") + Math.min(plan.total(), plan.completed() + 1) + "/" + plan.total() + " 列 · Y " + target.getY());
		advanceWhileMining(client,player);
	}
	private boolean fastClick(Minecraft c, BlockPos pos) {
		var state = c.level.getBlockState(pos);
		return repeatClick(c) || instant.allows(state.getBlock(), state.getDestroyProgress(c.player,c.level,pos));
	}
	private boolean repeatClick(Minecraft c) {
		return engine.areaInstantRebreakRequested() && instant.repeatAllows(c.player.getMainHandItem().is(net.minecraft.tags.ItemTags.PICKAXES));
	}
	private void logPipelineGate(Minecraft c, String reason) {
		if (!reason.equals(pipelineGate) || c.player.tickCount - pipelineGateTick >= 100) {
			engine.fileLog(c,"area-pipeline-gate "+reason); pipelineGate = reason; pipelineGateTick = c.player.tickCount;
		}
	}
	private boolean canGroundForMining(Minecraft c, LocalPlayer p) {
		if (cargo.active() || plan == null || plan.phase() != BorerAreaPlan.Phase.HORIZONTAL) return false;
		var box = p.getBoundingBox();
		boolean supported = true;
		for (int x = (int)Math.floor(box.minX+.001); x <= (int)Math.floor(box.maxX-.001); x++)
			for (int z = (int)Math.floor(box.minZ+.001); z <= (int)Math.floor(box.maxZ-.001); z++) {
				var floor = new BlockPos(x,plan.bottomY()-1,z);
				if (!safeWalkingFloor(c,floor)) supported = false;
			}
		var v = p.getDeltaMovement();
		return BorerAreaGrounding.allowed(true,p.getY(),plan.bottomY(),v.x,v.y,v.z,supported);
	}
	private void holdForMining(Minecraft c, LocalPlayer p) {
		releaseMovement(c); flight.speed(0); naturalDescent = false;
		if (canGroundForMining(c,p)) flight.digOnFoot(); else flight.fly();
	}
	private boolean clickPipeline(Minecraft c, LocalPlayer player, BlockPos pos, BlockHitResult hit) {
		stopAttack(c); holdForMining(c,player);
		if (!fastClick(c,pos)) return false;
		boolean repeat = repeatClick(c);
		engine.miningConfirmation.startObservedBreak(c,pos,hit.getDirection());
		if (repeat && !c.level.getBlockState(pos).isAir()) instant.finishRepeat(pos,hit.getDirection());
		if (!repeat && !c.level.getBlockState(pos).isAir()) {
			failedFastTarget = pos; attacking = true;
			show(c,"当前方块不能点挖，转为持续挖掘"); return true;
		}
		if (!repeat && !engine.miningConfirmation.pending(c.level,pos)) {
			stop(c,"瞬时破坏未登记服务器确认，已暂停；请重新进服核对方块"); return true;
		}
		pipeline.submitted(pos,player.tickCount);
		player.swing(net.minecraft.world.InteractionHand.MAIN_HAND);
		mining = pos; progressKey = ""; moveIdleTicks = mineIdleTicks = 0;
		engine.fileLog(c,"area-pipeline-click block="+pos+" pending="+pipeline.size()+" mode="+(repeat?"InstantRebreak":"SpeedMine/vanilla")+" onGround="+player.onGround());
		show(c,"连续点挖 · 待确认 "+pipeline.size()+"/"+BorerAreaPipeline.LIMIT);
		return true;
	}
	private void tickPipeline(Minecraft c, LocalPlayer player) {
		try { tickPipelineWork(c,player); }
		finally { if (engine.active && pipeline.active()) advanceWhileMining(c,player); }
	}
	private void tickPipelineWork(Minecraft c, LocalPlayer player) {
		stopAttack(c); holdForMining(c,player);
		var confirmed = pipeline.update(player.tickCount, p -> new BorerAreaPipeline.Observation(
			c.level.hasChunkAt(p) && c.level.getBlockState(p).isAir(), engine.miningConfirmation.pending(c.level,p)));
		for (var pos : confirmed)
			engine.fileLog(c,"area-pipeline-confirmed block="+pos);
		BlockPos expired = pipeline.expired(player.tickCount);
		if (expired != null) { stop(c,"连续点挖 5 秒未确认 "+BorerText.block(expired)+"，已停挖；未计完成"); return; }
		var tool = player.getMainHandItem();
		boolean toolReady = BorerItems.isMiningTool(tool) && engine.toolPolicy.allows(tool.getItem(),tool.isDamageableItem(),tool.getMaxDamage(),BorerItems.remainingDurability(tool));
		// Vanilla has one delayed-destroy slot: B's first STOP may be ignored while A still owns it.
		if (!confirmed.isEmpty() && toolReady && repeatClick(c)) {
			for (var pos : pipeline.positions()) {
				if (cell(c,pos) != BorerAreaPlan.Cell.SOLID || !plan.pipelineAllowed(world(c),pos,pipeline::contains)
					|| BorerHazards.wouldOpenWater(c,pos) || BorerHazards.wouldOpenLava(c,pos)) continue;
				var state = c.level.getBlockState(pos);
				if (state.requiresCorrectToolForDrops() && !tool.isCorrectToolForDrops(state)) continue;
				var hit = BorerAim.visibleHit(c,player,pos,pos::equals);
				if (hit == null || pipeline.blocksRay(player.getEyePosition(),hit.getLocation(),pos)) continue;
				look = RotationAim.lookAt(player,BorerAim.lookAlongRay(player.getEyePosition(),hit)); RotationAim.apply(player,look);
				var actual = BorerAim.clipView(c,player);
				if (actual == null || !pos.equals(actual.getBlockPos())) continue;
				instant.finishRepeat(pos,actual.getDirection());
				engine.fileLog(c,"area-pipeline-followup block="+pos+" reason=previous-block-confirmed");
			}
		}
		if (!pipeline.canClick(player.tickCount) || cargo.shouldStart(c) || !toolReady || torch.needsService(c)) {
			show(c,"核对方块更新 · 待确认 "+pipeline.size()); return;
		}
		var candidates = new java.util.ArrayList<BlockPos>();
		var candidateWorld = world(c);
		BlockPos base = player.blockPosition();
		for (BlockPos pos : BlockPos.betweenClosed(base.offset(-4,-4,-4),base.offset(4,4,4))) {
			if (pipeline.contains(pos) || pos.equals(failedFastTarget) || cell(c,pos) != BorerAreaPlan.Cell.SOLID
				|| player.getBoundingBox().intersects(new net.minecraft.world.phys.AABB(pos))
				|| !plan.pipelineAllowed(candidateWorld,pos,pipeline::contains) || BorerHazards.wouldOpenWater(c,pos) || BorerHazards.wouldOpenLava(c,pos)) continue;
			candidates.add(pos.immutable());
		}
		candidates.sort(java.util.Comparator.comparingDouble(p -> Vec3.atCenterOf(p).distanceToSqr(player.getEyePosition())));
		int attempts = 0;
		for (var pos : candidates) {
			if (++attempts > 24) break;
			BlockHitResult hit = BorerAim.visibleHit(c,player,pos,pos::equals);
			if (hit == null || pipeline.blocksRay(player.getEyePosition(),hit.getLocation())) continue;
			// An in-flight click keeps its tool until confirmed; never cancel it with an inventory swap.
			var state = c.level.getBlockState(pos);
			if (state.requiresCorrectToolForDrops() && !player.getMainHandItem().isCorrectToolForDrops(state) || !fastClick(c,pos)) continue;
			look = RotationAim.lookAt(player,BorerAim.lookAlongRay(player.getEyePosition(),hit)); RotationAim.apply(player,look);
			BlockHitResult actual = BorerAim.clipView(c,player);
			if (actual == null || !pos.equals(actual.getBlockPos()) || pipeline.blocksRay(player.getEyePosition(),actual.getLocation())) continue;
			c.hitResult = actual; c.crosshairPickEntity = null;
			if (clickPipeline(c,player,pos,actual)) return;
		}
		if (!pipeline.active()) { mining = null; look = null; show(c,"本批方块已确认，继续清挖"); return; }
		logPipelineGate(c,"等待独立可见目标 candidates="+candidates.size()+" pending="+pipeline.size());
		show(c,"等待已点方块确认，保持原地");
	}
	private boolean safeWalkingFloor(Minecraft c, BlockPos floor) {
		if (!c.level.hasChunkAt(floor) || engine.miningConfirmation.pending(c.level,floor) || pipeline.contains(floor)) return false;
		var state=c.level.getBlockState(floor);
		return state.isCollisionShapeFullBlock(c.level,floor) && state.getFluidState().isEmpty() && !state.is(Blocks.MAGMA_BLOCK);
	}
	private void advanceWhileMining(Minecraft c, LocalPlayer player) {
		if (!engine.active || c.screen != null || cargo.active() || cargo.shouldStart(c) || look == null
			|| plan == null || plan.phase() != BorerAreaPlan.Phase.HORIZONTAL || player.isUsingItem()) return;
		if (plan.continueMiningWalk(world(c),pose(player),player.tickCount,pipeline::contains))
			torch.begin(new BlockPos(plan.column().getX(),plan.bottomY(),plan.column().getZ()));
		var input = BorerAreaAdvance.input(pose(player),plan.miningTravelGoal(),look.yaw());
		var safety = new BorerAreaAdvance.World() {
			public boolean air(BlockPos p) { return !pipeline.contains(p) && cell(c,p)==BorerAreaPlan.Cell.AIR; }
			public boolean floor(BlockPos p) { return safeWalkingFloor(c,p); }
		};
		if (!BorerAreaAdvance.safe(safety,pose(player),plan.bottomY(),input)) return;
		flight.speed(0); flight.digOnFoot(); naturalDescent=false;
		c.options.keyUp.setDown(input.forward()); c.options.keyDown.setDown(input.back());
		c.options.keyLeft.setDown(input.left()); c.options.keyRight.setDown(input.right());
		plan.miningAdvanced(world(c),pose(player));
		show(c,"边挖边接近下一格 · 待确认 "+pipeline.size());
	}

	private void beginSideWater(Minecraft client, BlockPos target) {
		stopAttack(client); releaseMovement(client); flight.fly(); flight.speed(0); naturalDescent = false; look = null;
		BlockPos side = water.candidate(client, target);
		if (side == null) { stop(client, "侧水位置变化或不能安全封堵，保留通道挡块"); return; }
		water.begin(client, target, side);
		sealSideWater(client);
	}
	private void sealSideWater(Minecraft client) {
		stopAttack(client); releaseMovement(client); flight.fly(); flight.speed(0); naturalDescent = false; look = null;
		var result = water.tick(client);
		// Persist a protective reservation even if the user stops during the confirmation window.
		// This is not completion: continued mining still waits for DONE below.
		if (water.observedSolid(client) && !plan.isWaterSeal(water.water())) { plan.rememberWaterSeal(water.water()); checkpoint(); }
		if (result == BorerWaterSealPolicy.Action.DONE) {
			BlockPos sealed = water.water(), barrier = water.barrier();
			if (!plan.isWaterSeal(sealed)) plan.rememberWaterSeal(sealed);
			engine.fileLog(client, "area-water-confirmed side=" + sealed + " continue=" + barrier);
			water.end(client); checkpoint(); progressKey = "";
			show(client, "侧面进水口已封住，保留挡水石并继续开路");
		} else if (result == BorerWaterSealPolicy.Action.FAIL) {
			String reason = water.failure();
			engine.fileLog(client, "area-water-failed side=" + water.water() + " reason=" + reason);
			water.end(client); stop(client, reason);
		} else show(client, "正在用石料封住侧水 " + BorerText.block(water.water()) + "，等待封堵生效");
	}

	private void move(Minecraft client, LocalPlayer player) {
		stopAttack(client);
		engine.clearMiningTarget(client, "area-v2-moving");
		mining = null;
		BorerAreaMotion.Input input = cargo.active() ? BorerCargoMotion.of(command, pose(player), player.getYRot())
			: BorerAreaMotion.of(command, pose(player), player.getYRot());
		// A single axis and one yaw per tick, including the host's post-tick reapply.
		look = new RotationAim.Look(input.yaw(), command.action() == BorerAreaPlan.Action.DOWN && plan.phase() == BorerAreaPlan.Phase.DIG ? 90 : 0);
		RotationAim.apply(player, look);
		if (naturalDescent && command.action() == BorerAreaPlan.Action.DOWN) {
			flight.speed(0);
			if (!watchProgress(client, player, plan.distanceRemaining(pose(player)))) return;
			show(client, "低头自然下落，继续下挖");
			return;
		}
		flight.speed(input.speed());
		client.options.keyUp.setDown(input.forward());
		client.options.keyJump.setDown(input.up());
		client.options.keyShift.setDown(input.down());
		if (!watchProgress(client, player, cargo.active()
			? Math.abs(command.x() - player.getX()) + Math.abs(command.y() - player.getY()) + Math.abs(command.z() - player.getZ())
			: plan.distanceRemaining(pose(player)))) return;
		show(client, command.reason() + " · 第 " + Math.min(plan.total(), plan.completed() + 1) + "/" + plan.total() + " 列");
	}

	private void rescue(Minecraft client, LocalPlayer player) {
		cargo.pause(client);
		stopAttack(client);
		flight.fly();
		naturalDescent = false;
		if (rescueTicks++ == 0) {
			if (plan.phase() == BorerAreaPlan.Phase.DIG || plan.phase() == BorerAreaPlan.Phase.HORIZONTAL) plan.skipLiquid(pose(player), player.blockPosition());
			checkpoint();
			engine.fileLog(client, "area-liquid-rescue pos=" + BorerText.precise(player) + " lava=" + player.isInLava());
		}
		if (rescueTicks > 100 || !client.level.noCollision(player, player.getBoundingBox().move(0, 0.5, 0))) {
			stop(client, "液体逃生上方被挡或超时，已保留飞行，请手动接管"); return;
		}
		look = new RotationAim.Look(player.getYRot(), 0);
		RotationAim.apply(player, look);
		flight.speed(0.10);
		client.options.keyJump.setDown(true);
		show(client, player.isInLava() ? "意外进入岩浆，停挖并启飞上升脱离" : "意外进水，停挖并启飞上浮");
	}

	private boolean watchProgress(Minecraft client, LocalPlayer player, double distance) {
		String key = cargo.active() ? "cargo:" + cargo.stamp() + ":" + command.action() : plan.progressStamp();
		if (!key.equals(progressKey)) {
			progressKey = key;
			bestDistance = distance;
			moveIdleTicks = 0;
		} else if (distance < bestDistance - 0.025) {
			bestDistance = distance;
			moveIdleTicks = 0;
		} else if (++moveIdleTicks >= 240) {
			stop(client, "区域动作连续 12 秒没有进展：" + command.reason() + " @ " + BorerText.precise(player));
			return false;
		}
		return true;
	}

	void reapplyLook(Minecraft client) {
		if (look == null || client.player == null || client.screen != null) return;
		RotationAim.apply(client.player, look);
		if (attacking) {
			BlockHitResult hit = BorerAim.clipView(client, client.player);
			if (hit == null || !Objects.equals(mining, hit.getBlockPos())) stopAttack(client);
		}
	}

	private void stopAttack(Minecraft client) {
		if (attacking && client.gameMode != null) client.gameMode.stopDestroyBlock();
		if (client.options != null) client.options.keyAttack.setDown(false);
		attacking = false;
	}

	private void stop(Minecraft client, String reason) {
		engine.fileLog(client, "area-v2-stop " + diagnosticState() + " reason=" + reason);
		suspend(client);
		engine.stop(client, reason);
	}

	private void show(Minecraft client, String text) {
		engine.status = text;
		engine.overlay(client, text, 0x55FFFF);
	}

	private static String blockSuffix(BlockPos block) { return block == null ? "" : " @ " + BorerText.block(block); }
	private static BorerAreaPlan.Pose pose(LocalPlayer p) {
		Vec3 v = p.getDeltaMovement();
		return new BorerAreaPlan.Pose(p.getX(), p.getY(), p.getZ(), v.x, v.y, v.z);
	}
	private void releaseMovement(Minecraft client) {
		client.options.keyUp.setDown(false); client.options.keyDown.setDown(false);
		client.options.keyLeft.setDown(false); client.options.keyRight.setDown(false);
		client.options.keyJump.setDown(false); client.options.keyShift.setDown(false);
		client.options.keySprint.setDown(false); client.options.keyUse.setDown(false);
		client.player.setSprinting(false);
		engine.attemptedForward = false;
	}
}
