package dev.twob2tkit.piglin;

import dev.twob2tkit.runtime.engine.BorerFlight;
import dev.twob2tkit.runtime.engine.BorerHazards;
import dev.twob2tkit.runtime.engine.BorerItems;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Ghast;
import net.minecraft.world.entity.monster.piglin.AbstractPiglin;
import net.minecraft.world.entity.monster.piglin.Piglin;
import net.minecraft.world.entity.monster.zombie.ZombifiedPiglin;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.projectile.hurtingprojectile.LargeFireball;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.core.BlockPos;
import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.Vec3;

import java.util.HashMap;
import java.util.Locale;
import java.util.Map;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;

/**
 * 下界刷猪人经验用的自动战斗：
 * 近战砍够得着的猪人/僵尸猪人（拿弩的优先），恶魂火球自动瞄准反弹，
 * 有弓和箭时射远处的恶魂和拿弩的猪人，飞行时左右拉扯躲投射物。
 */
public final class PiglinBrawler {
	/** 远程目标全量扫描的间隔。火球检测必须每拍跑，这个不用。 */
	private static final int RANGED_SCAN_INTERVAL = 5;
	private static final int SHOT_REFRESH_TICKS = 3;
	private static final int RANGED_SKIP_TICKS = 60;
	private static final double FIREBALL_SCAN_RANGE = 28.0;

	private final KitConfig config;
	private boolean active;
	private String status = "";
	private Vec3 aim;
	private Vec3 aimPoint;
	private int aimEntityId = -1;
	private float brawlYaw;
	private float brawlPitch;
	private boolean hasBrawlLook;
	private boolean bowKeyHeld;
	/** 本模块为了射恶魂/弩猪人切到弓；false 时不抢玩家自己选的弓。 */
	private boolean moduleBowActive;
	private int strafeSign = 1;
	private int strafeTicks;
	/** 本模块当前按住的横移键：0 没按，-1 左，1 右。只用来精确松开自己按下的那个。 */
	private int strafeHeld;
	private boolean jumpHeld;
	private String hoverNote = "";
	private int rangedTargetId = -1;
	private int rangedScanCooldown;
	/** 弹道算下来打不到的目标，暂时跳过，别一直盯着一个坑里的怪。 */
	private final Map<Integer, Long> rangedSkipped = new HashMap<>();
	private BowAim.Shot shot;
	private int shotTargetId = -1;
	private int shotTicks;

	/** 按配置构造打猪人辅助。 */
	public PiglinBrawler(KitConfig config) {
		this.config = config;
	}

	/** 是否运行中。 */
	public boolean isActive() {
		return active;
	}

	/** 最近状态文案。 */
	public String status() {
		return status;
	}

	/** 热键开/关。 */
	public void toggle(Minecraft client) {
		if (active) stop(client, "手动关闭");
		else start(client);
	}

	/** 开始打猪人。 */
	public void start(Minecraft client) {
		if (client.player == null) return;
		active = true;
		status = "找目标";
		message(client, config.brawlerMeleeEnabled
			? "自动打猪人已开启：近战砍猪人/僵尸猪人，恶魂火球自动反弹，"
				+ "有弓和箭会射远处的恶魂和拿弩的猪人。人不会自己跑动。紧急停止键随时可停"
			: "自动打猪人已开启（近战交给 Meteor）：只反弹恶魂火球、拉弓射远处的恶魂和弩猪人。紧急停止键随时可停");
		if (config.brawlerDeflectFireball) {
			message(client, "提示：Meteor 的 Arrow Dodge 勾了 all-projectiles 会把你推离火球路径，反弹就永远够不着。"
				+ "想反弹就把 all-projectiles 关掉（箭照躲）；想让它躲火球就到设置里关掉本模块的「反弹恶魂火球」");
		}
	}

	/** 停止并松键。 */
	public void stop(Minecraft client, String reason) {
		if (client.player != null) restoreSword(client, client.player);
		releaseKeys(client, true);
		aim = null;
		if (!active) return;
		active = false;
		hoverNote = "";
		rangedTargetId = -1;
		rangedScanCooldown = 0;
		rangedSkipped.clear();
		shot = null;
		shotTargetId = -1;
		moduleBowActive = false;
		aimPoint = null;
		aimEntityId = -1;
		status = "已停止：" + reason;
		message(client, "自动打猪人已停止：" + reason);
	}

