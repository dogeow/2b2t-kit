package dev.twob2tkit.combat;

import dev.twob2tkit.runtime.engine.BorerCombatPolicy;
import dev.twob2tkit.runtime.engine.BorerHazards;
import dev.twob2tkit.runtime.engine.BorerThreats;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.network.chat.Component;
import net.minecraft.world.damagesource.DamageSource;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.item.Items;

import java.util.Locale;
import dev.twob2tkit.AfkLogoutPolicy;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.borer.TunnelBorer;

/**
 * 一直记被打和死亡。钓鱼挂机被打中一次才下线；附近有骷髅不够。巡航时仍看陌生玩家和最低心数。
 */
public final class CombatWatch {
	private final KitConfig config;
	private float lastHealth = -1.0F;
	private boolean wasDead;

	/** 按配置构造战斗监视。 */
	public CombatWatch(KitConfig config) {
		this.config = config;
	}

	/** 跟踪掉血与死亡；钓鱼挨打可下线。 */
	public void tick(Minecraft client) {
		if (client.player == null || client.level == null) {
			wasDead = false;
			lastHealth = -1.0F;
			return;
		}
		LocalPlayer player = client.player;
		if (player.isDeadOrDying()) {
			if (!wasDead) recordDeath(client, player);
			wasDead = true;
			return;
		}
		wasDead = false;
		noteHurt(client, player);
		if (shouldGuardLogout()) maybeLogout(client, player);
	}

	/** 血量下降时记攻击者并可能武装/下线。 */
	private void noteHurt(Minecraft client, LocalPlayer player) {
		float health = player.getHealth() + player.getAbsorptionAmount();
		if (lastHealth < 0.0F) {
			lastHealth = health;
			return;
		}
		if (health < lastHealth - 0.05F) {
			String attacker = attackerName(client, player);
			boolean env = isEnvironmentalHurt(client, player);
			config.lastAttackTimeEpochMillis = System.currentTimeMillis();
			config.lastAttacker = attacker;
			config.lastAttackHealth = health;
			config.lastAttackActivity = currentActivity();
			config.save();
			CombatFileLog.append(client, String.format(Locale.ROOT,
				"hurt attacker=%s hp=%.1f->%.1f activity=%s at %.1f %.1f %.1f",
				attacker, lastHealth, health, config.lastAttackActivity, player.getX(), player.getY(), player.getZ()));
			if (client.player != null) {
				String verb = env ? "烫伤" : "被打";
				client.player.sendSystemMessage(Component.literal(
					String.format(Locale.ROOT, "[2b2t-kit] %s：%s  血 %.1f→%.1f", verb, attacker, lastHealth, health)
				).withColor(0xFFAA55));
			}
			if (AutoProtectPolicy.armOnMobHit(config.autoProtectOnHit, BorerThreats.currentHurtIsFromMob(player))) {
				MeteorCombatAssist.arm(client);
			}
			boolean fishing = KitClient.fisher() != null && KitClient.fisher().isActive();
			if (AfkLogoutPolicy.hitLogsOut(fishing) && shouldGuardLogout()
				&& BorerThreats.currentHurtIsFromMob(player)) {
				lastHealth = health;
				KitClient.safeLogout(client, "被" + attacker + "打中，钓鱼挂机下线");
				return;
			}
		}
		lastHealth = health;
	}

	/** 记下死亡点、杀手与活动。 */
	private void recordDeath(Minecraft client, LocalPlayer player) {
		String killer = killerName(client, player);
		String message;
		try {
			message = player.getCombatTracker().getDeathMessage().getString();
		} catch (RuntimeException ignored) {
			message = "已死亡";
		}
		if (message == null || message.isBlank()) message = "已死亡";
		config.hasDeathPoint = true;
		config.deathX = player.getX();
		config.deathY = player.getY();
		config.deathZ = player.getZ();
		config.deathDimension = client.level.dimension().identifier().toString();
		config.deathTimeEpochMillis = System.currentTimeMillis();
		config.deathKiller = killer;
		config.deathMessage = message;
		config.deathActivity = currentActivity();
		config.save();
		CombatFileLog.append(client, String.format(Locale.ROOT,
			"death killer=%s msg=%s activity=%s at %.1f %.1f %.1f lastHit=%s %d",
			killer, message, config.deathActivity, config.deathX, config.deathY, config.deathZ,
			config.lastAttacker, config.lastAttackTimeEpochMillis));
	}

	/** 最低心数或陌生玩家靠近则安全下线。 */
	private void maybeLogout(Minecraft client, LocalPlayer player) {
		if (config.minHealth > 0.0 && player.getHealth() <= config.minHealth) {
			KitClient.safeLogout(client, String.format(Locale.ROOT, "生命 %.1f ≤ %.1f，挂机自动下线",
				player.getHealth(), config.minHealth));
			return;
		}
		String nearby = nearbyUntrusted(client, player);
		if (nearby != null) {
			KitClient.safeLogout(client, "附近陌生玩家：" + nearby);
		}
	}

	/** 挂机自动中且非打猪人/围箱才看下线。 */
	private boolean shouldGuardLogout() {
		if (KitClient.brawler() != null && KitClient.brawler().isActive()) return false;
		if (KitClient.surround() != null && KitClient.surround().isActive()) return false;
		return KitClient.anyAfkAuto();
	}

