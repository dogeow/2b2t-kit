package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.util.Mth;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;

import java.util.Locale;
import java.util.function.Predicate;

/** 挖矿瞄准与距离：按方块最近面/命中点判断，而不是方块中心。 */
public final class BorerAim {
	/**
	 * 故意比原版 4.5 再短一截。最近面 4.4 时原版准星经常打到邻居，破坏进度一直是 -1。
	 * 3.9 格内再挥镐；更远的先走近。
	 */
	public static final double REACH_MARGIN = 0.60;

	private BorerAim() {
	}

	/** 本次实际用来挥镐的距离上限（原版属性距离，副手盾牌不会缩短它）。 */
	public static double breakReach(LocalPlayer player) {
		return Math.max(1.25, player.blockInteractionRange() - REACH_MARGIN);
	}

	/** 眼睛到方块碰撞箱最近一点的距离平方。 */
	public static double nearestDistanceSqr(Vec3 eye, BlockPos pos) {
		Vec3 nearest = new Vec3(
			Mth.clamp(eye.x, pos.getX(), pos.getX() + 1.0),
			Mth.clamp(eye.y, pos.getY(), pos.getY() + 1.0),
			Mth.clamp(eye.z, pos.getZ(), pos.getZ() + 1.0)
		);
		return eye.distanceToSqr(nearest);
	}

	/** 方块最近表面是否在可挖距离内。 */
	public static boolean inReach(LocalPlayer player, BlockPos pos) {
		double reach = breakReach(player);
		return nearestDistanceSqr(player.getEyePosition(), pos) <= reach * reach;
	}

	/**
	 * 这一次射线是否够得着：方块最近面在圈内即可。
	 * 命中点可能落在远角，比最近面远一截，不能单用命中点把整块判飞。
	 */
	public static boolean hitInReach(LocalPlayer player, BlockHitResult hit) {
		if (hit == null || hit.getType() != HitResult.Type.BLOCK) return false;
		return inReach(player, hit.getBlockPos());
	}

	/** 玩家碰撞箱是否贴着该方块（贴脸也能挖）。 */
	public static boolean touches(LocalPlayer player, BlockPos pos) {
		return player.getBoundingBox().inflate(0.18).intersects(new AABB(pos));
	}

	/** 轮廓裁剪：从 from 看到 to 时打到的第一个方块。 */
	public static BlockHitResult clipOutline(Minecraft client, LocalPlayer player, Vec3 from, Vec3 to) {
		if (client.level == null) return null;
		BlockHitResult hit = client.level.clip(new ClipContext(
			from, to, ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, player
		));
		return hit.getType() == HitResult.Type.BLOCK ? hit : null;
	}

	/**
	 * 沿命中面法线收进方块内部。朝几何中心收会偏到邻居。
	 * 挖矿优先用 {@link #lookAlongRay}，避免横向一夹就把准星甩到旁边那块。
	 */
	public static Vec3 lookPoint(BlockHitResult hit) {
		return lookPoint(hit, 0.18);
	}

	/** 从命中结果取瞄准点，按 inset 略往面内收。 */
	private static Vec3 lookPoint(BlockHitResult hit, double inset) {
		if (hit == null) return Vec3.ZERO;
		BlockPos pos = hit.getBlockPos();
		Direction face = hit.getDirection();
		Vec3 loc = hit.getLocation();
		Vec3 inward = loc.subtract(face.getStepX() * inset, face.getStepY() * inset, face.getStepZ() * inset);
		return new Vec3(
			Mth.clamp(inward.x, pos.getX() + 0.12, pos.getX() + 0.88),
			Mth.clamp(inward.y, pos.getY() + 0.12, pos.getY() + 0.88),
			Mth.clamp(inward.z, pos.getZ() + 0.12, pos.getZ() + 0.88)
		);
	}

	/** 沿「眼睛 → 命中点」再往里走一点，不横向挪，准星还在原来那条射线上。 */
	public static Vec3 lookAlongRay(Vec3 eye, BlockHitResult hit) {
		if (hit == null) return Vec3.ZERO;
		Vec3 loc = hit.getLocation();
		Vec3 dir = loc.subtract(eye);
		double len = dir.length();
		if (len < 1.0E-6) return lookPoint(hit, 0.12);
		return loc.add(dir.scale(0.22 / len));
	}