	/** 选目标：近战/拉弓/反弹火球/拉扯。 */
	public void tick(Minecraft client) {
		if (!active) return;
		LocalPlayer player = client.player;
		if (player == null || client.level == null || client.gameMode == null) {
			stop(client, "离开世界");
			return;
		}
		if (KitClient.controller() != null && KitClient.controller().isActive()) {
			stop(client, "巡航接管");
			return;
		}
		if (config.brawlerMinHealth > 0.0 && player.getHealth() <= config.brawlerMinHealth) {
			stop(client, String.format(Locale.ROOT, "血量只剩 %.0f，先撤了自己补血", player.getHealth()));
			overlay(client, "血量太低已停手，快补血", 0xFF5555);
			return;
		}
		if (client.screen != null) {
			releaseKeys(client, true);
			return;
		}
		aim = null;

		// 一旦开始拉弓，没拉满绝不松手，也不去近战/反弹火球，否则原版会把没充能的箭射出去。
		if (bowKeyHeld) {
			if (config.brawlerMeleeEnabled) {
				MeleeScan scan = scanMelee(client, player);
				maintainHover(client, player, scan.verticalGap());
			} else {
				holdJump(client, false);
			}
			LivingEntity ranged = pickRangedTarget(client, player, false);
			if (ranged != null) {
				handleRanged(client, player, ranged, true);
				return;
			}
			stowBow(client, player);
			if (bowKeyHeld) {
				status = "弓还在拉，切不出剑";
				overlay(client, status, 0xFFFF55);
				return;
			}
		}

		// 关掉反弹就完全不管火球，交给 Meteor 的 arrow-dodge 去躲：两件事互斥，不能都做。
		if (config.brawlerDeflectFireball) {
			LargeFireball fireball = incomingFireball(client, player);
			if (fireball != null) {
				holdJump(client, false);
				handleFireball(client, player, fireball);
				return;
			}
		}

		MeleeScan scan = scanMelee(client, player);
		if (config.brawlerMeleeEnabled) maintainHover(client, player, scan.verticalGap());
		else holdJump(client, false);

		// 近战交给 Meteor KillAura 时不抢挥手和视角，免得两边互相重置攻击充能。
		if (config.brawlerMeleeEnabled && scan.target() != null) {
			handleMelee(client, player, scan.target());
			return;
		}

		LivingEntity ranged = pickRangedTarget(client, player, false);
		if (ranged != null) {
			handleRanged(client, player, ranged, true);
			if (bowKeyHeld || !(ranged instanceof Ghast)) return;
		}

		releaseKeys(client, false);
		status = "没发现敌人";
		overlay(client, status, 0xA0A0A0);
	}

	/** 是否有要维持的瞄准。 */
	public boolean hasLook() {
		return aim != null;
	}

	/** 写回瞄准。 */
	public void reapplyLook(Minecraft client) {
		if (client.player == null || client.screen != null) return;
		if (!active && !config.ghastGuardEnabled) return;
		if (!hasBrawlLook) return;
		if (client.player.getMainHandItem().is(Items.BOW) && !bowKeyHeld) return;
		RotationAim.apply(client.player, brawlYaw, brawlPitch);
	}

