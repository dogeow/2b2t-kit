package dev.twob2tkit.chopper;

import dev.twob2tkit.runtime.engine.BorerAim;
import dev.twob2tkit.runtime.engine.BorerFlight;
import dev.twob2tkit.runtime.engine.BorerItems;
import dev.twob2tkit.runtime.engine.BorerThreats;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.AxeItem;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ShearsItem;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.HashSet;
import java.util.Iterator;
import java.util.Locale;
import java.util.Set;
import dev.twob2tkit.ApproachTracker;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitKeys;

/**
 * 自动挖树：找连通原木 → 够得着就砍 → 可选捡掉落物与补种。
 * <p>
 * 移动/挖掘走原版按键，飞行只在目标明显高于站立触及距离时开；
 * 遇战停砍切剑。过程写入 {@code chopper.log}。
 */
public final class AutoChopper {
	/** 挖树主机逻辑版本（打进诊断日志）。 */
	public static final String VERSION = "1.6.200";
	/** 无进度时多久再点一次攻击（tick）。 */
	private static final int RETRY_TICKS = 40;
	/** 挖不动多久跳过这块（tick）。 */
	private static final int STALL_TICKS = 200;
	/** 走近卡住多久换树（tick）。 */
	private static final int STUCK_TICKS = 100;
	/** 周期性诊断间隔（tick）。 */
	private static final int LOG_EVERY_TICKS = 40;

	private final KitConfig config;
	private final ChopperLoot loot = new ChopperLoot();
	private final Set<BlockPos> treeLogs = new HashSet<>();
	private final Set<BlockPos> stumps = new HashSet<>();
	private final Set<BlockPos> ignored = new HashSet<>();
	private boolean active;
	private String status = "";
	private BlockPos mineTarget;
	private BlockPos walkTarget;
	private Item saplingItem;
	private int mineTicks;
	private int lastDestroyStage = -1;
	private int choppedLogs;
	private int treesDone;
	private int replanted;
	private final ApproachTracker approach = new ApproachTracker();
	private int searchCooldown;
	private int replantDelay;
	private Vec3 mineLook;
	private int combatPauseTicks;
	private int flyToggleCooldown;
	private boolean flightHeld;
	/** 当前这棵树还没走完「砍完 → 捡木头 → 补种」。空树干时不能直接锁下一棵。 */
	private boolean currentTreeOpen;
	private int logTicks;
	private String lastFileLog = "";
	private double flightHorizBest = Double.MAX_VALUE;
	private int flightHorizTicks;
	private BlockPos flightDest;

	public AutoChopper(KitConfig config) {
		this.config = config;
	}

	/** 是否正在挖树。 */
	public boolean isActive() {
		return active;
	}

	/** 最近一条状态文案（界面与 HUD 共用）。 */
	public String status() {
		return status;
	}

	/** 本局已砍原木数（含旁人挖掉的连通块）。 */
	public int choppedLogs() {
		return choppedLogs;
	}

	/** 本局完成的棵数。 */
	public int treesDone() {
		return treesDone;
	}

	/** 本局补种次数。 */
	public int replanted() {
		return replanted;
	}

	/** 本局捡到的掉落物件数。 */
	public int pickedLoot() {
		return loot.picked();
	}

	/** 开始挖树：清状态、写配置相关开关到日志、发聊天提示。 */
	public void start(Minecraft client) {
		if (client.player == null || client.level == null) return;
		active = true;
		clearTree();
		ignored.clear();
		loot.resetSession();
		loot.setCollectLeaves(config.chopperLeaves);
		choppedLogs = 0;
		treesDone = 0;
		replanted = 0;
		searchCooldown = 0;
		combatPauseTicks = 0;
		flyToggleCooldown = 0;
		flightHeld = false;
		logTicks = 0;
		lastFileLog = "";
		status = "开始找树";
		ChopperKeys.message(client, "自动挖树已开启。够得着就站着砍，够不着才飞。树叶会换剪刀。再按 "
			+ KitKeys.boundLabel(KitKeys.TOGGLE_CHOPPER) + " 或 End 停止");
		fileLog(client, "start player=" + precisePosition(client.player)
			+ " range=" + formatRange()
			+ " walk=" + config.chopperWalk
			+ " leaves=" + config.chopperLeaves
			+ " pickup=" + config.chopperPickup);
	}