	/** 沿「眼睛 → 瞄准点」按完整方块交互距离裁剪，和准星 pick 同一条射线。 */
	public static BlockHitResult clipToward(Minecraft client, LocalPlayer player, Vec3 lookPoint) {
		Vec3 eye = player.getEyePosition();
		Vec3 delta = lookPoint.subtract(eye);
		double len = delta.length();
		if (len < 1.0E-6) return null;
		Vec3 end = eye.add(delta.scale(Math.max(player.blockInteractionRange(), len) / len));
		return clipOutline(client, player, eye, end);
	}

	/** 玩家此刻十字准星的真实射线；只有它能授权点击或按住攻击。 */
	public static BlockHitResult clipView(Minecraft client, LocalPlayer player) {
		Vec3 eye = player.getEyePosition();
		Vec3 end = eye.add(player.getViewVector(1.0F).scale(player.blockInteractionRange()));
		return clipOutline(client, player, eye, end);
	}

	/** 转到这个点之后，准星第一条轮廓射线打到的就是 expected。 */
	public static boolean aimHits(Minecraft client, LocalPlayer player, Vec3 lookPoint, BlockPos expected) {
		return verifiedHit(client, player, lookPoint, expected) != null;
	}

	/** 只返回重新裁剪得到的真实命中；不能用调用方构造的假命中授权挖掘。 */
	public static BlockHitResult verifiedHit(
		Minecraft client,
		LocalPlayer player,
		Vec3 lookPoint,
		BlockPos expected
	) {
		BlockHitResult hit = clipToward(client, player, lookPoint);
		if (hit == null || !hit.getBlockPos().equals(expected) || !hitInReach(player, hit)) return null;
		return hit;
	}

	/** 过滤不可用命中，返回仍可用于挖掘/放置的命中。 */
	private static BlockHitResult usableHit(Minecraft client, LocalPlayer player, BlockHitResult hit) {
		if (hit == null || hit.getType() != HitResult.Type.BLOCK) return null;
		if (!hitInReach(player, hit)) return null;
		BlockPos pos = hit.getBlockPos();
		Vec3[] looks = {
			lookAlongRay(player.getEyePosition(), hit),
			lookPoint(hit, 0.12),
			lookPoint(hit, 0.04)
		};
		for (Vec3 look : looks) {
			BlockHitResult verified = verifiedHit(client, player, look, pos);
			if (verified != null) return verified;
		}
		return null;
	}

	/** 能看见并够得着该方块时，返回可用来挥镐的命中。 */
	public static BlockHitResult visibleHit(
		Minecraft client,
		LocalPlayer player,
		BlockPos pos,
		Predicate<BlockPos> mineable
	) {
		Vec3 eye = player.getEyePosition();
		for (Vec3 sample : aimPoints(pos)) {
			BlockHitResult hit = usableHit(client, player, clipOutline(client, player, eye, sample));
			if (hit != null && hit.getBlockPos().equals(pos)) return hit;
		}
		if (touches(player, pos) && mineable.test(pos)) {
			Vec3 center = Vec3.atCenterOf(pos);
			Direction face = Direction.getApproximateNearest(eye.x - center.x, eye.y - center.y, eye.z - center.z);
			BlockHitResult contact = usableHit(client, player, new BlockHitResult(center, face, pos, true));
			if (contact != null) return contact;
		}
		return null;
	}

	/** 朝目标连线上，第一个可挖且「准星转过去真的打到它」的方块。 */
	public static BlockHitResult firstMineable(
		Minecraft client,
		LocalPlayer player,
		BlockPos target,
		Predicate<BlockPos> mineable
	) {
		if (client.level == null) return null;
		Vec3 eye = player.getEyePosition();
		BlockHitResult along = clipOutline(client, player, eye, Vec3.atCenterOf(target));
		if (along != null && mineable.test(along.getBlockPos()) && hitInReach(player, along)) {
			BlockHitResult usable = usableHit(client, player, along);
			return usable != null ? usable : along;
		}
		for (Vec3 sample : aimPoints(target)) {
			BlockHitResult raw = clipOutline(client, player, eye, sample);
			if (raw == null || !mineable.test(raw.getBlockPos()) || !hitInReach(player, raw)) continue;
			BlockHitResult usable = usableHit(client, player, raw);
			return usable != null ? usable : raw;
		}
		return null;
	}