	/**
	 * 没开打猪人时也处理恶魂：反弹火球，空闲时拉弓射。
	 * 不横移、不拉高，避免被推进堡垒柱子上的火。
	 * @return 这一拍占用了视角/攻击，其它自动动作应停一拍
	 */
	public boolean tickGhastGuard(Minecraft client, boolean allowBow) {
		if (active) return false;
		if (!config.ghastGuardEnabled) {
			releaseModuleKeys(client, true);
			aim = null;
			return false;
		}
		LocalPlayer player = client.player;
		if (player == null || client.level == null || client.gameMode == null) return false;
		if (client.screen != null) {
			releaseModuleKeys(client, true);
			aim = null;
			return false;
		}
		if (!player.getMainHandItem().is(Items.BOW)) {
			moduleBowActive = false;
			bowKeyHeld = false;
		} else if (!moduleBowActive) {
			// 玩家自己选的弓：不抢右键、不拉视角，否则按住右键也拉不开。
			bowKeyHeld = false;
			return false;
		}
		aim = null;
		if (bowKeyHeld) {
			holdJump(client, false);
			if (allowBow) {
				LivingEntity ghast = pickRangedTarget(client, player, true);
				if (ghast != null) {
					handleRanged(client, player, ghast, false);
					return true;
				}
			}
			stowBow(client, player);
			return bowKeyHeld;
		}
		if (config.brawlerDeflectFireball) {
			LargeFireball fireball = incomingFireball(client, player);
			if (fireball != null) {
				holdJump(client, false);
				handleFireball(client, player, fireball);
				return true;
			}
		}
		if (!allowBow) {
			releaseModuleKeys(client, false);
			return false;
		}
		LivingEntity ghast = pickRangedTarget(client, player, true);
		if (ghast != null) {
			handleRanged(client, player, ghast, false);
			return bowKeyHeld;
		}
		releaseModuleKeys(client, false);
		return false;
	}

	/** 找最近一颗朝自己飞来的恶魂火球。 */
	private LargeFireball incomingFireball(Minecraft client, LocalPlayer player) {
		AABB box = player.getBoundingBox().inflate(FIREBALL_SCAN_RANGE);
		LargeFireball best = null;
		double bestDist = Double.MAX_VALUE;
		for (LargeFireball fireball : client.level.getEntitiesOfClass(LargeFireball.class, box)) {
			if (!fireball.isAlive()) continue;
			Vec3 velocity = fireball.getDeltaMovement();
			if (velocity.lengthSqr() < 1.0E-6) continue;
			Vec3 toPlayer = player.getEyePosition().subtract(fireball.position());
			if (toPlayer.lengthSqr() < 1.0E-6) continue;
			if (velocity.normalize().dot(toPlayer.normalize()) < 0.55) continue;
			double dist = player.distanceTo(fireball);
			if (dist < bestDist) {
				bestDist = dist;
				best = fireball;
			}
		}
		return best;
	}

	/** 反弹或躲开恶魂火球。 */
	private void handleFireball(Minecraft client, LocalPlayer player, LargeFireball fireball) {
		double dist = reachDistance(player, fireball);
		stopDrawingBow(client);
		// 要反弹就不能躲：横移会把自己挪出火球路径，永远进不了反弹距离。
		releaseStrafe(client);
		// 原版是按攻击者的视线朝向把火球弹出去的，所以瞄恶魂本体而不是火球，回弹才走直线。
		// 打的是指名实体，不看准心，所以朝向和命中互不影响。
		aimAt(player, deflectAim(fireball), fireball.getId());
		if (dist <= config.brawlerFireballReach) {
			attackEntity(client, player, fireball);
			status = "反弹恶魂火球";
			overlay(client, status, 0xFFFF55);
			return;
		}
		status = String.format(Locale.ROOT, "火球来了（%.0f 格），站住等它进 %.0f 格再弹",
			dist, config.brawlerFireballReach);
		overlay(client, status, 0xFF5555);
	}

	/** 优先瞄放火球的恶魂；找不到主人就沿火球来路反推一个远点。 */
	private static Vec3 deflectAim(LargeFireball fireball) {
		if (fireball.getOwner() instanceof LivingEntity owner && owner.isAlive()) {
			return owner.getBoundingBox().getCenter();
		}
		Vec3 velocity = fireball.getDeltaMovement();
		Vec3 center = fireball.getBoundingBox().getCenter();
		if (velocity.lengthSqr() < 1.0E-6) return center;
		return center.subtract(velocity.normalize().scale(32.0));
	}

