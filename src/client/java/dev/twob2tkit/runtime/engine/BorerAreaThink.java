package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.EnumSet;
import java.util.List;

/** 区域挖卡住后按记忆试招，解开就加分。 */
final class BorerAreaThink {
	private final DefaultTunnelBorerEngine engine;
	private final BorerArea area;
	private BorerAreaThinkStore.File memory;
	private Vec3 lastPos;
	private int stillTicks;
	private BorerAreaThinkPolicy.Move current;
	private int tryTicks;
	private String scene;
	private final EnumSet<BorerAreaThinkPolicy.Move> tried = EnumSet.noneOf(BorerAreaThinkPolicy.Move.class);
	private int skipCooldown;
	private long lastNoteTick = Long.MIN_VALUE;
	private int ticksSinceAsk = BorerAreaThinkPolicy.ASK_COOLDOWN_TICKS;
	private int shaftsSinceAsk;
	private boolean asking;
	private boolean patching;
	private int askingTicks;
	private int liveGoodTicks;
	private String lastStuckScene;
	private int repeatStuckCycles;
	private double thinkStartY;

	BorerAreaThink(DefaultTunnelBorerEngine engine, BorerArea area) {
		this.engine = engine;
		this.area = area;
	}

	/** 清空想想状态。 */
	void reset() {
		stillTicks = 0;
		current = null;
		tryTicks = 0;
		scene = null;
		tried.clear();
		lastPos = null;
		skipCooldown = 0;
		lastNoteTick = Long.MIN_VALUE;
		ticksSinceAsk = BorerAreaThinkPolicy.ASK_COOLDOWN_TICKS;
		shaftsSinceAsk = 0;
		asking = false;
		patching = false;
		askingTicks = 0;
		liveGoodTicks = 0;
		lastStuckScene = null;
		repeatStuckCycles = 0;
	}

	/** 想想试验是否进行中。 */
	boolean active() {
		return current != null;
	}

	/** 取消当前想想招数。 */
	void cancelMove() {
		current = null;
		tryTicks = 0;
		scene = null;
		tried.clear();
		stillTicks = 0;
	}

	/** 推进卡住计时。 */
	void nudgeStuck() {
		stillTicks = BorerAreaThinkPolicy.stuckTicksAfterHazard(stillTicks);
	}

	/** 根据现场更新想想进度与卡住判定。 */
	void note(Minecraft client, LocalPlayer player) {
		if (player == null || client.level == null) return;
		long now = client.level.getGameTime();
		if (now == lastNoteTick) return;
		lastNoteTick = now;
		if (memory == null) memory = BorerAreaThinkStore.load(client);
		if (skipCooldown > 0) skipCooldown--;
		ticksSinceAsk++;
		if (asking) {
			askingTicks++;
			if (BorerAreaThinkPolicy.askTimedOut(askingTicks, patching) && !BorerAreaThinkAsk.busy()) {
				asking = false;
				patching = false;
				askingTicks = 0;
				engine.fileLog(client, "area-think-ask timeout");
				BorerAiHud.end(engine.host, "Grok 超时", true);
			}
		}
		Vec3 pos = player.position();
		double distSqr = lastPos == null ? 0.0 : lastPos.distanceToSqr(pos);
		boolean moved = lastPos != null && BorerAreaThinkPolicy.moved(distSqr);
		boolean mining = engine.currentTarget != null
			&& client.gameMode != null
			&& client.gameMode.getDestroyStage() >= 0;
		lastPos = pos;
		if (current == BorerAreaThinkPolicy.Move.DESCEND) {
			if (BorerAreaThinkPolicy.acceptDescendWin(thinkStartY, player.getY())) {
				finish(client, true);
				return;
			}
			tryTicks++;
			if (!BorerAreaThinkPolicy.keepTrying(tryTicks)) finish(client, false);
			return;
		}
		if (moved || mining) {
			stillTicks = 0;
			if (current != null) {
				if (BorerAreaThinkPolicy.acceptThinkWin(mining, distSqr)) {
					finish(client, true);
					return;
				}
				// 微小位移只重置 still，不记 win；继续计 try 直到 TRY_TICKS
				tryTicks++;
				if (!BorerAreaThinkPolicy.keepTrying(tryTicks)) finish(client, false);
				return;
			}
			liveGoodTicks++;
			if (liveGoodTicks >= BorerAreaThinkPolicy.LIVE_CREDIT_TICKS) {
				liveGoodTicks = 0;
				creditLive(client, player, mining);
			}
			return;
		}
		liveGoodTicks = 0;
		stillTicks++;
		if (current != null) {
			tryTicks++;
			if (!BorerAreaThinkPolicy.keepTrying(tryTicks)) finish(client, false);
			return;
		}
		if (BorerAreaThinkPolicy.stuck(stillTicks, false)) begin(client, player);
	}