	/**
	 * 挖矿打的那一面：方块在身旁就取东西南北，只有头顶/脚下方块才上下。
	 * 避免人略高于方块时去瞄顶面，破坏进度一直是 0。
	 */
	public static Direction mineFace(Vec3 eye, BlockPos pos) {
		double dx = eye.x - (pos.getX() + 0.5);
		double dy = eye.y - (pos.getY() + 0.5);
		double dz = eye.z - (pos.getZ() + 0.5);
		double ax = Math.abs(dx);
		double ay = Math.abs(dy);
		double az = Math.abs(dz);
		if (Math.max(ax, az) >= 0.25 && Math.max(ax, az) >= ay * 0.5) {
			if (ax >= az) return dx >= 0 ? Direction.EAST : Direction.WEST;
			return dz >= 0 ? Direction.SOUTH : Direction.NORTH;
		}
		if (ay >= ax && ay >= az) return dy >= 0 ? Direction.UP : Direction.DOWN;
		if (ax >= az) return dx >= 0 ? Direction.EAST : Direction.WEST;
		return dz >= 0 ? Direction.SOUTH : Direction.NORTH;
	}

	/** 轴向瞄准：眼睛看向方块中心在轴向上的落点。 */
	public static Vec3 axisLookPoint(Vec3 eye, BlockPos pos) {
		Direction face = mineFace(eye, pos);
		double inset = 0.18;
		return new Vec3(
			pos.getX() + 0.5 + face.getStepX() * (0.5 - inset),
			pos.getY() + 0.5 + face.getStepY() * (0.5 - inset),
			pos.getZ() + 0.5 + face.getStepZ() * (0.5 - inset)
		);
	}

	/** 水平方向对应的 yaw 角。 */
	public static float yawOf(Direction dir) {
		return switch (dir) {
			case SOUTH -> 0.0F;
			case WEST -> 90.0F;
			case NORTH -> 180.0F;
			case EAST -> -90.0F;
			default -> 0.0F;
		};
	}

	/** 区域挖等需要斜向命中的场合：直接朝方块中心瞄准。 */
	public static void lookAtBlockCenter(LocalPlayer player, BlockPos pos) {
		RotationAim.apply(player, RotationAim.lookAt(player, Vec3.atCenterOf(pos)));
	}

	/** 偏航锁在东西南北，俯仰只在这一条轴上算；不斜着瞄角落。 */
	public static void lookAxis(LocalPlayer player, BlockPos pos) {
		Vec3 eye = player.getEyePosition();
		Direction face = mineFace(eye, pos);
		Direction look = face.getOpposite();
		if (look.getAxis().isVertical()) {
			RotationAim.apply(player, player.getYRot(), look == Direction.UP ? -90.0F : 90.0F);
		} else {
			Vec3 point = axisLookPoint(eye, pos);
			double dy = point.y - eye.y;
			double horiz = Math.hypot(point.x - eye.x, point.z - eye.z);
			float pitch = (float) Math.toDegrees(-Math.atan2(dy, Math.max(0.001, horiz)));
			RotationAim.apply(player, yawOf(look), pitch);
		}
	}

	/** 叠加文字：最近面距离 / 本次可挖距离。 */
	public static String reachInfo(LocalPlayer player, BlockPos pos) {
		double distance = Math.sqrt(nearestDistanceSqr(player.getEyePosition(), pos));
		return String.format(Locale.ROOT, "（距离 %.1f / 可挖 %.1f）", distance, breakReach(player));
	}

	/** 方块中心、六个面内侧和八个角内侧。贴表面的点准星会擦到邻居。 */
	static Vec3[] aimPoints(BlockPos pos) {
		Vec3 center = Vec3.atCenterOf(pos);
		return new Vec3[] {
			center,
			center.add(0.28, 0.0, 0.0), center.add(-0.28, 0.0, 0.0),
			center.add(0.0, 0.28, 0.0), center.add(0.0, -0.28, 0.0),
			center.add(0.0, 0.0, 0.28), center.add(0.0, 0.0, -0.28),
			center.add(0.28, 0.28, 0.28), center.add(0.28, 0.28, -0.28),
			center.add(0.28, -0.28, 0.28), center.add(0.28, -0.28, -0.28),
			center.add(-0.28, 0.28, 0.28), center.add(-0.28, 0.28, -0.28),
			center.add(-0.28, -0.28, 0.28), center.add(-0.28, -0.28, -0.28)
		};
	}
}