	/**
	 * 一次扫描同时取两样：够得着的近战目标，以及脚下最近那只地面怪的高度差。
	 * 高度差用来维持悬停——拿矛的猪人攻击距离比剑长，站得不够高会挨打。
	 */
	private MeleeScan scanMelee(Minecraft client, LocalPlayer player) {
		double watch = Math.max(config.brawlerMeleeReach, config.brawlerHoverHeight) + 3.0;
		AABB box = player.getBoundingBox().inflate(watch, watch + 2.0, watch);
		LivingEntity best = null;
		int bestRank = Integer.MAX_VALUE;
		double bestDist = Double.MAX_VALUE;
		double gap = Double.MAX_VALUE;
		for (Entity entity : client.level.getEntities(player, box)) {
			if (!(entity instanceof LivingEntity living) || !living.isAlive()) continue;
			int rank = targetRank(living);
			if (rank < 0) continue;
			// 恶魂在天上飞，跟悬停高度没关系。
			if (!(living instanceof Ghast) && horizontalDistance(player, living) <= watch) {
				gap = Math.min(gap, player.getY() - living.getY());
			}
			double dist = reachDistance(player, living);
			if (dist > config.brawlerMeleeReach) continue;
			if (rank < bestRank || rank == bestRank && dist < bestDist) {
				best = living;
				bestRank = rank;
				bestDist = dist;
			}
		}
		return new MeleeScan(best, gap);
	}

	/** 近战扫描结果：目标与垂直差。 */
	private record MeleeScan(LivingEntity target, double verticalGap) {
	}

	/** 与实体的水平距离。 */
	private static double horizontalDistance(LocalPlayer player, Entity entity) {
		return Math.hypot(entity.getX() - player.getX(), entity.getZ() - player.getZ());
	}

	/**
	 * 站得比地面怪高够多才安全：拿矛的猪人比拿剑的够得远，贴脸就会挨打。
	 * 只在飞行时才顶得上去；走地面时只能提醒，跳一下没用。
	 */
	private void maintainHover(Minecraft client, LocalPlayer player, double verticalGap) {
		hoverNote = "";
		if (config.brawlerHoverHeight <= 0.0 || verticalGap == Double.MAX_VALUE
			|| verticalGap >= config.brawlerHoverHeight) {
			holdJump(client, false);
			return;
		}
		if (!BorerFlight.isFlying(player)) {
			// 走地面顶不上去，只能提醒。
			holdJump(client, false);
			hoverNote = String.format(Locale.ROOT, "（只高出 %.1f 格，会挨打）", verticalGap);
			return;
		}
		holdJump(client, true);
		hoverNote = String.format(Locale.ROOT, "（正在拉高到 %.0f 格）", config.brawlerHoverHeight);
	}

	/** 和横移键一样：只按/松本模块自己控制的那一下，别抹掉玩家手按的空格。 */
	private void holdJump(Minecraft client, boolean down) {
		if (client.options == null) return;
		if (down) {
			jumpHeld = true;
			if (!client.options.keyJump.isDown()) client.options.keyJump.setDown(true);
			return;
		}
		if (!jumpHeld) return;
		jumpHeld = false;
		client.options.keyJump.setDown(false);
	}

	/** 拿弩的猪人最优先，然后蛮兵、普通猪人、僵尸猪人，凑近的恶魂也砍。 */
	private static int targetRank(LivingEntity entity) {
		if (entity instanceof Piglin piglin) return piglin.isHolding(Items.CROSSBOW) ? 0 : 2;
		if (entity instanceof AbstractPiglin) return 1;
		if (entity instanceof ZombifiedPiglin) return 3;
		if (entity instanceof Ghast) return 4;
		return -1;
	}

	/** 近战接近并挥击。 */
	private void handleMelee(Minecraft client, LocalPlayer player, LivingEntity target) {
		stopDrawingBow(client);
		releaseStrafe(client);
		BorerItems.selectWeapon(client, player);
		aimAt(player, target.getBoundingBox().getCenter(), target.getId());
		if (player.getAttackStrengthScale(0.0F) >= 0.95F) attackEntity(client, player, target);
		status = "砍 " + target.getName().getString();
		overlay(client, status, 0x55FF55);
	}

	/**
	 * 直接攻击指定实体，不走 keyAttack。
	 * 原版 startAttack() 看的是 client.hitResult，而 hitResult 是渲染帧算的，
	 * 我们刚在 tick 开头改完朝向，本拍读到的还是转头前的结果：既容易打空，
	 * 更糟的是 hitResult 落在方块上时会直接开挖背后的方块。指名实体就没这些问题。
	 */
	private static void attackEntity(Minecraft client, LocalPlayer player, Entity target) {
		client.gameMode.attack(player, target);
		player.swing(InteractionHand.MAIN_HAND);
	}