	/** 本井挖完时通知想想。 */
	void onShaftDone(Minecraft client, LocalPlayer player) {
		shaftsSinceAsk++;
		maybeAsk(client, player, false);
	}

	/** 当前招要挖的目标格；无则 null。 */
	BlockPos mineTarget(Minecraft client, LocalPlayer player) {
		if (current == null || engine.areaShaftColumn == null) return null;
		int topY = engine.areaMax.getY();
		int colX = engine.areaShaftColumn.getX();
		int colZ = engine.areaShaftColumn.getZ();
		return switch (current) {
			case MINE_LOOKED -> area.lookedMineable(client, player);
			case MINE_FRONT -> area.flyObstruction(client, player, colX, colZ, topY);
			case DESCEND -> area.descendToShaftTop(client, player, colX, colZ, topY);
			default -> null;
		};
	}

	/** 推进本模块一拍；已处理返回 true。 */
	boolean handle(Minecraft client, LocalPlayer player) {
		if (current == null) return false;
		if (!area.allowThinkMove(current)) {
			engine.fileLog(client, "area-think cancel deterministic-phase move=" + current.name());
			current = null;
			tryTicks = 0;
			tried.clear();
			return false;
		}
		if (engine.areaMin == null || engine.areaMax == null || engine.areaShaftColumn == null) {
			engine.fileLog(client, "area-think skip reason=no-shaft-column move=" + current.name());
			current = null;
			tryTicks = 0;
			return false;
		}
		engine.status = "想想：" + current.label;
		engine.overlay(client, engine.status, 0xFFFF55);
		BorerAiHud.note(engine.host, "试试：" + current.label);
		int topY = engine.areaMax.getY();
		int colX = engine.areaShaftColumn.getX();
		int colZ = engine.areaShaftColumn.getZ();
		return switch (current) {
			case MINE_LOOKED, MINE_FRONT -> mineNow(client, player);
			case DESCEND -> descendNow(client, player, colX, colZ, topY);
			case FLY_LEVEL, FLY_UP -> flyNow(client, player, colX, colZ, topY, current == BorerAreaThinkPolicy.Move.FLY_UP);
			case RELEASE_FORWARD -> {
				if (engine.centerOnShaftColumn(client, player)) {
					engine.status = "想想：先回到格心";
					engine.overlay(client, engine.status, 0xFFFF55);
					yield true;
				}
				releaseKeys(client);
				yield true;
			}
			case SKIP_SHAFT -> {
				area.advanceShaft(client, colX, colZ, topY);
				skipCooldown = BorerAreaThinkPolicy.SKIP_COOLDOWN_TICKS;
				finish(client, true);
				yield true;
			}
		};
	}

	/** 立刻按当前招挖一拍。 */
	private boolean mineNow(Minecraft client, LocalPlayer player) {
		BlockPos pos = mineTarget(client, player);
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		if (pos != null) {
			engine.setMiningTarget(client, player, pos, "area-think-" + current.name());
			engine.frontOccluded = false;
		} else {
			client.options.keyAttack.setDown(false);
		}
		return true;
	}

	/** 立刻下降/进井一拍。 */
	private boolean descendNow(Minecraft client, LocalPlayer player, int colX, int colZ, int topY) {
		if (area.tryDescendShaft(client, player, colX, colZ,
			BorerAreaPolicy.shaftBottomY(engine.areaBoundedDown, engine.areaMin.getY()),
			player.blockPosition())) {
			return true;
		}
		BlockPos down = area.descendToShaftTop(client, player, colX, colZ, topY);
		if (down != null) {
			engine.setMiningTarget(client, player, down, "area-think-descend");
			client.options.keyUp.setDown(false);
			client.options.keyJump.setDown(false);
			return true;
		}
		engine.fallDown(client, player, "想想：往下挖");
		return true;
	}