	/** 停止挖树：松键、关本模块开的飞行、写日志与聊天。 */
	public void stop(Minecraft client, String reason) {
		if (!active) return;
		int pickedLoot = loot.picked();
		active = false;
		clearTree();
		ignored.clear();
		loot.resetSession();
		releaseFlight(client.player);
		ChopperKeys.holdStill(client);
		status = "已停止：" + reason;
		fileLog(client, "stop reason=" + reason
			+ " chopped=" + choppedLogs + " trees=" + treesDone + " loot=" + pickedLoot);
		ChopperKeys.message(client, "自动挖树已停止：" + reason
			+ (choppedLogs > 0 ? "（砍了 " + choppedLogs + " 根原木，" + treesDone + " 棵树，捡了 " + pickedLoot + " 个）" : ""));
	}

	/**
	 * 每拍主循环：遇战 → 捡物/补种/找树 → 砍目标或走近。
	 * <p>
	 * 副作用：改按键、朝向、飞行与 {@code hitResult}。
	 */
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		if (client.screen != null) {
			ChopperKeys.releaseMine(client);
			ChopperKeys.releaseWalk(client);
			status = "先关掉界面再砍";
			return;
		}

		LocalPlayer player = client.player;
		if (flyToggleCooldown > 0) flyToggleCooldown--;
		if (updateCombatPause(client, player)) return;
		pruneGone(client);
		if (ignored.size() > 800) ignored.clear();
		logTicks++;
		if (logTicks % LOG_EVERY_TICKS == 0) logPeriodic(client, player);

		if (treeLogs.isEmpty()) {
			boolean moreLeaves = config.chopperLeaves && currentTreeOpen && nearestLeaf(client, player) != null;
			if (!moreLeaves) {
				if (currentTreeOpen) finishTree(client);
				if (!loot.miningObstacle()) ChopperKeys.releaseMine(client);
				if (config.chopperPickup && loot.active()) {
					status = "去捡掉落物";
					boolean fly = loot.wantsFlight(client, player);
					applyFlight(player, fly);
					boolean collecting = loot.tick(client, player);
					mineLook = loot.look();
					if (collecting) {
						if (mineLook != null) {
							fileLogOnce(client, "loot-go dest=" + format(BlockPos.containing(mineLook))
								+ " fly=" + fly
								+ " flying=" + BorerFlight.isFlying(player));
						}
						return;
					}
				}
				if (replantDelay > 0) {
					replantDelay--;
					applyFlight(player, false);
					ChopperKeys.holdStill(client);
					return;
				}
				if (config.chopperReplant && !stumps.isEmpty()) {
					if (tryReplant(client, player)) return;
					stumps.clear();
				}
				if (searchCooldown > 0) {
					searchCooldown--;
					applyFlight(player, false);
					ChopperKeys.holdStill(client);
					status = "附近暂时没有树";
					ChopperKeys.overlay(client, status, 0xA0A0A0);
					return;
				}
				if (!lockNextTree(client, player)) {
					applyFlight(player, false);
					if (config.chopperPickup && loot.beginNear(client, player)) {
						status = "没有新树，先捡剩下的掉落物";
						applyFlight(player, loot.wantsFlight(client, player));
						boolean collecting = loot.tick(client, player);
						mineLook = loot.look();
						if (collecting) return;
					}
					searchCooldown = 20;
					ChopperKeys.holdStill(client);
					status = "附近 " + formatRange() + " 格没有可砍的树";
					ChopperKeys.overlay(client, status, 0xA0A0A0);
					return;
				}
			}
		}

		BlockPos next = pickMineTarget(client, player);
		if (next == null) {
			ChopperKeys.releaseMine(client);
			if (config.chopperWalk && walkTarget != null && !BorerAim.inReach(player, walkTarget)) {
				if (!approach(client, player, walkTarget)) return;
				status = "走向树干 " + format(walkTarget) + BorerAim.reachInfo(player, walkTarget);
				ChopperKeys.overlay(client, status, 0x55FFFF);
				return;
			}
			finishTree(client);
			return;
		}