	/** 到实体碰撞箱最近点的距离，和原版判定攻击距离的口径一致。 */
	private static double reachDistance(LocalPlayer player, Entity target) {
		return Math.sqrt(target.getBoundingBox().distanceToSqr(player.getEyePosition()));
	}

	/**
	 * 只松开本模块自己按下的那一个横移键，而且只在状态真的变化时写一次。
	 * 这里跑在 Minecraft.tick 的 HEAD mixin 里，比玩家采样 KeyMapping 早；
	 * 要是每拍无条件写 false，玩家手按的 A/D 会被当拍抹掉，表现为「只有 WS 能动」。
	 */
	private void releaseStrafe(Minecraft client) {
		holdStrafe(client, 0);
	}

	/** 按住左右平移。 */
	private void holdStrafe(Minecraft client, int sign) {
		if (client.options == null) return;
		if (strafeHeld == sign) {
			// 玩家手动碰过同一个键会把它松掉，补按回来；反方向的键不管，让玩家自己控制。
			if (sign < 0 && !client.options.keyLeft.isDown()) client.options.keyLeft.setDown(true);
			else if (sign > 0 && !client.options.keyRight.isDown()) client.options.keyRight.setDown(true);
			return;
		}
		if (strafeHeld < 0) client.options.keyLeft.setDown(false);
		else if (strafeHeld > 0) client.options.keyRight.setDown(false);
		if (sign < 0) client.options.keyLeft.setDown(true);
		else if (sign > 0) client.options.keyRight.setDown(true);
		strafeHeld = sign;
	}

	/**
	 * 全量扫描要遍历几十格内的所有实体并逐个做射线检测，刷怪塔里每拍跑一次太贵。
	 * 锁定的目标每拍只做一次便宜的复核，真正的重扫最多 {@link #RANGED_SCAN_INTERVAL} 拍一次。
	 */
	private LivingEntity pickRangedTarget(Minecraft client, LocalPlayer player, boolean ghastsOnly) {
		LivingEntity locked = lockedRanged(client, player, ghastsOnly);
		if (locked != null) return locked;
		if (rangedScanCooldown > 0) {
			rangedScanCooldown--;
			return null;
		}
		rangedScanCooldown = RANGED_SCAN_INTERVAL;

		AABB box = player.getBoundingBox().inflate(config.brawlerGhastRange, 40.0, config.brawlerGhastRange);
		LivingEntity best = null;
		double bestScore = Double.MAX_VALUE;
		for (Entity entity : client.level.getEntities(player, box)) {
			if (!(entity instanceof LivingEntity living) || !living.isAlive()) continue;
			if (ghastsOnly && !(living instanceof Ghast)) continue;
			if (!inRangedRange(player, living)) continue;
			if (skipped(client, living)) continue;
			if (!player.hasLineOfSight(living)) continue;
			double score = living instanceof Ghast ? player.distanceTo(living) : player.distanceTo(living) - 8.0;
			if (score < bestScore) {
				bestScore = score;
				best = living;
			}
		}
		rangedTargetId = best == null ? -1 : best.getId();
		return best;
	}

	/** 弹道解算不便宜，每 {@link #SHOT_REFRESH_TICKS} 拍重算一次；目标换了立刻重算。 */
	private BowAim.Shot shotFor(Minecraft client, LocalPlayer player, LivingEntity target) {
		if (shot != null && shotTargetId == target.getId() && shotTicks > 0) {
			shotTicks--;
			return shot;
		}
		shot = BowAim.solve(client, player, target);
		shotTargetId = target.getId();
		shotTicks = SHOT_REFRESH_TICKS;
		return shot;
	}

	/** 这个目标打不到，先放一边去找别的，过一会儿再考虑它。 */
	private void skipRanged(Minecraft client, LivingEntity target) {
		rangedSkipped.put(target.getId(), client.level.getGameTime() + RANGED_SKIP_TICKS);
		rangedTargetId = -1;
		rangedScanCooldown = 0;
		shot = null;
		shotTargetId = -1;
	}

