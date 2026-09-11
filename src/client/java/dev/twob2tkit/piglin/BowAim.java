package dev.twob2tkit.piglin;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import java.util.Optional;
import java.util.WeakHashMap;

/** Shared visible bow aim: observed target motion, discrete drag/gravity, shooter motion and moving hitboxes. */
public final class BowAim {
    private static final WeakHashMap<Entity, BowTargetMotion> MOTION = new WeakHashMap<>();
    public record Shot(Vec3 aim, String problem, double flightTicks, Vec3 velocity, Vec3 predictedCenter) {
        public Shot(Vec3 aim, String problem) { this(aim, problem, 0, Vec3.ZERO, null); }
        public boolean feasible() { return aim != null; }
        public String diagnostic() {
            return String.format(java.util.Locale.ROOT, "flight=%.2f velocity=(%.3f,%.3f,%.3f) predicted=%s",
                flightTicks, velocity.x, velocity.y, velocity.z, predictedCenter);
        }
    }
    public static Shot solve(Minecraft client, LocalPlayer player, Entity target) { return solve(client, player, target, 20); }
    public static Shot solve(Minecraft client, LocalPlayer player, Entity target, int chargeTicks) {
        if (client == null || client.level == null || player == null || target == null || !target.isAlive() || target.level() != client.level)
            return new Shot(null, "没有有效目标");
        Vec3 motion = MOTION.computeIfAbsent(target, ignored -> new BowTargetMotion())
            .observe(client.level.getGameTime(), target.position(), target.getDeltaMovement(), target.onGround());
        Vec3 eye = player.getEyePosition(), origin = eye.add(0, -.1, 0);
        Vec3 known = player.getKnownMovement();
        Vec3 inherited = new Vec3(known.x, player.onGround() ? 0 : known.y, known.z);
        double latency = 0;
        if (client.getConnection() != null) {
            var info = client.getConnection().getPlayerInfo(player.getUUID());
            if (info != null) latency = Math.max(0, Math.min(4, info.getLatency() / 50.0));
        }
        BowTrajectory.World world = new BowTrajectory.World() {
            @Override public boolean targetSpace(AABB box) {
                return client.level.hasChunkAt(BlockPos.containing(box.minX, box.minY, box.minZ))
                    && client.level.hasChunkAt(BlockPos.containing(box.maxX, box.maxY, box.maxZ))
                    && client.level.noCollision(target, box);
            }
            @Override public Optional<Vec3> obstruction(Vec3 from, Vec3 to) {
                // Water changes arrow drag; refuse such a trajectory rather than claim the dry-air solution is valid.
                var block = client.level.clip(new ClipContext(from, to, ClipContext.Block.COLLIDER, ClipContext.Fluid.ANY, player));
                Vec3 nearest = block.getType() == HitResult.Type.BLOCK ? block.getLocation() : null;
                double distance = nearest == null ? Double.POSITIVE_INFINITY : from.distanceToSqr(nearest);
                for (Entity other : client.level.getEntities(player, new AABB(from, to).inflate(.35))) {
                    if (other == target || !(other instanceof LivingEntity) || !other.isAlive() || other.isSpectator()) continue;
                    AABB body = other.getBoundingBox().inflate(.3);
                    Optional<Vec3> hit = body.contains(from) ? Optional.of(from) : body.clip(from, to);
                    if (hit.isPresent() && from.distanceToSqr(hit.get()) < distance) {
                        nearest = hit.get(); distance = from.distanceToSqr(nearest);
                    }
                }
                return Optional.ofNullable(nearest);
            }
        };
        var solution = BowTrajectory.solve(origin, inherited, target.getBoundingBox(), motion, latency,
            BowTrajectory.speedForCharge(chargeTicks), world);
        if (solution == null) return new Shot(null, "弹道受阻或无法可靠截住目标", 0, motion, null);
        return new Shot(eye.add(solution.direction().scale(4)), null, solution.flightTicks(), motion, solution.predictedCenter());
    }
    private BowAim() {}
}