		BlockHitResult hit = BorerAim.firstMineable(client, player, next, pos -> isMineableTreeBlock(client, pos) && !ignored.contains(pos));
		if (hit != null) {
			boolean fly = keepFlyingFor(player, hit.getBlockPos());
			applyFlight(player, fly);
			if (mine(client, player, hit.getBlockPos(), hit)) {
				if (fly) holdFlightToward(client, player, mineTarget != null ? mineTarget : hit.getBlockPos());
				else ChopperKeys.releaseWalk(client);
				status = "砍 " + label(client, mineTarget != null ? mineTarget : hit.getBlockPos())
					+ BorerAim.reachInfo(player, mineTarget != null ? mineTarget : hit.getBlockPos())
					+ "  已砍 " + choppedLogs + " 根 / " + treesDone + " 棵";
				ChopperKeys.overlay(client, status, 0x55FF55);
				emitGizmos(client);
				return;
			}
			fileLogOnce(client, "mine-fail target=" + format(next)
				+ " hit=" + format(hit.getBlockPos()) + " " + BorerAim.reachInfo(player, next)
				+ " player=" + precisePosition(player)
				+ " flying=" + BorerFlight.isFlying(player));
		}

		ChopperKeys.releaseMine(client);
		if (!config.chopperWalk) {
			ChopperKeys.holdStill(client);
			status = "太远" + BorerAim.reachInfo(player, next) + "，走近一点或打开「走近再砍」";
			ChopperKeys.overlay(client, status, 0xFFFF55);
			return;
		}
		if (!approach(client, player, next)) return;
		status = (hit != null ? "树叶挡住，飞近再砍 " : "走近 ")
			+ label(client, next) + BorerAim.reachInfo(player, next);
		ChopperKeys.overlay(client, status, 0x55FFFF);
		emitGizmos(client);
	}

	/** Meteor 改朝向后写回挖树/捡物瞄准。 */
	public void reapplyLook(Minecraft client) {
		if (!active || combatPauseTicks > 0 || client.player == null || client.screen != null) return;
		if (mineLook != null) {
			ChopperKeys.reapplySmoothLook(client.player);
			return;
		}
		if (mineTarget != null) ChopperKeys.reapplySmoothLook(client.player);
		else if (loot.active()) ChopperKeys.lookAt(client.player, loot.origin());
	}

	/** 当前树原木砍完：计数、可选开捡物、设补种延迟。 */
	private void finishTree(Minecraft client) {
		if (!currentTreeOpen || !treeLogs.isEmpty()) return;
		currentTreeOpen = false;
		treesDone++;
		replantDelay = config.chopperReplant ? 12 : 4;
		if (config.chopperPickup) {
			BlockPos start = walkTarget != null ? walkTarget
				: !stumps.isEmpty() ? stumps.iterator().next()
				: client.player != null ? client.player.blockPosition() : null;
			if (start != null) loot.begin(start, saplingItem);
		}
		mineTarget = null;
		walkTarget = null;
		status = config.chopperPickup ? "这棵砍完了，去捡掉落物" : "这棵砍完了，共 " + treesDone + " 棵";
		ChopperKeys.overlay(client, status, 0x55FFFF);
	}

	/** 扫描并锁定最近一棵合法树；失败返回 false。 */
	private boolean lockNextTree(Minecraft client, LocalPlayer player) {
		clearTree();
		int range = Math.max(4, (int)Math.round(config.chopperRange));
		ChopperTrees.Tree best = ChopperTrees.findNearest(client, player, range, config.chopperRequireLeaves, ignored);
		if (best == null) return false;
		treeLogs.addAll(best.logs());
		stumps.addAll(best.stumps());
		walkTarget = best.base().immutable();
		saplingItem = ChopperTrees.saplingFor(client.level.getBlockState(best.base()).getBlock());
		approach.reset();
		currentTreeOpen = true;
		status = "锁定一棵树，约 " + best.logs().size() + " 根原木";
		fileLog(client, "lock-tree logs=" + best.logs().size()
			+ " base=" + format(best.base())
			+ " player=" + precisePosition(player));
		return true;
	}

	/** 优先够得着的原木，否则按高度+距离；可切到附近树叶。 */
	private BlockPos pickMineTarget(Minecraft client, LocalPlayer player) {
		if (mineTarget != null && stillValid(client, mineTarget)) {
			return mineTarget;
		}
		mineTarget = null;
		mineTicks = 0;
		lastDestroyStage = -1;

		BlockPos best = null;
		double bestScore = Double.MAX_VALUE;
		for (BlockPos log : treeLogs) {
			if (!stillValid(client, log)) continue;
			double dist = player.getEyePosition().distanceToSqr(Vec3.atCenterOf(log));
			double score;
			if (BorerAim.inReach(player, log)) {
				score = dist - 1_000_000.0;
			} else {
				score = log.getY() * 32.0 + dist * 0.05;
			}
			if (score < bestScore) {
				bestScore = score;
				best = log;
			}
		}
		if (best == null && config.chopperLeaves) {
			best = nearestLeaf(client, player);
		}
		if (best == null) return null;
		mineTarget = best.immutable();
		return mineTarget;
	}

	/** 树桩/树干附近够得着的最近树叶。 */
	private BlockPos nearestLeaf(Minecraft client, LocalPlayer player) {
		BlockPos best = null;
		double bestDist = Double.MAX_VALUE;
		int range = 4;
		for (BlockPos log : stumps.isEmpty() ? treeLogs : stumps) {
			for (int dx = -range; dx <= range; dx++) {
				for (int dy = -1; dy <= 6; dy++) {
					for (int dz = -range; dz <= range; dz++) {
						BlockPos pos = log.offset(dx, dy, dz);
						if (!client.level.getBlockState(pos).is(BlockTags.LEAVES) || !ChopperTrees.canBreak(client, pos)) continue;
						if (!BorerAim.inReach(player, pos)) continue;
						double dist = player.getEyePosition().distanceToSqr(Vec3.atCenterOf(pos));
						if (dist < bestDist) {
							bestDist = dist;
							best = pos.immutable();
						}
					}
				}
			}
		}
		return best;
	}

	/** 原木或树叶且允许破坏。 */
	private boolean isMineableTreeBlock(Minecraft client, BlockPos pos) {
		if (!ChopperTrees.canBreak(client, pos)) return false;
		BlockState state = client.level.getBlockState(pos);
		return ChopperTrees.isWood(state) || state.is(BlockTags.LEAVES);
	}

	/**
	 * 对准并挖一块树相关方块；准星跑偏则改挖准星命中块。
	 *
	 * @return true 本拍已在挖；false 对不齐或卡住已跳过
	 */
	private boolean mine(Minecraft client, LocalPlayer player, BlockPos pos, BlockHitResult hit) {
		if (hit == null || !BorerAim.hitInReach(player, hit)) {
			if (mineTarget != null && mineTarget.equals(pos)) mineTarget = null;
			return false;
		}
		boolean fresh = !pos.equals(mineTarget) || mineTicks == 0;
		if (!pos.equals(mineTarget)) {
			mineTarget = pos.immutable();
			mineTicks = 0;
			lastDestroyStage = -1;
		}
		int stage = client.gameMode.getDestroyStage();
		if (stage > lastDestroyStage) {
			lastDestroyStage = stage;
			mineTicks = 0;
		} else {
			mineTicks++;
		}
		if (mineTicks >= STALL_TICKS) {
			ignored.add(pos.immutable());
			treeLogs.remove(pos);
			mineTarget = null;
			ChopperKeys.releaseMine(client);
			status = label(client, pos) + " 挖不动，跳过";
			fileLog(client, "stall skip=" + format(pos) + " block=" + label(client, pos)
				+ " player=" + precisePosition(player));
			return false;
		}
		mineLook = BorerAim.lookPoint(hit);
		ChopperKeys.smoothLookAt(player, mineLook, 40.0F);
		BlockHitResult aimed = BorerAim.clipToward(client, player, mineLook);
		if (aimed != null && BorerAim.hitInReach(player, aimed) && isMineableTreeBlock(client, aimed.getBlockPos())
			&& !ignored.contains(aimed.getBlockPos())) {
			if (!aimed.getBlockPos().equals(pos)) {
				fileLogOnce(client, "clip-switch from=" + format(pos)
					+ " to=" + format(aimed.getBlockPos())
					+ " block=" + label(client, aimed.getBlockPos())
					+ " player=" + precisePosition(player));
				pos = aimed.getBlockPos().immutable();
				mineTarget = pos;
				hit = aimed;
				mineLook = BorerAim.lookPoint(aimed);
				ChopperKeys.smoothLookAt(player, mineLook, 40.0F);
			}
		} else {
			fileLogOnce(client, "clip-miss target=" + format(pos)
				+ " aimed=" + (aimed == null ? "-" : format(aimed.getBlockPos()))
				+ " player=" + precisePosition(player));
			if (mineTarget != null && mineTarget.equals(pos)) mineTarget = null;
			ChopperKeys.releaseMine(client);
			return false;
		}
		selectTool(client, aimed.getBlockPos());
		client.hitResult = aimed;
		client.crosshairPickEntity = null;
		if (fresh || mineTicks > 0 && mineTicks % RETRY_TICKS == 0) {
			ChopperKeys.clickAttack(client);
		}
		client.options.keyAttack.setDown(true);
		try {
			Gizmos.cuboid(pos, GizmoStyle.strokeAndFill(0xFF00FFFF, 2.6F, 0x3300FFFF));
		} catch (IllegalStateException ignored) {
		}
		return true;
	}

	/** 在树桩上补种对应树苗；够不着则走近。成功或正在走近返回 true。 */
	private boolean tryReplant(Minecraft client, LocalPlayer player) {
		if (saplingItem == null || !hasItem(player, saplingItem)) {
			status = saplingItem == null ? "这棵树没有对应树苗，下一棵" : "背包没有树苗，先不补种";
			return false;
		}
		for (Iterator<BlockPos> iterator = stumps.iterator(); iterator.hasNext(); ) {
			BlockPos stump = iterator.next();
			if (ChopperTrees.isWood(client.level.getBlockState(stump))) continue;
			BlockPos soil = client.level.getBlockState(stump).canBeReplaced() ? stump.below() : stump;
			BlockPos plant = soil.above();
			if (!client.level.getBlockState(plant).canBeReplaced() && !client.level.getBlockState(plant).isAir()) {
				iterator.remove();
				continue;
			}
			if (!(saplingItem instanceof BlockItem blockItem)) {
				iterator.remove();
				continue;
			}
			if (!blockItem.getBlock().defaultBlockState().canSurvive(client.level, plant)) {
				iterator.remove();
				continue;
			}
			if (!BorerAim.inReach(player, soil)) {
				if (config.chopperWalk) {
					approach(client, player, soil);
					status = "去补种 " + new ItemStack(saplingItem).getHoverName().getString();
					ChopperKeys.overlay(client, status, 0x55FFFF);
					return true;
				}
				continue;
			}
			ChopperKeys.releaseWalk(client);
			InteractionHand hand = selectItem(client, saplingItem);
			if (hand == null) return false;
			Vec3 click = Vec3.atCenterOf(soil).add(0.0, 0.51, 0.0);
			ChopperKeys.lookAt(player, click);
			InteractionResult result = client.gameMode.useItemOn(player, hand, new BlockHitResult(click, Direction.UP, soil, false));
			player.swing(hand);
			if (result.consumesAction() || client.level.getBlockState(plant).is(blockItem.getBlock())) {
				replanted++;
				iterator.remove();
				status = "已补种 " + new ItemStack(saplingItem).getHoverName().getString();
				ChopperKeys.overlay(client, status, 0x55FF55);
				return true;
			}
			iterator.remove();
		}
		return false;
	}

	/**
	 * 走近目标格：卡住则整棵忽略；可选飞行。
	 *
	 * @return false 卡住已放弃；true 本拍已写入移动
	 */
	private boolean approach(Minecraft client, LocalPlayer player, BlockPos dest) {
		if (player.isPassenger()) {
			ChopperKeys.holdStill(client);
			status = "先下来再砍";
			ChopperKeys.overlay(client, status, 0xFFFF55);
			return false;
		}
		Vec3 destCenter = Vec3.atCenterOf(dest);
		double dist = Math.sqrt(BorerAim.nearestDistanceSqr(player.getEyePosition(), dest));
		if (approach.track(dest, dist, STUCK_TICKS)) {
			ignored.addAll(treeLogs);
			clearTree();
			ChopperKeys.holdStill(client);
			status = "过不去，换一棵";
			fileLog(client, "approach-stuck dest=" + format(dest)
				+ " dist=" + String.format(Locale.ROOT, "%.1f", dist)
				+ " player=" + precisePosition(player));
			ChopperKeys.overlay(client, status, 0xFFFF55);
			return false;
		}
		if (walkTarget == null || !walkTarget.equals(dest)) {
			walkTarget = dest.immutable();
		}
		mineLook = destCenter;
		ChopperKeys.lookAt(player, destCenter);
		boolean fly = keepFlyingFor(player, dest);
		applyFlight(player, fly);
		double horiz = Math.hypot(destCenter.x - player.getX(), destCenter.z - player.getZ());
		if (fly) {
			client.options.keyUp.setDown(horiz > 0.35);
			client.options.keyDown.setDown(false);
			client.options.keyJump.setDown(destCenter.y > player.getY() + 0.35);
			client.options.keyShift.setDown(destCenter.y < player.getY() - 0.25 && horiz < 1.2);
			return true;
		}
		client.options.keyUp.setDown(horiz > 0.2);
		client.options.keyDown.setDown(false);
		boolean stepUp = dest.getY() > player.getY() + 0.45 && dest.getY() <= player.getY() + 1.25;
		client.options.keyJump.setDown(stepUp && player.onGround());
		client.options.keyShift.setDown(false);
		return true;
	}

	/** 站着够得着就落地砍（空中挖掘只有 1/5 速度）。只在目标明显高于站立触及距离时才飞。 */
	private boolean keepFlyingFor(LocalPlayer player, BlockPos dest) {
		if (player == null || dest == null) return false;
		if (BorerAim.inReach(player, dest) && player.onGround()) return false;
		double reach = BorerAim.breakReach(player);
		double horiz = Math.hypot(dest.getX() + 0.5 - player.getX(), dest.getZ() + 0.5 - player.getZ());
		if (BorerAim.inReach(player, dest)) {
			return dest.getY() + 0.5 > player.getEyeY() + 0.35 && !player.onGround();
		}
		double standingEye = player.onGround()
			? player.getEyeY()
			: (walkTarget != null ? walkTarget.getY() + player.getEyeHeight() : player.getY() + player.getEyeHeight());
		return horiz <= 2.8 && dest.getY() + 0.5 > standingEye + reach - 0.35;
	}

	/** 飞高时按移动键；没在挖方块或盘旋时重新瞄准，避免樱花树叶挡准星空转。 */
	private void holdFlightToward(Minecraft client, LocalPlayer player, BlockPos dest) {
		if (dest == null) return;
		if (flightDest == null || !flightDest.equals(dest)) {
			flightDest = dest.immutable();
			flightHorizBest = Double.MAX_VALUE;
			flightHorizTicks = 0;
		}
		Vec3 center = Vec3.atCenterOf(dest);
		double horiz = Math.hypot(center.x - player.getX(), center.z - player.getZ());
		flightHorizTicks++;
		if (horiz + 0.5 < flightHorizBest) {
			flightHorizBest = horiz;
			flightHorizTicks = 0;
		}
		boolean mining = client.gameMode != null && client.gameMode.getDestroyStage() >= 0;
		boolean orbit = flightHorizTicks >= 20 && horiz > flightHorizBest + 0.5;
		if (!mining || orbit) {
			ChopperKeys.smoothLookAt(player, center, 40.0F);
			mineLook = center;
			if (orbit) {
				flightHorizBest = horiz;
				flightHorizTicks = 0;
			}
		}
		client.options.keyUp.setDown(horiz > 0.35);
		client.options.keyDown.setDown(false);
		client.options.keyJump.setDown(center.y > player.getY() + 0.35);
		client.options.keyShift.setDown(center.y < player.getY() - 0.25 && horiz < 1.2);
	}

	/** 按需开关本模块持有的飞行；玩家自开的飞行不抢关。 */
	private void applyFlight(LocalPlayer player, boolean wantFly) {
		if (player == null) return;
		if (flyToggleCooldown > 0) return;
		boolean flying = BorerFlight.isFlying(player);
		if (wantFly) {
			if (flying) return; // 玩家自己开的 Flight 不归本模块所有。
			if (!BorerFlight.ensureFlying(player, true)) return;
			flightHeld = true;
		} else {
			if (!flightHeld) return;
			if (flying && !BorerFlight.ensureFlying(player, false)) return;
			flightHeld = false;
		}
		flyToggleCooldown = 8;
	}

	/** 停止时关掉本模块开的飞行。 */
	private void releaseFlight(LocalPlayer player) {
		if (player != null && flightHeld && BorerFlight.isFlying(player)) {
			BorerFlight.ensureFlying(player, false);
		}
		flightHeld = false;
		flyToggleCooldown = 0;
	}

	/** 原木已消失则计入砍数并清无效挖掘目标。 */
	private void pruneGone(Minecraft client) {
		if (treeLogs.isEmpty()) return;
		int before = treeLogs.size();
		treeLogs.removeIf(pos -> !ChopperTrees.isWood(client.level.getBlockState(pos)));
		int removed = before - treeLogs.size();
		if (removed > 0) choppedLogs += removed;
		if (mineTarget != null && !stillValid(client, mineTarget)) {
			mineTarget = null;
			mineTicks = 0;
			lastDestroyStage = -1;
			ChopperKeys.releaseMine(client);
		}
	}

	/** 世界里画出当前树干（当前目标高亮）。 */
	private void emitGizmos(Minecraft client) {
		try {
			for (BlockPos log : treeLogs) {
				boolean current = log.equals(mineTarget);
				int stroke = current ? 0xFF00FFFF : 0xFFFFAA00;
				int fill = current ? 0x3300FFFF : 0x22FFAA00;
				Gizmos.cuboid(log, GizmoStyle.strokeAndFill(stroke, current ? 2.4F : 1.1F, fill));
			}
		} catch (IllegalStateException ignored) {
		}
	}

	/** 清空当前树锁定与瞄准状态（不含 ignored）。 */
	private void clearTree() {
		treeLogs.clear();
		stumps.clear();
		mineTarget = null;
		walkTarget = null;
		saplingItem = null;
		mineTicks = 0;
		lastDestroyStage = -1;
		approach.reset();
		mineLook = null;
		flightDest = null;
		flightHorizBest = Double.MAX_VALUE;
		flightHorizTicks = 0;
		ChopperKeys.resetSmoothLook();
		combatPauseTicks = 0;
		currentTreeOpen = false;
		loot.clear();
	}

	/** 被打或身边有敌对生物时松手、放开准星，方便自动攻击还手。 */
	private boolean updateCombatPause(Minecraft client, LocalPlayer player) {
		String combat = BorerThreats.combatPauseReason(player);
		String nearby = nearbyHostile(client, player);
		if (combat != null || nearby != null) combatPauseTicks = 40;
		if (combatPauseTicks <= 0) return false;
		combatPauseTicks--;
		mineLook = null;
		ChopperKeys.holdStill(client);
		String sword = BorerItems.selectWeapon(client, player) ? "，已切剑" : "";
		if (combat != null) status = combat + "，已停手" + sword;
		else if (nearby != null) status = "附近有 " + nearby + "，已停手" + sword;
		else status = "刚被打过，已停手" + sword;
		ChopperKeys.overlay(client, status, 0xFF5555);
		return true;
	}

	/** 半径内最近敌对生物显示名；没有则 null。 */
	private static String nearbyHostile(Minecraft client, LocalPlayer player) {
		if (client.level == null) return null;
		double radius = 8.0;
		AABB box = player.getBoundingBox().inflate(radius);
		for (Entity entity : client.level.getEntities(player, box)) {
			if (!(entity instanceof Enemy) || !entity.isAlive()) continue;
			if (player.distanceTo(entity) > radius) continue;
			return entity.getName().getString();
		}
		return null;
	}

	/** 目标仍是可砍原木，或（勾选/还在砍树时）可砍树叶。 */
	private boolean stillValid(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (ChopperTrees.isWood(state)) return ChopperTrees.canBreak(client, pos);
		if (!state.is(BlockTags.LEAVES) || !ChopperTrees.canBreak(client, pos)) return false;
		return config.chopperLeaves || !treeLogs.isEmpty();
	}

	/** 树叶换剪刀，否则换斧。 */
	private void selectTool(Minecraft client, BlockPos pos) {
		if (client.level != null && client.level.getBlockState(pos).is(BlockTags.LEAVES)) {
			selectShears(client);
			return;
		}
		selectAxe(client);
	}

	/** 快捷栏或背包换出斧子。 */
	private void selectAxe(Minecraft client) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().getItem() instanceof AxeItem) return;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).getItem() instanceof AxeItem) {
				inventory.setSelectedSlot(slot);
				return;
			}
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!(inventory.getItem(slot).getItem() instanceof AxeItem)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			return;
		}
	}

	/** 快捷栏或背包换出剪刀。 */
	private void selectShears(Minecraft client) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().getItem() instanceof ShearsItem) return;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).getItem() instanceof ShearsItem) {
				inventory.setSelectedSlot(slot);
				return;
			}
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!(inventory.getItem(slot).getItem() instanceof ShearsItem)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			return;
		}
	}

	/** 把指定物品握到主手（或副手已有则用副手）；找不到返回 null。 */
	private InteractionHand selectItem(Minecraft client, Item item) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().is(item)) return InteractionHand.MAIN_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			inventory.setSelectedSlot(slot);
			return InteractionHand.MAIN_HAND;
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			if (player.getMainHandItem().is(item)) return InteractionHand.MAIN_HAND;
		}
		if (player.getOffhandItem().is(item)) return InteractionHand.OFF_HAND;
		return null;
	}

	/** 背包（含双手）是否有该物品。 */
	private static boolean hasItem(LocalPlayer player, Item item) {
		if (player.getMainHandItem().is(item) || player.getOffhandItem().is(item)) return true;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (stack.is(item)) return true;
		}
		return false;
	}

	/** 搜寻范围文案（整数不带小数）。 */
	private String formatRange() {
		double range = Math.max(4.0, config.chopperRange);
		return range == Math.rint(range) ? Integer.toString((int)range) : String.format("%.1f", range);
	}

	/** 方块本地化名。 */
	private static String label(Minecraft client, BlockPos pos) {
		return client.level.getBlockState(pos).getBlock().getName().getString();
	}

	/** 方块坐标短串 {@code x,y,z}。 */
	private static String format(BlockPos pos) {
		return pos.getX() + "," + pos.getY() + "," + pos.getZ();
	}

	/** 玩家脚底精确坐标（诊断用）。 */
	private static String precisePosition(LocalPlayer player) {
		return String.format(Locale.ROOT, "%.3f,%.3f,%.3f", player.getX(), player.getY(), player.getZ());
	}

	/** 写入 chopper.log。 */
	private void fileLog(Minecraft client, String line) {
		ChopperFileLog.append(client, VERSION, line);
	}

	/** 相邻重复行只记一次，避免刷屏。 */
	private void fileLogOnce(Minecraft client, String line) {
		if (line.equals(lastFileLog)) return;
		lastFileLog = line;
		fileLog(client, line);
	}

	/** 周期性快照：动作、按键、准星与状态。 */
	private void logPeriodic(Minecraft client, LocalPlayer player) {
		String cross = "-";
		if (client.hitResult instanceof BlockHitResult hit && hit.getType() == HitResult.Type.BLOCK) {
			cross = format(hit.getBlockPos()) + "/" + hit.getDirection().getSerializedName();
		}
		fileLog(client, "periodic action=" + (mineTarget != null ? "MINE" : walkTarget != null ? "WALK" : loot.active() ? "LOOT" : "IDLE")
			+ " player=" + precisePosition(player)
			+ " flying=" + BorerFlight.isFlying(player)
			+ " onGround=" + player.onGround()
			+ " target=" + (mineTarget == null ? "-" : format(mineTarget))
			+ " walk=" + (walkTarget == null ? "-" : format(walkTarget))
			+ " logs=" + treeLogs.size()
			+ " stage=" + (client.gameMode == null ? -1 : client.gameMode.getDestroyStage())
			+ " mineTicks=" + mineTicks
			+ " attack=" + client.options.keyAttack.isDown()
			+ " up=" + client.options.keyUp.isDown()
			+ " jump=" + client.options.keyJump.isDown()
			+ " crosshair=" + cross
			+ (loot.active() ? " " + loot.diagnostic(client, player) : "")
			+ " status=" + status);
	}
}