	/** 该实体是否被暂时跳过。 */
	private boolean skipped(Minecraft client, Entity entity) {
		Long until = rangedSkipped.get(entity.getId());
		if (until == null) return false;
		if (until > client.level.getGameTime()) return true;
		rangedSkipped.remove(entity.getId());
		return false;
	}

	/** 锁定的远程目标（可限恶魂）。 */
	private LivingEntity lockedRanged(Minecraft client, LocalPlayer player, boolean ghastsOnly) {
		if (rangedTargetId < 0) return null;
		Entity entity = client.level.getEntity(rangedTargetId);
		if (entity instanceof LivingEntity living && living.isAlive()
			&& (!ghastsOnly || living instanceof Ghast)
			&& inRangedRange(player, living) && player.hasLineOfSight(living)) {
			return living;
		}
		rangedTargetId = -1;
		return null;
	}

	/** 值得用弓的：恶魂，以及拿弩的猪人。 */
	private boolean inRangedRange(LocalPlayer player, LivingEntity entity) {
		if (entity instanceof Ghast) return player.distanceTo(entity) <= config.brawlerGhastRange;
		if (entity instanceof Piglin piglin && piglin.isHolding(Items.CROSSBOW)) {
			return player.distanceTo(entity) <= config.brawlerCrossbowRange;
		}
		return false;
	}

	/** 拉弓瞄准并射击。 */
	private void handleRanged(Minecraft client, LocalPlayer player, LivingEntity target, boolean dodge) {
		if (dodge) strafeDodge(client, player);
		else releaseStrafe(client);
		boolean ghast = target instanceof Ghast;
		Vec3 center = target.getBoundingBox().getCenter();
		double dist = player.getEyePosition().distanceTo(center);
		if (!hasBowAmmo(player)) {
			stowBow(client, player);
			if (ghast) {
				clearAim();
				status = "没箭，没法射 " + target.getName().getString();
			} else if (active && config.brawlerMeleeEnabled) {
				aimAt(player, center, target.getId());
				status = "没箭，盯着 " + target.getName().getString() + "，等它靠近再砍";
			} else {
				status = "没箭，没法射 " + target.getName().getString();
			}
			overlay(client, status, 0xFFFF55);
			return;
		}
		if (!selectBow(client, player)) {
			if (bowKeyHeld) holdBow(client);
			else stopDrawingBow(client, false);
			if (ghast) {
				clearAim();
				status = "没弓，没法射 " + target.getName().getString();
			} else if (active && config.brawlerMeleeEnabled) {
				aimAt(player, center, target.getId());
				status = "没弓，盯着 " + target.getName().getString() + "，等它靠近再砍";
			} else {
				status = "没弓，没法射 " + target.getName().getString();
			}
			overlay(client, status, 0xFFFF55);
			return;
		}
		BowAim.Shot shot = shotFor(client, player, target);
		if (!shot.feasible()) {
			if (ghast) {
				if (bowKeyHeld) stowBow(client, player);
				else skipRanged(client, target);
				clearAim();
				status = target.getName().getString() + " " + shot.problem() + "，先不瞄";
			} else if (bowKeyHeld) {
				holdBow(client);
				aimAt(player, center, target.getId());
				status = target.getName().getString() + " " + shot.problem() + "，继续拉满不放空箭";
			} else {
				skipRanged(client, target);
				status = target.getName().getString() + " " + shot.problem() + "，不放空箭";
			}
			overlay(client, status, 0xFFFF55);
			return;
		}
		holdBow(client);
		if (bowKeyHeld) {
			aimAt(player, shot.aim(), target.getId());
		}
		if (bowFullyCharged(player)) {
			bowKeyHeld = false;
			client.options.keyUse.setDown(false);
			clearAim();
			status = String.format(Locale.ROOT, "放箭 %s（%.0f 格）", target.getName().getString(), dist);
		} else {
			status = String.format(Locale.ROOT, "拉弓瞄 %s（%.0f 格）", target.getName().getString(), dist);
		}
		overlay(client, status, 0x55FFFF);
	}

