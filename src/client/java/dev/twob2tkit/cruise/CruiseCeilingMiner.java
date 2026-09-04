package dev.twob2tkit.cruise;

import com.mojang.blaze3d.platform.InputConstants;
import dev.twob2tkit.runtime.api.RotationAim;
import dev.twob2tkit.runtime.engine.BorerFlight;
import dev.twob2tkit.runtime.engine.BorerHazards;
import dev.twob2tkit.runtime.engine.BorerItems;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.util.Mth;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.item.FallingBlockEntity;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.FallingBlock;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import net.minecraft.world.phys.Vec3;
import net.minecraft.world.phys.shapes.VoxelShape;

import java.util.HashSet;
import java.util.Set;
import dev.twob2tkit.KitConfig;

/** 巡航升空时挖掉头上方块：垫脚站着挖、躲开下落沙砾、挖到岩浆先封再绕。 */
public final class CruiseCeilingMiner {
	private static final int RETRY_TICKS = 40;
	private static final int STALL_TICKS = 200;
	private static final int SCAFFOLD_EVERY = 5;
	private static final int DODGE_TICKS = 24;
	private static final int FLY_TOGGLE_COOLDOWN = 8;

	private final KitConfig config;
	private BlockPos target;
	private int mineTicks;
	private int lastDestroyStage = -1;
	private int retryCount;
	private String status = "";
	private String blockLabel = "";
	private final Set<BlockPos> skipped = new HashSet<>();
	private BlockPos lastScaffold;
	private boolean landing;
	private int dodgeTicks;
	private int dodgeSign = 1;
	private int flyToggleCooldown;
	private Boolean lastWantFly;
	private boolean haveMineLook;
	private float mineYaw;
	private float minePitch = -72.0F;
	private boolean placingLook;

	/** 按配置构造升空挖顶。 */
	public CruiseCeilingMiner(KitConfig config) {
		this.config = config;
	}

	/** 当前是否正在处理头顶挡路。 */
	public boolean isMining() {
		return target != null || landing || dodgeTicks > 0;
	}

	/** 给巡航 HUD 看的短状态。 */
	public String status() {
		return status;
	}

	/** 正在挖的方块中文名。 */
	public String blockLabel() {
		return blockLabel;
	}

	/** 松开挖掘并清掉垫脚、绕开状态。 */
	public void release(Minecraft client) {
		target = null;
		mineTicks = 0;
		lastDestroyStage = -1;
		retryCount = 0;
		status = "";
		blockLabel = "";
		landing = false;
		dodgeTicks = 0;
		haveMineLook = false;
		placingLook = false;
		if (client.options != null) {
			client.options.keyAttack.setDown(false);
			client.options.keyJump.setDown(false);
		}
		if (client.gameMode != null) client.gameMode.stopDestroyBlock();
	}

