package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.Mob;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.item.Items;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.AABB;
import java.util.*;

/** Client-observable engagement, not an assumption that server Mob.getTarget is synchronised. */
final class BorerEngagement {
	private record Sample(Vec3 mob, Vec3 player) {}
	private final Map<Integer, Sample> samples = new HashMap<>();
	private final Set<Integer> approaching = new HashSet<>();
	private final Map<Integer, Long> attackers = new HashMap<>();
	private final Map<Integer, Long> aimingUntil = new HashMap<>();
	private long sampledAt = Long.MIN_VALUE;
	void clear() { samples.clear(); approaching.clear(); attackers.clear(); aimingUntil.clear(); sampledAt = Long.MIN_VALUE; }
	void update(Minecraft c) {
		var p = c.player;
		long now = c.level.getGameTime();
		if (sampledAt != Long.MIN_VALUE && now < sampledAt) clear();
		var source = p.getLastDamageSource();
		if (p.hurtTime > 0 && source != null && !BorerThreats.isEnvironmental(source) && source.getEntity() instanceof LivingEntity attacker)
			attackers.put(attacker.getId(), now + 100);
		attackers.entrySet().removeIf(e -> e.getValue() < now);
		aimingUntil.entrySet().removeIf(e -> e.getValue() < now);
		for (Projectile shot : c.level.getEntitiesOfClass(Projectile.class, p.getBoundingBox().inflate(12))) {
			if (shot.getOwner() instanceof Enemy && incoming(p.getBoundingBox(), shot.position(), shot.getDeltaMovement()))
				attackers.put(shot.getOwner().getId(), now + 60);
		}
		if (sampledAt != Long.MIN_VALUE && now - sampledAt < 5) return;
		sampledAt = now;
		Set<Integer> visibleIds = new HashSet<>();
		approaching.clear();
		for (Entity e : c.level.getEntities(p, p.getBoundingBox().inflate(40))) {
			if (!(e instanceof Enemy) || !e.isAlive()) continue;
			visibleIds.add(e.getId());
			Sample old = samples.put(e.getId(), new Sample(e.position(), p.position()));
			if (old == null) continue;
			// Enemy displacement toward the previous player position. Player motion cannot create a threat.
			if (BorerDefensePolicy.approaching(e.getX() - old.mob.x, e.getZ() - old.mob.z,
				old.player.x - old.mob.x, old.player.z - old.mob.z)) approaching.add(e.getId());
		}
		samples.keySet().retainAll(visibleIds);
	}
	boolean recentAttacker(LocalPlayer p, Entity e) {
		int age = p.tickCount - p.getLastHurtByMobTimestamp();
		return e == p.getLastHurtByMob() && age >= 0 && age <= 100
			|| attackers.getOrDefault(e.getId(), Long.MIN_VALUE) >= p.level().getGameTime();
	}
	boolean shouldReact(LocalPlayer p, Entity e) {
		if (!(e instanceof LivingEntity living) || !(e instanceof Enemy) || !e.isAlive()) return false;
		LivingEntity target = e instanceof Mob mob ? mob.getTarget() : null;
		boolean other = target != null && target != p;
		double distance = p.distanceTo(e);
		boolean swell = e instanceof Creeper creeper && BorerDefensePolicy.blastThreat(
			creeper.isIgnited() || creeper.getSwellDir() > 0 || creeper.getSwelling(1) > .15, creeper.isPowered(), distance);
		Vec3 toward = p.getEyePosition().subtract(living.getEyePosition()).normalize();
		boolean facing = living.getViewVector(1).dot(toward) > .94;
		boolean ranged = living.getMainHandItem().is(Items.BOW) || living.getMainHandItem().is(Items.CROSSBOW);
		boolean attackPose = facing && e instanceof Mob mob && mob.isAggressive()
			&& (ranged && living.isUsingItem() || !ranged && distance <= 3);
		boolean visible = p.hasLineOfSight(e);
		if (attackPose && visible && !other) aimingUntil.put(e.getId(), p.level().getGameTime() + 30);
		return BorerDefensePolicy.engaged(visible, recentAttacker(p, e), other, target == p,
			approaching.contains(e.getId()), aimingUntil.getOrDefault(e.getId(), Long.MIN_VALUE) >= p.level().getGameTime(), swell, distance, p.getY() - e.getY());
	}
	static boolean incoming(AABB player, Vec3 position, Vec3 velocity) {
		return velocity.lengthSqr() > .0025 && player.inflate(.4).clip(position, position.add(velocity.scale(10))).isPresent();
	}
}