	/** 只在飞行时左右拉扯，走地面乱动容易掉岩浆。开了 Meteor arrow-dodge 就该关掉这个，别两边一起推。 */
	private void strafeDodge(Minecraft client, LocalPlayer player) {
		if (!config.brawlerStrafeDodge || !BorerFlight.isFlying(player)) {
			releaseStrafe(client);
			return;
		}
		strafeTicks++;
		if (strafeTicks % 36 == 0) strafeSign = -strafeSign;
		if (unsafeStrafe(client, player, strafeSign)) {
			strafeSign = -strafeSign;
			if (unsafeStrafe(client, player, strafeSign)) {
				releaseStrafe(client);
				return;
			}
		}
		holdStrafe(client, strafeSign);
	}

	/** 横移方向上有火、岩浆或实心柱，就别往那边飞。 */
	private static boolean unsafeStrafe(Minecraft client, LocalPlayer player, int sign) {
		if (client.level == null || sign == 0) return false;
		float yaw = player.getYRot() + (sign < 0 ? -90.0F : 90.0F);
		double rad = Math.toRadians(yaw);
		double x = player.getX() - Math.sin(rad) * 1.4;
		double z = player.getZ() + Math.cos(rad) * 1.4;
		BlockPos feet = BlockPos.containing(x, player.getY(), z);
		for (int dy = 0; dy <= 2; dy++) {
			if (hazardBlock(client, feet.above(dy))) return true;
		}
		return hazardBlock(client, feet.below());
	}

	/** 脚下/目标是否危险方块。 */
	private static boolean hazardBlock(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (state.is(Blocks.FIRE) || state.is(Blocks.SOUL_FIRE)
			|| state.is(Blocks.CAMPFIRE) || state.is(Blocks.SOUL_CAMPFIRE)) {
			return true;
		}
		return BorerHazards.isLavaFluid(client, pos) || BorerHazards.isMagma(client, pos);
	}

	/** 是否有箭可射。 */
	private static boolean hasBowAmmo(LocalPlayer player) {
		if (player == null) return false;
		if (player.getAbilities().instabuild) return true;
		ItemStack bow = player.getMainHandItem().is(Items.BOW) ? player.getMainHandItem() : ItemStack.EMPTY;
		if (bow.isEmpty()) {
			Inventory inventory = player.getInventory();
			for (int slot = 0; slot < 36; slot++) {
				if (!inventory.getItem(slot).is(Items.BOW)) continue;
				bow = inventory.getItem(slot);
				break;
			}
		}
		if (bow.isEmpty()) return false;
		return !player.getProjectile(bow).isEmpty();
	}