	/** 每 tick：躲沙砾、封岩浆、每 5 格垫脚，再挖头顶。 */
	public boolean tick(Minecraft client, LocalPlayer player, double cruiseY) {
		if (client.level == null || client.gameMode == null) {
			release(client);
			return false;
		}
		if (flyToggleCooldown > 0) flyToggleCooldown--;

		if (fallingHazard(client, player)) {
			ensureFlying(client, player, true);
			client.options.keyAttack.setDown(false);
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			client.options.keyUp.setDown(false);
			if (client.gameMode != null) client.gameMode.stopDestroyBlock();
			status = "沙子/沙砾下落，已开飞行躲开";
			return true;
		}

		BlockPos lava = nearbyLava(client, player);
		if (lava != null) {
			if (sealLava(client, player, lava)) {
				startDodge(player);
				status = "挖到岩浆已封堵 " + format(lava) + "，改水平绕开再上去";
			} else {
				skipped.add(lava.immutable());
				startDodge(player);
				status = "头顶附近有岩浆 " + format(lava) + "，封堵失败，先水平离开";
			}
			return true;
		}

		if (dodgeTicks > 0) {
			dodgeTicks--;
			ensureFlying(client, player, true);
			client.options.keyAttack.setDown(false);
			client.options.keyUp.setDown(true);
			client.options.keyJump.setDown(true);
			client.options.keyShift.setDown(false);
			status = "水平绕开后继续升空";
			if (dodgeTicks == 0 && !ascentBlocked(client, player)) {
				release(client);
				return false;
			}
			return true;
		}

		if (!ascentBlocked(client, player) && !landing) {
			skipped.clear();
			releaseMineOnly(client);
			haveMineLook = false;
			return false;
		}

		if (Boolean.TRUE.equals(BorerFlight.meteorFlightActive())) {
			landing = false;
		} else if (needScaffold(player) && placeFoothold(client, player)) {
			landing = true;
			holdMiningLook(player);
			status = "已垫脚，落到方块上再挖更快";
			return true;
		}

		if (landing) {
			if (Boolean.TRUE.equals(BorerFlight.meteorFlightActive())) {
				landing = false;
			} else {
				holdMiningLook(player);
				if (player.onGround()) {
					landing = false;
				} else {
					ensureFlying(client, player, false);
					client.options.keyAttack.setDown(false);
					client.options.keyJump.setDown(false);
					client.options.keyShift.setDown(true);
					client.options.keyUp.setDown(false);
					status = "落到垫脚方块上再挖";
					return true;
				}
			}
		}

		if (target != null && !shouldMine(client, target)) {
			releaseMineOnly(client);
		}
		if (target != null && !inReach(player, target)) {
			releaseMineOnly(client);
		}
		if (target == null) {
			target = findCeilingAlongLook(client, player, cruiseY);
			mineTicks = 0;
			lastDestroyStage = -1;
			retryCount = 0;
		}
		if (target == null) {
			status = blockedUnbreakable(client, player)
				? "头顶挡路但挖不掉"
				: "头顶挡住，正在寻找可挖方块";
			return false;
		}

		BlockPos openedLava = BorerHazards.lavaOpenedByMining(client, target);
		if (openedLava != null) {
			if (sealLava(client, player, openedLava)) {
				startDodge(player);
				status = "继续挖会出岩浆，已封堵并水平绕开";
				target = null;
				return true;
			}
			skipped.add(target.immutable());
			target = null;
			startDodge(player);
			status = "前方挖开会出岩浆，改水平方向";
			return true;
		}

		BlockHitResult hit = clipMiningLook(client, player);
		if (hit == null || !hit.getBlockPos().equals(target)) {
			hit = visibleHit(client, player, target);
		}
		if (hit == null) {
			releaseMineOnly(client);
			return false;
		}

		if (isFallingType(client, target) || sandStackedAbove(client, target)) {
			ensureFlying(client, player, true);
		}

		boolean fresh = mineTicks == 0;
		int stage = client.gameMode.getDestroyStage();
		if (stage > lastDestroyStage) {
			lastDestroyStage = stage;
			mineTicks = 0;
			retryCount = 0;
		} else {
			mineTicks++;
		}
		if (mineTicks >= STALL_TICKS) {
			blockLabel = label(client, target);
			status = "头顶 " + blockLabel + " 挖不动，已跳过";
			skipped.add(target.immutable());
			releaseMineOnly(client);
			return false;
		}

		holdMiningLook(player);
		client.hitResult = hit;
		client.crosshairPickEntity = null;
		if (fresh || mineTicks > 0 && mineTicks % RETRY_TICKS == 0) {
			KeyMapping.click(InputConstants.getKey(client.options.keyAttack.saveString()));
			if (!fresh) retryCount++;
		}
		client.options.keyAttack.setDown(true);
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(player.onGround());
		blockLabel = label(client, target);
		status = (player.onGround() ? "站着挖头顶 " : "飞行挖头顶 ") + blockLabel + " " + format(target);
		try {
			Gizmos.cuboid(target, GizmoStyle.strokeAndFill(0xFF00FFFF, 2.5F, 0x3300FFFF));
		} catch (IllegalStateException ignored) {
		}
		return true;
	}