	/** 想想：飞向竖井；climb 时按跳升高。 */
	private boolean flyNow(
		Minecraft client, LocalPlayer player, int colX, int colZ, int topY, boolean climb
	) {
		if (climb && !BorerAreaThinkPolicy.allowFlyUp(engine.areaRelocating, destRelOf(scene))) {
			engine.fallDown(client, player, "想想：目标在下面，下去");
			return true;
		}
		engine.enableMeteorFlight(player);
		if (area.flyToShaft(client, player, colX, colZ, topY)) {
			if (climb) {
				client.options.keyJump.setDown(true);
				client.options.keyShift.setDown(false);
			} else {
				client.options.keyJump.setDown(false);
			}
			engine.status = "想想：" + current.label;
			engine.overlay(client, engine.status, 0xFFFF55);
			return true;
		}
		if (climb) {
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			return true;
		}
		return true;
	}

	/** 松开本模块按下的键。 */
	private static void releaseKeys(Minecraft client) {
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
		client.options.keyAttack.setDown(false);
		client.options.keyLeft.setDown(false);
		client.options.keyRight.setDown(false);
	}

	/** 开始一轮想想试验。 */
	private void begin(Minecraft client, LocalPlayer player) {
		String nextScene = sceneOf(client, player);
		if (nextScene.equals(lastStuckScene)) {
			repeatStuckCycles++;
		} else {
			lastStuckScene = nextScene;
			repeatStuckCycles = 1;
		}
		scene = nextScene;
		tried.clear();
		tryTicks = 0;
		if (repeatStuckCycles >= BorerAreaThinkPolicy.REPEAT_STUCK_ASK) {
			maybeAsk(client, player, true);
		}
		pick(client, player);
		if (current != null) {
			engine.fileLog(client, "area-think start scene=" + scene
				+ " move=" + current.name()
				+ " repeat=" + repeatStuckCycles);
			BorerAiHud.begin(engine.host, "想想");
			BorerAiHud.note(engine.host, "试试：" + current.label);
		}
	}

	/** 结束本轮想想试验并记胜负。 */
	private void finish(Minecraft client, boolean win) {
		if (current != null && scene != null) {
			BorerAreaThinkStore.record(memory, scene, current, win);
			BorerAreaThinkStore.save(client, memory);
			engine.fileLog(client, "area-think " + (win ? "win" : "fail")
				+ " scene=" + scene + " move=" + current.name());
		}
		if (win) {
			current = null;
			tryTicks = 0;
			tried.clear();
			stillTicks = 0;
			return;
		}
		pick(client, client.player);
	}

	/** 挑选下一招。 */
	private void pick(Minecraft client, LocalPlayer player) {
		if (player == null) {
			current = null;
			return;
		}
		BorerAreaThinkPolicy.Move[] all = BorerAreaThinkPolicy.Move.values();
		int[] wins = new int[all.length];
		int[] losses = new int[all.length];
		for (int i = 0; i < all.length; i++) {
			wins[i] = BorerAreaThinkStore.wins(memory, scene, all[i]);
			losses[i] = BorerAreaThinkStore.losses(memory, scene, all[i]);
		}
		List<BorerAreaThinkPolicy.Move> order = BorerAreaThinkPolicy.order(wins, losses);
		for (BorerAreaThinkPolicy.Move move : order) {
			if (tried.contains(move)) continue;
			if (!area.allowThinkMove(move)) continue;
			if (move == BorerAreaThinkPolicy.Move.SKIP_SHAFT
				&& !BorerAreaThinkPolicy.allowSkipShaft(skipCooldown)) {
				continue;
			}
			if (move == BorerAreaThinkPolicy.Move.FLY_UP
				&& !BorerAreaThinkPolicy.allowFlyUp(engine.areaRelocating, destRelOf(scene))) {
				continue;
			}
			tried.add(move);
			current = move;
			tryTicks = 0;
			thinkStartY = player.getY();
			return;
		}
		tried.clear();
		stillTicks = 0;
		current = null;
		maybeAsk(client, player, true);
	}