	/** 切弓并检查箭。 */
	private boolean selectBow(Minecraft client, LocalPlayer player) {
		if (player.getMainHandItem().is(Items.BOW)) return true;
		// 正在用别的东西（吃、喝、举盾）时不抢槽位。看玩家的真实状态，不看自己维护的布尔量，
		// 否则那个布尔量一旦残留成 true，就再也换不出弓了。
		if (player.isUsingItem()) return false;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!inventory.getItem(slot).is(Items.BOW)) continue;
			inventory.setSelectedSlot(slot);
			moduleBowActive = true;
			return true;
		}
		int dest = weaponSwapSlot(inventory);
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(Items.BOW)) continue;
			inventory.setSelectedSlot(dest);
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, dest, ContainerInput.SWAP, player);
			moduleBowActive = true;
			return true;
		}
		return false;
	}

	/** 从背包换弓出来时避开镐/铲，优先空格。 */
	private static int weaponSwapSlot(Inventory inventory) {
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).isEmpty()) return slot;
		}
		for (int slot = 8; slot >= 0; slot--) {
			if (!BorerItems.isMiningTool(inventory.getItem(slot))) return slot;
		}
		return 8;
	}

	/** 松键。 */
	private void releaseKeys(Minecraft client, boolean force) {
		releaseModuleKeys(client, force);
	}

	/** 只松本模块按下的键；玩家自己拉弓时不要动 keyUse。 */
	private void releaseModuleKeys(Minecraft client, boolean force) {
		releaseStrafe(client);
		holdJump(client, false);
		if (moduleBowActive || bowKeyHeld || force) {
			stopDrawingBow(client, force);
		}
	}

	/** 握住弓。 */
	private void holdBow(Minecraft client) {
		if (client.options == null) return;
		moduleBowActive = true;
		bowKeyHeld = true;
		client.options.keyUse.setDown(true);
	}

	/** 恶魂没了：先切剑取消拉弓，不要松右键把没瞄准的箭射出去。 */
	private void stowBow(Minecraft client, LocalPlayer player) {
		restoreSword(client, player);
		boolean stillDrawing = player != null
			&& player.getMainHandItem().is(Items.BOW)
			&& player.isUsingItem();
		if (stillDrawing) {
			holdBow(client);
			return;
		}
		bowKeyHeld = false;
		if (client.options != null) client.options.keyUse.setDown(false);
	}

	/** 射完换回剑。 */
	private void restoreSword(Minecraft client, LocalPlayer player) {
		if (player == null || !moduleBowActive) return;
		moduleBowActive = false;
		if (!player.getMainHandItem().is(Items.BOW)) return;
		BorerItems.selectWeapon(client, player);
	}

	/** 满弓所需 tick。 */
	private int bowChargeTicks() {
		return Math.max(5, config.brawlerBowChargeTicks);
	}

	/** 弓是否已拉满。 */
	private boolean bowFullyCharged(LocalPlayer player) {
		return player != null && player.isUsingItem() && player.getTicksUsingItem() >= bowChargeTicks();
	}

	/**
	 * 没拉满时松右键，原版 handleKeybinds 会立刻 releaseUsingItem，射出没充能的箭。
	 * 模块停止 / 开界面才强制松手；其余情况继续按住，等 handleRanged 在拉满且弹道可行时再放。
	 */
	private void stopDrawingBow(Minecraft client) {
		stopDrawingBow(client, false);
	}

	/** 停止拉弓；可强制松手。 */
	private void stopDrawingBow(Minecraft client, boolean force) {
		if (!force && bowKeyHeld) {
			holdBow(client);
			return;
		}
		if (!moduleBowActive && !bowKeyHeld) return;
		bowKeyHeld = false;
		moduleBowActive = false;
		if (client.options != null) client.options.keyUse.setDown(false);
	}

	/** 悬停提醒挂在状态尾巴上，否则会被后面的攻击状态覆盖掉。 */
	private void overlay(Minecraft client, String text, int color) {
		client.gui.setOverlayMessage(Component.literal((active ? "[打猪人] " : "[恶魂防护] ") + text + hoverNote).withColor(color), false);
	}

	/** 发系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[打猪人] " + text));
	}

	/** 清瞄准状态。 */
	private void clearAim() {
		aim = null;
		aimPoint = null;
		aimEntityId = -1;
		hasBrawlLook = false;
	}

	/** 瞄准点做低通滤波，再限制每 tick 转角，避免恶魂/猪灵乱晃。 */
	private void aimAt(LocalPlayer player, Vec3 raw, int entityId) {
		if (entityId >= 0 && entityId != aimEntityId) {
			aimPoint = null;
			aimEntityId = entityId;
		}
		if (aimPoint == null || raw.distanceToSqr(aimPoint) > 64.0 * 64.0) {
			aimPoint = raw;
		} else {
			double blend = 0.2;
			aimPoint = new Vec3(
				aimPoint.x + (raw.x - aimPoint.x) * blend,
				aimPoint.y + (raw.y - aimPoint.y) * blend,
				aimPoint.z + (raw.z - aimPoint.z) * blend
			);
		}
		aim = aimPoint;
		smoothLookAt(player, aimPoint);
	}

	/** 平滑转向目标点。 */
	private void smoothLookAt(LocalPlayer player, Vec3 target) {
		RotationAim.Look want = RotationAim.lookAt(player, target);
		if (!hasBrawlLook) {
			brawlYaw = player.getYRot();
			brawlPitch = player.getXRot();
			hasBrawlLook = true;
		}
		float maxStep = (float)Math.max(2.0, config.brawlerLookDegreesPerTick);
		brawlYaw = RotationAim.step(brawlYaw, want.yaw(), maxStep);
		brawlPitch = RotationAim.step(brawlPitch, want.pitch(), maxStep);
		RotationAim.apply(player, brawlYaw, brawlPitch);
	}
}