	/** 挖头顶时保持前上方准星，避免每挖一格就甩头。 */
	public void reapplyLook(LocalPlayer player) {
		if (placingLook) return;
		holdMiningLook(player);
	}

	/** 只松开镐，保留垫脚记录。 */
	private void releaseMineOnly(Minecraft client) {
		target = null;
		mineTicks = 0;
		lastDestroyStage = -1;
		retryCount = 0;
		if (client.options != null) client.options.keyAttack.setDown(false);
		if (client.gameMode != null) client.gameMode.stopDestroyBlock();
	}

	/** 离上一块垫脚是否已走过约 5 格，或还在空中没有落脚点。 */
	private boolean needScaffold(LocalPlayer player) {
		if (player.onGround()) {
			BlockPos below = player.blockPosition().below();
			if (lastScaffold == null) lastScaffold = below.immutable();
			double dx = player.getX() - (lastScaffold.getX() + 0.5);
			double dz = player.getZ() - (lastScaffold.getZ() + 0.5);
			return Math.hypot(dx, dz) >= SCAFFOLD_EVERY;
		}
		if (lastScaffold == null) return true;
		double dx = player.getX() - (lastScaffold.getX() + 0.5);
		double dz = player.getZ() - (lastScaffold.getZ() + 0.5);
		return Math.hypot(dx, dz) >= SCAFFOLD_EVERY;
	}

	/** 在脚下或脚下一格放一块站立用的方块。 */
	private boolean placeFoothold(Minecraft client, LocalPlayer player) {
		BlockPos dest = player.blockPosition().below();
		if (!isReplaceable(client, dest)) dest = player.blockPosition();
		if (!isReplaceable(client, dest)) return false;
		if (player.getBoundingBox().intersects(new AABB(dest)) && dest.getY() >= Mth.floor(player.getY())) {
			dest = player.blockPosition().below();
			if (!isReplaceable(client, dest)) return false;
		}
		ItemChoice choice = selectSeal(client, player);
		if (choice == null) {
			status = "没有方块可垫脚，只能空中挖";
			return false;
		}
		if (!placeAt(client, player, dest, choice)) return false;
		lastScaffold = dest.immutable();
		landing = true;
		return true;
	}

	/** 头顶或身边是否有岩浆需要立刻处理。 */
	private BlockPos nearbyLava(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		for (int dy = 0; dy <= 3; dy++) {
			for (int dx = -1; dx <= 1; dx++) {
				for (int dz = -1; dz <= 1; dz++) {
					BlockPos pos = feet.offset(dx, dy, dz);
					if (BorerHazards.isLavaFluid(client, pos)) return pos.immutable();
				}
			}
		}
		return null;
	}

	/** 用背包方块堵住岩浆格。 */
	private boolean sealLava(Minecraft client, LocalPlayer player, BlockPos lava) {
		ItemChoice choice = selectSeal(client, player);
		if (choice == null) return false;
		return placeAt(client, player, lava, choice);
	}

	/** 开始向侧面水平走开，避开岩浆柱。 */
	private void startDodge(LocalPlayer player) {
		dodgeSign = -dodgeSign;
		float yaw = player.getYRot() + dodgeSign * 90.0F;
		player.setYRot(yaw);
		player.setXRot(0.0F);
		player.setYHeadRot(yaw);
		dodgeTicks = DODGE_TICKS;
		target = null;
		landing = false;
	}

	/** 沙子、沙砾或下落实体是否会砸到玩家。 */
	private boolean fallingHazard(Minecraft client, LocalPlayer player) {
		AABB search = player.getBoundingBox().inflate(0.7, 2.8, 0.7);
		if (!client.level.getEntitiesOfClass(FallingBlockEntity.class, search, entity ->
			entity.isAlive() && entity.getY() + 0.1 >= player.getY()).isEmpty()) {
			return true;
		}
		BlockPos feet = player.blockPosition();
		for (int dy = 1; dy <= 4; dy++) {
			for (int dx = -1; dx <= 1; dx++) {
				for (int dz = -1; dz <= 1; dz++) {
					BlockPos pos = feet.offset(dx, dy, dz);
					if (!isFallingType(client, pos)) continue;
					BlockPos below = pos.below();
					if (isReplaceable(client, below) || below.equals(target)) return true;
				}
			}
		}
		return false;
	}