	/** 警戒半径内第一个非信任玩家名。 */
	private String nearbyUntrusted(Minecraft client, LocalPlayer localPlayer) {
		if (config.playerRadius <= 0.0) return null;
		double radiusSquared = config.playerRadius * config.playerRadius;
		for (Player other : client.level.players()) {
			if (other == localPlayer || other.isSpectator()) continue;
			String name = other.getGameProfile().name();
			if (config.isTrusted(name)) continue;
			if (localPlayer.distanceToSqr(other) <= radiusSquared) return name;
		}
		return null;
	}

	/** 岩浆块等环境伤，不算挨打武装。 */
	private static boolean isEnvironmentalHurt(Minecraft client, LocalPlayer player) {
		DamageSource source = player.getLastDamageSource();
		if (BorerThreats.isEnvironmental(source)) return true;
		LivingEntity byMob = player.getLastHurtByMob();
		int since = byMob == null ? Integer.MAX_VALUE : player.tickCount - player.getLastHurtByMobTimestamp();
		return BorerHazards.playerOnMagma(client, player)
			&& !BorerCombatPolicy.treatAsMobHit(true, false, since);
	}

	/** 尽量还原本次伤害来源名称。 */
	private static String attackerName(Minecraft client, LocalPlayer player) {
		DamageSource source = player.getLastDamageSource();
		if (BorerThreats.isEnvironmental(source)) return BorerThreats.environmentalLabel(source);
		LivingEntity byMob = player.getLastHurtByMob();
		int since = byMob == null ? Integer.MAX_VALUE : player.tickCount - player.getLastHurtByMobTimestamp();
		if (BorerHazards.playerOnMagma(client, player)
			&& !BorerCombatPolicy.treatAsMobHit(true, false, since)) {
			return "岩浆块";
		}
		if (byMob != null && byMob.isAlive()
			&& BorerCombatPolicy.treatAsMobHit(true, false, since)) {
			return byMob.getName().getString();
		}
		Player byPlayer = player.getLastHurtByPlayer();
		if (byPlayer != null) return byPlayer.getGameProfile().name();
		if (source != null) {
			String named = livingName(source.getEntity());
			if (named != null) return named;
			Entity direct = source.getDirectEntity();
			if (direct instanceof Projectile shot) {
				named = livingName(shot.getOwner());
				if (named != null) return named;
			}
			named = livingName(direct);
			if (named != null) return named;
		}
		if (client.level != null) {
			String fromShot = nearbyProjectileOwner(client, player);
			if (fromShot != null) return fromShot;
			if (source != null && source.getDirectEntity() instanceof Projectile) {
				String archer = nearbyRangedHostile(client, player);
				if (archer != null) return archer;
			}
		}
		return "未知";
	}

	/** 死亡击杀归属名。 */
	private static String killerName(Minecraft client, LocalPlayer player) {
		LivingEntity credit = player.getKillCredit();
		if (credit instanceof Player p) return p.getGameProfile().name();
		if (credit != null) return credit.getName().getString();
		return attackerName(client, player);
	}

	/** 实体显示名；玩家用档案名。 */
	private static String livingName(Entity entity) {
		if (entity instanceof Player player) return player.getGameProfile().name();
		if (entity instanceof LivingEntity living && living.isAlive()) return living.getName().getString();
		return null;
	}

	/** 客户端往往收不到 lastHurtByMob：箭是弹射物，伤害在服务端结算。 */
	private static String nearbyProjectileOwner(Minecraft client, LocalPlayer player) {
		String best = null;
		double bestDist = 8.0 * 8.0;
		for (Entity entity : client.level.entitiesForRendering()) {
			if (!(entity instanceof Projectile shot) || entity == player) continue;
			double dist = player.distanceToSqr(entity);
			if (dist > bestDist) continue;
			String named = livingName(shot.getOwner());
			if (named == null) continue;
			best = named;
			bestDist = dist;
		}
		return best;
	}

	/** 附近持弓弩三叉戟的敌对生物。 */
	private static String nearbyRangedHostile(Minecraft client, LocalPlayer player) {
		String best = null;
		double bestDist = 32.0 * 32.0;
		for (Entity entity : client.level.entitiesForRendering()) {
			if (!(entity instanceof LivingEntity living) || !(entity instanceof Enemy) || !living.isAlive()) continue;
			if (entity == player) continue;
			if (!living.isHolding(Items.BOW) && !living.isHolding(Items.CROSSBOW) && !living.isHolding(Items.TRIDENT)) {
				continue;
			}
			double dist = player.distanceToSqr(living);
			if (dist >= bestDist) continue;
			best = living.getName().getString();
			bestDist = dist;
		}
		return best;
	}

	/** 当前自动模块活动标签。 */
	private static String currentActivity() {
		if (KitClient.fisher() != null && KitClient.fisher().isActive()) return "钓鱼";
		if (KitClient.controller() != null && KitClient.controller().isActive()) return "巡航";
		TunnelBorer borer = KitClient.borer();
		if (borer != null && borer.isActive()) return "盾构";
		if (KitClient.chopper() != null && KitClient.chopper().isActive()) return "挖树";
		if (KitClient.planter() != null && KitClient.planter().isActive()) return "种田";
		if (KitClient.feeder() != null && KitClient.feeder().isActive()) return "喂养";
		if (KitClient.brawler() != null && KitClient.brawler().isActive()) return "打猪人";
		return "空闲";
	}
}