	/** 根据现场进展记分。 */
	private void creditLive(Minecraft client, LocalPlayer player, boolean mining) {
		BorerAreaThinkPolicy.Move move = BorerAreaThinkPolicy.liveMove(
			engine.areaRelocating,
			mining,
			BorerFlight.isFlying(player),
			engine.areaMax != null && BorerAreaThinkPolicy.destRel(
				engine.areaMax.getY() - player.blockPosition().getY()).equals("below"));
		if (move == null) return;
		String liveScene = sceneOf(client, player);
		BorerAreaThinkStore.record(memory, liveScene, move, true);
		BorerAreaThinkStore.save(client, memory);
	}

	/** 卡住时考虑问 Grok。 */
	private void maybeAsk(Minecraft client, LocalPlayer player, boolean allFailed) {
		boolean busy = BorerAreaThinkAsk.busy();
		boolean canAsk = BorerAreaThinkAsk.canAsk(client);
		if (busy || !BorerAreaThinkPolicy.shouldAskAi(
			canAsk, asking, ticksSinceAsk, allFailed, shaftsSinceAsk, repeatStuckCycles)) {
			String reason = BorerAreaThinkPolicy.askSkipReason(
				busy, canAsk, asking, ticksSinceAsk, allFailed, shaftsSinceAsk, repeatStuckCycles);
			engine.fileLog(client, "area-think-ask-skip reason=" + reason
				+ " " + BorerAreaThinkAsk.probeText());
			if ("no-grok-or-key".equals(reason)) {
				BorerAiHud.begin(engine.host, "Grok · 盾构想想");
				BorerAiHud.end(engine.host,
					"游戏没读到 Grok 登录。命令行能聊也要 ~/.grok/auth.json；已改成读 HOME 而不只 user.home",
					true);
			}
			return;
		}
		boolean patch = BorerAreaThinkPolicy.shouldPatchCode(
			BorerAreaThinkAsk.grokAvailable(),
			BorerAreaThinkAsk.sourceRoot(client) != null,
			allFailed);
		asking = true;
		patching = patch;
		askingTicks = 0;
		ticksSinceAsk = 0;
		shaftsSinceAsk = 0;
		engine.status = patch ? "Grok 正在改挖矿代码" : "问问本地 Grok";
		engine.overlay(client, engine.status, 0x55FFFF);
		BorerAiHud.begin(engine.host, "Grok · 盾构想想");
		BorerAiHud.note(engine.host, patch ? "准备改挖矿代码" : "准备问招数");
		engine.fileLog(client, "area-think-ask scene="
			+ (scene == null ? sceneOf(client, player) : scene)
			+ " grok=" + BorerAreaThinkAsk.grokAvailable()
			+ " patch=" + patch
			+ " repeat=" + repeatStuckCycles);
		String scores = scoreSummary();
		String logTail = BorerFileLog.tail(client, 40);
		String askScene = scene == null ? sceneOf(client, player) : scene;
		BorerAreaThinkAsk.ask(client, askScene, scores, logTail, patch, engine.runtimeVersion(),
			step -> BorerAiHud.note(engine.host, step),
			advice -> {
				asking = false;
				patching = false;
				askingTicks = 0;
				applyAdvice(client, askScene, advice);
				BorerAiHud.end(engine.host, hudResult(advice), false);
			}, () -> {
				asking = false;
				patching = false;
				askingTicks = 0;
				engine.fileLog(client, "area-think-ask-fail");
				engine.status = "Grok 问问失败";
				engine.overlay(client, engine.status, 0xFF5555);
				BorerAiHud.end(engine.host, "问问失败", true);
			});
	}

	/** 胜负分数摘要。 */
	private String scoreSummary() {
		if (memory == null || scene == null) return "";
		StringBuilder out = new StringBuilder();
		for (BorerAreaThinkPolicy.Move move : BorerAreaThinkPolicy.Move.values()) {
			out.append(move.name())
				.append(" w=").append(BorerAreaThinkStore.wins(memory, scene, move))
				.append(" l=").append(BorerAreaThinkStore.losses(memory, scene, move))
				.append('\n');
		}
		return out.toString();
	}