	/** 该格是不是沙子、沙砾一类会下落的方块。 */
	private static boolean isFallingType(Minecraft client, BlockPos pos) {
		Block block = client.level.getBlockState(pos).getBlock();
		return block instanceof FallingBlock;
	}

	/** 目标上方是否还叠着会下落的方块。 */
	private static boolean sandStackedAbove(Minecraft client, BlockPos pos) {
		return client.level.getBlockState(pos.above()).getBlock() instanceof FallingBlock;
	}

	/** 打开或关闭 Meteor 飞行；找不到模组时按配置键（默认 C）。 */
	private void ensureFlying(Minecraft client, LocalPlayer player, boolean wantFly) {
		if (flyToggleCooldown > 0 && lastWantFly != null && lastWantFly == wantFly) return;
		Boolean meteor = meteorFlightActive();
		boolean flying = meteor != null ? meteor : player.getAbilities().flying;
		if (flying == wantFly) {
			lastWantFly = wantFly;
			return;
		}
		if (!toggleMeteorFlight()) {
			try {
				String key = config.ceilingFlyKey == null || config.ceilingFlyKey.isBlank()
					? "key.keyboard.c" : config.ceilingFlyKey;
				KeyMapping.click(InputConstants.getKey(key));
			} catch (RuntimeException ignored) {
			}
		}
		flyToggleCooldown = FLY_TOGGLE_COOLDOWN;
		lastWantFly = wantFly;
	}

	/** 反射读取 Meteor Flight 是否开启。 */
	private static Boolean meteorFlightActive() {
		try {
			Class<?> modulesClz = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
			Object modules = modulesClz.getMethod("get").invoke(null);
			if (modules == null) return null;
			Class<?> flightClz = Class.forName("meteordevelopment.meteorclient.systems.modules.movement.Flight");
			Object flight = modulesClz.getMethod("get", Class.class).invoke(modules, flightClz);
			if (flight == null) return null;
			return (Boolean) flight.getClass().getMethod("isActive").invoke(flight);
		} catch (Throwable ignored) {
			return null;
		}
	}

	/** 反射开关 Meteor Flight。 */
	private static boolean toggleMeteorFlight() {
		try {
			Class<?> modulesClz = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
			Object modules = modulesClz.getMethod("get").invoke(null);
			if (modules == null) return false;
			Class<?> flightClz = Class.forName("meteordevelopment.meteorclient.systems.modules.movement.Flight");
			Object flight = modulesClz.getMethod("get", Class.class).invoke(modules, flightClz);
			if (flight == null) return false;
			flight.getClass().getMethod("toggle").invoke(flight);
			return true;
		} catch (Throwable ignored) {
			return false;
		}
	}

	/** 从背包选出一块封路/垫脚方块。 */
	private ItemChoice selectSeal(Minecraft client, LocalPlayer player) {
		for (Item item : BorerItems.SEAL_ITEMS) {
			if (!(item instanceof BlockItem blockItem) || countItem(player, item) <= 0) continue;
			InteractionHand hand = selectItem(client, player, item);
			if (hand != null) return new ItemChoice(blockItem.getBlock(), hand);
		}
		return null;
	}