	/** 把建议应用到现场动作。 */
	private void applyAdvice(Minecraft client, String askScene, BorerAreaThinkAsk.Advice advice) {
		if (advice == null) return;
		for (BorerAreaThinkPolicy.Move move : advice.prefer) {
			BorerAreaThinkStore.record(memory, askScene, move, true);
			BorerAreaThinkStore.record(memory, askScene, move, true);
		}
		for (BorerAreaThinkPolicy.Move move : advice.avoid) {
			BorerAreaThinkStore.record(memory, askScene, move, false);
		}
		BorerAreaThinkStore.save(client, memory);
		if (advice.lesson != null && !advice.lesson.isBlank()) {
			BorerAreaThinkStore.appendLesson(client, advice.lesson);
		}
		if (advice.deployed) {
			engine.status = "已编译新引擎 " + advice.version + "，等热加载";
			engine.overlay(client, engine.status, 0x55FF55);
		} else if (advice.patched) {
			engine.status = "Grok 改了代码但还没装上";
			engine.overlay(client, engine.status, 0xFFAA00);
		} else if (advice.lesson != null && !advice.lesson.isBlank()) {
			engine.status = "Grok 课：" + advice.lesson;
			engine.overlay(client, engine.status, 0x55FF55);
		}
		engine.fileLog(client, "area-think-ask-ok prefer=" + advice.prefer + " avoid=" + advice.avoid
			+ " patched=" + advice.patched + " deployed=" + advice.deployed
			+ " version=" + advice.version);
	}

	/** 建议结果的 HUD 文案。 */
	private static String hudResult(BorerAreaThinkAsk.Advice advice) {
		if (advice == null) return "看过了";
		if (advice.deployed) return "已编译新引擎 " + advice.version;
		if (advice.patched) return "改了代码但还没装上";
		if (advice.lesson != null && !advice.lesson.isBlank()) return advice.lesson;
		return "看过了";
	}

	/** 当前场景键。 */
	private String sceneOf(Minecraft client, LocalPlayer player) {
		if (engine.areaMax == null) return "unknown|walk|same|open|none|far";
		int topY = engine.areaMax.getY();
		BlockPos feet = player.blockPosition();
		BlockPos dest = engine.areaShaftColumn == null
			? feet
			: BorerAreaPolicy.shaftStandPos(engine.areaShaftColumn.getX(), engine.areaShaftColumn.getZ(), topY);
		double horiz = Math.hypot((dest.getX() + 0.5) - player.getX(), (dest.getZ() + 0.5) - player.getZ());
		Direction dir = engine.headingToward(feet, dest);
		if (dir == null) dir = engine.forward;
		boolean frontSolid = dir != null && (engine.hasCollision(client, feet.relative(dir))
			|| engine.hasCollision(client, feet.relative(dir).above()));
		boolean hasHit = client.hitResult instanceof BlockHitResult hit
			&& hit.getType() == HitResult.Type.BLOCK;
		boolean inArea = false;
		if (hasHit) {
			BlockPos look = ((BlockHitResult) client.hitResult).getBlockPos();
			inArea = engine.areaMin != null && BorerAreaPolicy.containsXZ(
				look.getX(), look.getZ(),
				engine.areaMin.getX(), engine.areaMin.getZ(),
				engine.areaMax.getX(), engine.areaMax.getZ());
		}
		Integer targetY = engine.currentTarget == null ? null : engine.currentTarget.getY();
		return BorerAreaThinkPolicy.sceneKey(
			engine.areaRelocating,
			BorerFlight.isFlying(player),
			BorerAreaThinkPolicy.destRel(BorerAreaPolicy.thinkDestDy(
				engine.areaRelocating, topY, feet.getY(), targetY)),
			frontSolid,
			BorerAreaThinkPolicy.lookKind(hasHit, inArea),
			BorerAreaPolicy.mineAdjacentShaftInsteadOfFly(horiz));
	}

	/** 场景键对应的相对高度档。 */
	private static String destRelOf(String sceneKey) {
		if (sceneKey == null) return "same";
		String[] parts = sceneKey.split("\\|", 4);
		return parts.length >= 3 ? parts[2] : "same";
	}
}