	/** 把该物品拿到手上。 */
	private InteractionHand selectItem(Minecraft client, LocalPlayer player, Item item) {
		if (player.getMainHandItem().is(item)) return InteractionHand.MAIN_HAND;
		if (player.getOffhandItem().is(item)) return InteractionHand.OFF_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			inventory.setSelectedSlot(slot);
			return InteractionHand.MAIN_HAND;
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			return InteractionHand.MAIN_HAND;
		}
		return null;
	}

	/** 背包某物品数量。 */
	private int countItem(LocalPlayer player, Item item) {
		int count = player.getOffhandItem().is(item) ? player.getOffhandItem().getCount() : 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (stack.is(item)) count += stack.getCount();
		}
		return count;
	}

	/** 固定准星朝前上方，沿视线挖够得着的方块。 */
	private void holdMiningLook(LocalPlayer player) {
		if (!haveMineLook) {
			mineYaw = player.getYRot();
			minePitch = -72.0F;
			haveMineLook = true;
		}
		player.setYRot(mineYaw);
		player.setXRot(minePitch);
		player.setYHeadRot(mineYaw);
	}

	/** 沿当前锁定的前上方视线裁剪。 */
	private BlockHitResult clipMiningLook(Minecraft client, LocalPlayer player) {
		holdMiningLook(player);
		double reach = Math.max(1.5, player.blockInteractionRange() - 0.2);
		Vec3 eye = player.getEyePosition();
		Vec3 dest = eye.add(player.getLookAngle().scale(reach));
		BlockHitResult hit = client.level.clip(new ClipContext(
			eye, dest, ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, player
		));
		return hit.getType() == HitResult.Type.BLOCK ? hit : null;
	}

	/** 先取正头顶挡路；视线打到侧壁不算。 */
	private BlockPos findCeilingAlongLook(Minecraft client, LocalPlayer player, double cruiseY) {
		AABB box = player.getBoundingBox();
		int minX = Mth.floor(box.minX);
		int maxX = Mth.floor(box.maxX - 1.0E-6);
		int minZ = Mth.floor(box.minZ);
		int maxZ = Mth.floor(box.maxZ - 1.0E-6);
		BlockHitResult along = clipMiningLook(client, player);
		if (along != null) {
			BlockPos look = along.getBlockPos();
			if (CruiseCeilingPolicy.acceptLookHit(
				CruiseCeilingPolicy.inAscentColumn(look.getX(), look.getZ(), minX, maxX, minZ, maxZ))
				&& shouldMine(client, look) && inReach(player, look) && !skipped.contains(look)) {
				return look.immutable();
			}
		}
		BlockPos nearby = findCeiling(client, player, cruiseY);
		if (nearby != null) nudgeLookToward(player, Vec3.atCenterOf(nearby));
		return nearby;
	}

	/** 只在当前视线打不到时，小幅度把准星转向新目标。 */
	private void nudgeLookToward(LocalPlayer player, Vec3 point) {
		holdMiningLook(player);
		Vec3 delta = point.subtract(player.getEyePosition());
		double horiz = Math.hypot(delta.x, delta.z);
		float wantYaw = (float)Math.toDegrees(Math.atan2(delta.z, delta.x)) - 90.0F;
		float wantPitch = (float)Math.toDegrees(-Math.atan2(delta.y, Math.max(0.001, horiz)));
		wantPitch = Mth.clamp(wantPitch, -85.0F, -50.0F);
		mineYaw += Mth.clamp(Mth.wrapDegrees(wantYaw - mineYaw), -6.0F, 6.0F);
		minePitch += Mth.clamp(wantPitch - minePitch, -4.0F, 4.0F);
		holdMiningLook(player);
	}

	/** 对着支撑面放下指定方块，放完立刻恢复前上方准星。 */
	private boolean placeAt(Minecraft client, LocalPlayer player, BlockPos pos, ItemChoice choice) {
		BlockHitResult support = findPlacementSupport(client, pos);
		if (support == null) return false;
		placingLook = true;
		lookAt(player, support.getLocation());
		client.hitResult = support;
		InteractionResult result = client.gameMode.useItemOn(player, choice.hand, support);
		placingLook = false;
		holdMiningLook(player);
		return result.consumesAction() || client.level.getBlockState(pos).is(choice.block);
	}

	/** 找一个可以贴着放方块的实心邻面。 */
	private BlockHitResult findPlacementSupport(Minecraft client, BlockPos pos) {
		Direction[] order = {Direction.DOWN, Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST, Direction.UP};
		for (Direction direction : order) {
			BlockPos support = pos.relative(direction);
			BlockState state = client.level.getBlockState(support);
			if (state.isAir() || state.canBeReplaced() || !state.getFluidState().isEmpty()) continue;
			if (state.getCollisionShape(client.level, support).isEmpty()) continue;
			Direction face = direction.getOpposite();
			Vec3 location = Vec3.atCenterOf(support).add(face.getStepX() * 0.51, face.getStepY() * 0.51, face.getStepZ() * 0.51);
			return new BlockHitResult(location, face, support, false);
		}
		return null;
	}

	/** 是否可替换方块。 */
	private static boolean isReplaceable(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		return (state.isAir() || state.canBeReplaced()) && state.getFluidState().isEmpty();
	}

	/** 找正上方要挖的挡路格。 */
	private BlockPos findCeiling(Minecraft client, LocalPlayer player, double cruiseY) {
		AABB box = player.getBoundingBox();
		double reach = Math.max(1.0, player.blockInteractionRange() - 0.35);
		int minX = Mth.floor(box.minX);
		int maxX = Mth.floor(box.maxX - 1.0E-6);
		int minZ = Mth.floor(box.minZ);
		int maxZ = Mth.floor(box.maxZ - 1.0E-6);
		int minY = Mth.floor(box.maxY - 0.08);
		int maxY = Math.min(Mth.floor(player.getEyeY() + reach), Mth.floor(Math.max(cruiseY + 1.0, box.maxY + 2.0)));
		if (maxY < minY) maxY = minY;

		AABB shaft = new AABB(box.minX, box.maxY - 0.15, box.minZ, box.maxX, Math.max(box.maxY + 0.4, maxY + 1.0), box.maxZ);
		BlockPos best = null;
		int bestOrder = Integer.MAX_VALUE;
		for (int y = minY; y <= maxY; y++) {
			for (int x = minX; x <= maxX; x++) {
				for (int z = minZ; z <= maxZ; z++) {
					BlockPos pos = new BlockPos(x, y, z);
					if (skipped.contains(pos) || !shouldMine(client, pos) || !collidesWith(client, pos, shaft)) continue;
					if (!inReach(player, pos)) continue;
					BlockHitResult hit = visibleHit(client, player, pos);
					if (hit == null) {
						BlockPos obstruction = visibleObstruction(client, player, pos);
						if (obstruction == null || skipped.contains(obstruction) || !shouldMine(client, obstruction)
							|| !CruiseCeilingPolicy.inAscentColumn(
								obstruction.getX(), obstruction.getZ(), minX, maxX, minZ, maxZ)) {
							continue;
						}
						pos = obstruction;
					}
					double dist = player.getEyePosition().distanceToSqr(Vec3.atCenterOf(pos));
					int order = CruiseCeilingPolicy.ascentOrder(pos.getY(), minY, dist);
					if (order < bestOrder) {
						bestOrder = order;
						best = pos.immutable();
					}
				}
			}
		}
		return best;
	}

	/** 头顶是基岩一类挖不掉的方块。 */
	public boolean blockedByUnbreakable(Minecraft client, LocalPlayer player) {
		return blockedUnbreakable(client, player);
	}

	/** 不可挖挡路（基岩等）。 */
	private boolean blockedUnbreakable(Minecraft client, LocalPlayer player) {
		AABB box = player.getBoundingBox();
		int minX = Mth.floor(box.minX);
		int maxX = Mth.floor(box.maxX - 1.0E-6);
		int minZ = Mth.floor(box.minZ);
		int maxZ = Mth.floor(box.maxZ - 1.0E-6);
		int minY = Mth.floor(box.maxY - 0.08);
		int maxY = minY + 2;
		for (int y = minY; y <= maxY; y++) {
			for (int x = minX; x <= maxX; x++) {
				for (int z = minZ; z <= maxZ; z++) {
					BlockPos pos = new BlockPos(x, y, z);
					BlockState state = client.level.getBlockState(pos);
					if (state.isAir() || state.canBeReplaced() || state.getCollisionShape(client.level, pos).isEmpty()) continue;
					if (!shouldMine(client, pos)) return true;
				}
			}
		}
		return false;
	}

	/** 上升路径是否仍被挡。 */
	private static boolean ascentBlocked(Minecraft client, LocalPlayer player) {
		return !client.level.noCollision(player, player.getBoundingBox().move(0.0, 0.25, 0.0));
	}

	/** 玩家碰撞是否碰到该格。 */
	private static boolean collidesWith(Minecraft client, BlockPos pos, AABB shaft) {
		VoxelShape shape = client.level.getBlockState(pos).getCollisionShape(client.level, pos);
		if (shape.isEmpty()) return false;
		return shaft.intersects(shape.bounds().move(pos));
	}

	/** 该格是否应挖。 */
	private static boolean shouldMine(Minecraft client, BlockPos pos) {
		BlockState state = client.level.getBlockState(pos);
		if (state.isAir() || state.liquid() || state.canBeReplaced()) return false;
		if (state.getCollisionShape(client.level, pos).isEmpty()) return false;
		if (state.getDestroySpeed(client.level, pos) < 0.0F) return false;
		if (state.is(Blocks.BEDROCK) || state.is(Blocks.BARRIER) || state.is(Blocks.END_PORTAL) || state.is(Blocks.END_PORTAL_FRAME)) {
			return false;
		}
		if (state.is(Blocks.CHEST) || state.is(Blocks.TRAPPED_CHEST) || state.is(Blocks.SPAWNER)) return false;
		return !client.player.blockActionRestricted(client.level, pos, client.gameMode.getPlayerMode());
	}

	/** 眼睛到目标是否够得着。 */
	private static boolean inReach(LocalPlayer player, BlockPos pos) {
		double reach = Math.max(1.25, player.blockInteractionRange() - 0.35);
		Vec3 eye = player.getEyePosition();
		Vec3 nearest = new Vec3(
			Mth.clamp(eye.x, pos.getX(), pos.getX() + 1.0),
			Mth.clamp(eye.y, pos.getY(), pos.getY() + 1.0),
			Mth.clamp(eye.z, pos.getZ(), pos.getZ() + 1.0)
		);
		return eye.distanceToSqr(nearest) <= reach * reach;
	}

	/** 视线打到目标格的命中。 */
	private static BlockHitResult visibleHit(Minecraft client, LocalPlayer player, BlockPos pos) {
		Vec3 center = Vec3.atCenterOf(pos);
		Vec3[] samples = {
			center,
			center.add(0.0, -0.49, 0.0),
			center.add(0.0, 0.49, 0.0),
			center.add(0.49, 0.0, 0.0), center.add(-0.49, 0.0, 0.0),
			center.add(0.0, 0.0, 0.49), center.add(0.0, 0.0, -0.49)
		};
		for (Vec3 sample : samples) {
			BlockHitResult hit = client.level.clip(new ClipContext(
				player.getEyePosition(), sample, ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, player
			));
			if (hit.getType() == HitResult.Type.BLOCK && hit.getBlockPos().equals(pos)) return hit;
		}
		return null;
	}

	/** 视线路径上挡住的方块。 */
	private static BlockPos visibleObstruction(Minecraft client, LocalPlayer player, BlockPos pos) {
		BlockHitResult hit = client.level.clip(new ClipContext(
			player.getEyePosition(), Vec3.atCenterOf(pos), ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, player
		));
		if (hit.getType() != HitResult.Type.BLOCK) return null;
		return hit.getBlockPos().immutable();
	}

	/** 瞬间对准。 */
	private static void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/** 方块显示名。 */
	private static String label(Minecraft client, BlockPos pos) {
		return client.level.getBlockState(pos).getBlock().getName().getString();
	}

	/** 坐标短字符串。 */
	private static String format(BlockPos pos) {
		return pos.getX() + "," + pos.getY() + "," + pos.getZ();
	}

	/** 选中的垫脚方块与手。 */
	private record ItemChoice(Block block, InteractionHand hand) {
	}
}
