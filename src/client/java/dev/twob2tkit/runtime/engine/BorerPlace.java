package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.protocol.game.ServerboundMovePlayerPacket;
import net.minecraft.tags.ItemTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

/** 选镐、封口/铺路、扔废石。SealChoice 类型仍挂在引擎上。 */
final class BorerPlace {
	private final DefaultTunnelBorerEngine engine;

	BorerPlace(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 封堵方块。 */
	DefaultTunnelBorerEngine.SealChoice selectSealBlock(Minecraft client, LocalPlayer player) {
		for (Item item : BorerItems.SEAL_ITEMS) {
			if (!(item instanceof BlockItem blockItem) || countItem(player, item) <= 0) continue;
			InteractionHand hand = selectItem(client, player, item);
			if (hand != null) return new DefaultTunnelBorerEngine.SealChoice(item, blockItem.getBlock(), hand);
		}
		return null;
	}

	/** 把手上换成指定物品。 */
	private InteractionHand selectItem(Minecraft client, LocalPlayer player, Item item) {
		if (player.getMainHandItem().is(item)) return InteractionHand.MAIN_HAND;
		if (player.getOffhandItem().is(item)) return InteractionHand.OFF_HAND;
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			inventory.setSelectedSlot(slot);
			return InteractionHand.MAIN_HAND;
		}
		int dest = hotbarSlotForUtility(inventory);
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			inventory.setSelectedSlot(dest);
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, dest, ContainerInput.SWAP, player);
			return InteractionHand.MAIN_HAND;
		}
		return null;
	}

	/** 把挖这个方块最快的工具拿到手上；镐在背包里也会换出来，不挤掉快捷栏里别的镐。 */
	void selectMiningTool(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (client.level == null || client.gameMode == null) return;
		BlockState state = client.level.getBlockState(pos);
		Inventory inventory = player.getInventory();
		int bestSlot = -1;
		float bestScore = toolScore(player.getMainHandItem(), state);
		for (int slot = 0; slot < 36; slot++) {
			float score = toolScore(inventory.getItem(slot), state);
			if (score > bestScore + 0.01F) {
				bestScore = score;
				bestSlot = slot;
			}
		}
		if (bestSlot < 0) return;
		if (bestSlot < 9) {
			inventory.setSelectedSlot(bestSlot);
			return;
		}
		int dest = hotbarSlotForTool(inventory);
		inventory.setSelectedSlot(dest);
		client.gameMode.handleContainerInput(player.containerMenu.containerId, bestSlot, dest, ContainerInput.SWAP, player);
	}

	/** 工具对该方块的破坏分。 */
	private static float toolScore(ItemStack stack, BlockState state) {
		if (stack.isEmpty() || BorerItems.isTooWorn(stack)) return 0.0F;
		float speed = stack.getDestroySpeed(state);
		if (stack.isCorrectToolForDrops(state)) speed += 1.0F;
		if (stack.is(ItemTags.PICKAXES)) speed += 0.25F;
		// 矿石优先时运：效率镐的破坏速度更高，不加这一档会永远拿着效率镐挖钻石。
		if (OreTarget.fortuneApplies(state)) {
			int fortune = BorerItems.fortuneLevel(stack);
			if (fortune > 0) speed += 1000.0F + fortune * 10.0F;
		}
		return speed;
	}

	/** 拿封路方块时避开镐所在格，避免把镐换进背包。 */
	private static int hotbarSlotForUtility(Inventory inventory) {
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).isEmpty()) return slot;
		}
		for (int slot = 8; slot >= 0; slot--) {
			if (!BorerItems.isMiningTool(inventory.getItem(slot))) return slot;
		}
		return 8;
	}

	/** 快捷栏里挖矿工具格。 */
	private static int hotbarSlotForTool(Inventory inventory) {
		int selected = inventory.getSelectedSlot();
		if (selected >= 0 && selected < 9 && inventory.getItem(selected).isEmpty()) return selected;
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).isEmpty()) return slot;
		}
		if (selected >= 0 && selected < 9 && !BorerItems.isMiningTool(inventory.getItem(selected))) return selected;
		return selected >= 0 && selected < 9 ? selected : 0;
	}

	/** 自己垫的台阶、封水路不能立刻再挖掉，否则会一直放石头又挖石头。 */
	boolean placeAndProtect(Minecraft client, LocalPlayer player, BlockPos pos, DefaultTunnelBorerEngine.SealChoice choice) {
		boolean placed = placeSealAt(client, player, pos, choice.block(), choice.hand());
		if (placed) rememberPlacedSupport(pos, choice.block());
		return placed;
	}

	/** 记住刚放置的支撑/封堵格。 */
	void rememberPlacedSupport(BlockPos pos, Block block) {
		engine.protectedSealBlocks.put(pos.immutable(), block);
		if (engine.currentTarget != null && engine.currentTarget.equals(pos)) {
			engine.clearMiningTarget(Minecraft.getInstance(), "placed-protected-support");
		}
	}

	/** 前方是空气/洞穴就铺路。能安全落下时不垫，矿石就在那一格坑里时也不垫平。 */
	boolean shouldBridgeDrops(LocalPlayer player) {
		if (engine.mode == DefaultTunnelBorerEngine.Mode.DOWN || engine.mode == DefaultTunnelBorerEngine.Mode.AREA) return false;
		if (engine.verticalMove == DefaultTunnelBorerEngine.VerticalMove.DOWN) return false;
		Minecraft client = Minecraft.getInstance();
		if (client != null && client.level != null && player != null
			&& !BorerFallPolicy.shouldBridge(BorerHazards.safeFallDepth(client, player.blockPosition().relative(engine.forward)))) {
			return false;
		}
		if (engine.mode != DefaultTunnelBorerEngine.Mode.ORE) return true;
		BlockPos goal = engine.loot.active() ? engine.loot.origin()
			: engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		if (goal == null) return true;
		BlockPos feet = player.blockPosition();
		BlockPos front = feet.relative(engine.forward);
		if (goal.getY() >= feet.getY()) return true;
		boolean inFeetCol = goal.getX() == feet.getX() && goal.getZ() == feet.getZ();
		boolean inFrontCol = goal.getX() == front.getX() && goal.getZ() == front.getZ();
		return !inFeetCol && !inFrontCol;
	}

	/** 在指定格封堵放置。 */
	private boolean placeSealAt(Minecraft client, LocalPlayer player, BlockPos pos, Block block, InteractionHand hand) {
		BlockHitResult support = findPlacementSupport(client, pos);
		if (support != null && tryPlaceOn(client, player, pos, block, hand, support)) return true;
		return tryPlaceOn(client, player, pos, block, hand, airPlaceHit(player, pos));
	}

	/** 先试脚下潜行搭边，再邻面点击，最后隔空放置。 */
	private boolean placeBridgeBlock(Minecraft client, LocalPlayer player, BlockPos pos, DefaultTunnelBorerEngine.SealChoice choice) {
		BlockPos stand = player.blockPosition().below();
		if (engine.isStandable(client, stand) && !stand.equals(pos)) {
			BlockHitResult edge = clickFace(stand, engine.forward);
			if (tryPlaceOn(client, player, pos, choice.block(), choice.hand(), edge)) return true;
		}
		return placeSealAt(client, player, pos, choice.block(), choice.hand());
	}

	/** 在命中面上尝试放置；失败返回 false。 */
	private boolean tryPlaceOn(
		Minecraft client,
		LocalPlayer player,
		BlockPos pos,
		Block block,
		InteractionHand hand,
		BlockHitResult hit
	) {
		if (hit == null || client.gameMode == null) return false;
		engine.lookAt(player, hit.getLocation());
		InteractionResult result = client.gameMode.useItemOn(player, hand, hit);
		return result.consumesAction() || client.level.getBlockState(pos).is(block);
	}

	/** 隔空放置用的假命中。 */
	private BlockHitResult airPlaceHit(LocalPlayer player, BlockPos pos) {
		Vec3 center = Vec3.atCenterOf(pos);
		Vec3 eye = player.getEyePosition();
		Direction face = Direction.getApproximateNearest(eye.x - center.x, eye.y - center.y, eye.z - center.z);
		return clickFace(pos, face);
	}

	/** 点支撑面某方向。 */
	private static BlockHitResult clickFace(BlockPos support, Direction face) {
		Vec3 location = Vec3.atCenterOf(support).add(face.getStepX() * 0.51, face.getStepY() * 0.51, face.getStepZ() * 0.51);
		return new BlockHitResult(location, face, support, false);
	}

	/** 找可点击的支撑面。 */
	private BlockHitResult findPlacementSupport(Minecraft client, BlockPos pos) {
		Direction[] order = {Direction.DOWN, Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST, Direction.UP};
		for (Direction direction : order) {
			BlockPos support = pos.relative(direction);
			BlockState state = client.level.getBlockState(support);
			if (state.isAir() || state.canBeReplaced() || !state.getFluidState().isEmpty()) continue;
			Direction face = direction.getOpposite();
			Vec3 location = Vec3.atCenterOf(support).add(face.getStepX() * 0.51, face.getStepY() * 0.51, face.getStepZ() * 0.51);
			return new BlockHitResult(location, face, support, false);
		}
		return null;
	}

	/** 背包该物品数量。 */
	private int countItem(LocalPlayer player, Item item) {
		return BorerItems.countItem(player, item);
	}

	/** 找矿时背包快满才把废石朝身后扔。只改本地朝向服务器收不到，会往前丢又捡回来。 */
	void discardExcessStone(Minecraft client, LocalPlayer player) {
		if (engine.discardCooldown > 0) {
			engine.discardCooldown--;
			return;
		}
		if (client.level == null || client.gameMode == null) return;
		if (!player.containerMenu.getCarried().isEmpty()) return;
		Inventory inventory = player.getInventory();
		if (BorerItems.emptySlots(inventory) > BorerItems.EMPTY_SLOTS_BEFORE_DISCARD) return;
		for (int slot = 0; slot < 36; slot++) {
			ItemStack stack = inventory.getItem(slot);
			if (stack.isEmpty()) continue;
			boolean xpSkip = engine.coalXpMode() && OreTarget.COAL.matchesDrop(stack)
				|| engine.quartzXpMode() && OreTarget.QUARTZ.matchesDrop(stack);
			if (!xpSkip && !BorerItems.isJunkStone(stack.getItem())) continue;
			if (!xpSkip && OreTarget.selectedMatchesDrop(engine.oreConfig(), stack)) continue;
			int total = countItem(player, stack.getItem());
			boolean seal = !xpSkip && BorerItems.isSealItem(stack.getItem());
			int keep = xpSkip ? 0 : BorerItems.sealReserve(stack.getItem());
			if (total <= keep) continue;
			if (seal && total - stack.getCount() < keep && stack.getCount() <= keep + 8) continue;
			throwStackBehind(client, player, slot < 9 ? slot + 36 : slot);
			if (player.getMainHandItem().isEmpty() && engine.currentTarget != null) {
				selectMiningTool(client, player, engine.currentTarget);
			}
			return;
		}
	}

	/** 先把朝后的视角包发给服务器，再扔，再把本地朝向转回来继续挖。 */
	private void throwStackBehind(Minecraft client, LocalPlayer player, int menuSlot) {
		float yaw = player.getYRot();
		float pitch = player.getXRot();
		float backYaw = yaw + 180.0F;
		float backPitch = -20.0F;
		// 连同 yRotO/xRotO 一起写：否则渲染插值会把这一帧画成回头的闪影。
		RotationAim.apply(player, backYaw, backPitch);
		if (player.connection != null) {
			player.connection.send(new ServerboundMovePlayerPacket.Rot(
				backYaw, backPitch, player.onGround(), player.horizontalCollision));
		}
		client.gameMode.handleContainerInput(
			player.containerMenu.containerId, menuSlot, 1, ContainerInput.THROW, player
		);
		RotationAim.apply(player, yaw, pitch);
		engine.discardCooldown = 8;
		engine.discardPauseTicks = 6;
	}

	/** 物品短标签。 */
	String itemLabel(Item item) {
		return new ItemStack(item).getHoverName().getString();
	}

	/** 补完一格落脚方块后，短时间优先走到那一列，避免规划器马上抢走前进键。 */
	boolean continueDescentBridgeAdvance(Minecraft client, LocalPlayer player) {
		if (engine.descentBridgeTarget == null || engine.descentBridgeAdvanceTicks <= 0) return false;
		BlockPos feet = player.blockPosition();
		if (feet.getX() == engine.descentBridgeTarget.getX() && feet.getZ() == engine.descentBridgeTarget.getZ()) {
			engine.descentBridgeTarget = null;
			engine.descentBridgeAdvanceTicks = 0;
			return false;
		}
		Direction bridgeHeading = engine.headingToward(feet, engine.descentBridgeTarget);
		if (bridgeHeading != null) engine.forward = bridgeHeading;
		if (engine.unsafeToWalk(client, player)) {
			engine.descentBridgeTarget = null;
			engine.descentBridgeAdvanceTicks = 0;
			return false;
		}
		engine.descentBridgeAdvanceTicks--;
		engine.releaseMine(client);
		engine.faceTowardPathCenter(player);
		engine.nudgeToColumnCenter(client, player);
		client.options.keyShift.setDown(false);
		client.options.keyUp.setDown(true);
		engine.attemptedForward = true;
		engine.status = "已垫落脚方块，正走上去继续挖 " + BorerText.block(engine.descentBridgeTarget);
		engine.overlay(client, engine.status, 0x55FFFF);
		if (engine.descentBridgeAdvanceTicks == 0) engine.descentBridgeTarget = null;
		return true;
	}

	/** 安全落差确实走不进去时，只补前方脚下一格；不覆盖矿石或目标下降列。 */
	boolean placeStalledDescentSupport(Minecraft client, LocalPlayer player, int drop) {
		BlockPos front = player.blockPosition().relative(engine.forward);
		BlockPos support = front.below();
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		boolean supportOnGoalColumn = goal != null
			&& goal.getX() == support.getX() && goal.getZ() == support.getZ();
		boolean supportContainsOre = OreTarget.ANY.matches(client.level.getBlockState(support));
		if (!BorerFallPolicy.shouldBridgeStalledSafeDrop(
			drop, engine.noMovementTicks, supportContainsOre, supportOnGoalColumn)) return false;
		if (!engine.canFillWalkway(client, support)) return false;
		DefaultTunnelBorerEngine.SealChoice choice = selectSealBlock(client, player);
		if (choice == null) return false;
		client.options.keyShift.setDown(true);
		client.options.keyUp.setDown(false);
		boolean placed = placeBridgeBlock(client, player, support, choice)
			|| placeAndProtect(client, player, support, choice);
		if (!placed) return false;
		rememberPlacedSupport(support, choice.block());
		engine.descentBridgeTarget = front.immutable();
		engine.descentBridgeAdvanceTicks = 12;
		engine.verticalMove = DefaultTunnelBorerEngine.VerticalMove.NONE;
		engine.status = "落差前走不动，已用" + itemLabel(choice.item()) + "补落脚 " + BorerText.block(support);
		engine.fileLog(client, "stalled-drop-bridge drop=" + drop + " support=" + BorerText.block(support)
			+ " goal=" + (goal == null ? "-" : BorerText.block(goal))
			+ " player=" + BorerText.precise(player));
		engine.overlay(client, engine.status, 0x55FFFF);
		return true;
	}

	/** 往岩浆或落差上铺石头；铺不成再挖头顶跳过去。 */
	boolean placeWalkingSupport(Minecraft client, LocalPlayer player) {
		DefaultTunnelBorerEngine.SealChoice choice = selectSealBlock(client, player);
		if (choice == null) {
			engine.status = "前方落差，背包没有圆石/石头可铺路";
			engine.overlay(client, engine.status, 0xFF5555);
			return false;
		}
		client.options.keyShift.setDown(true);
		client.options.keyUp.setDown(false);
		BlockPos feet = player.blockPosition();
		BlockPos front = feet.relative(engine.forward);
		BlockPos[] fills = {feet.below(), front.below(), engine.isLava(client, front) ? front : null};
		BlockPos lavaTarget = null;
		for (BlockPos pos : fills) {
			if (pos == null || !engine.canFillWalkway(client, pos)) continue;
			if (player.getBoundingBox().deflate(0.05).intersects(new AABB(pos)) && !engine.isLava(client, pos)) continue;
			if (engine.isLava(client, pos)) lavaTarget = pos;
			boolean placed = placeBridgeBlock(client, player, pos, choice) || placeAndProtect(client, player, pos, choice);
			if (!placed) continue;
			rememberPlacedSupport(pos, choice.block());
			engine.status = engine.isLava(client, pos)
				? "已在岩浆上铺" + itemLabel(choice.item()) + " " + BorerText.block(pos)
				: "已用" + itemLabel(choice.item()) + "铺路 " + BorerText.block(pos);
			engine.overlay(client, engine.status, 0x55FFFF);
			return true;
		}
		if (lavaTarget != null) {
			engine.status = "正在往岩浆上铺" + itemLabel(choice.item()) + " " + BorerText.block(lavaTarget);
			engine.overlay(client, engine.status, 0xFFFF55);
			return false;
		}
		BlockPos support = front.below();
		if (!engine.canFillWalkway(client, support)) return false;
		engine.status = "前方落差，正在用" + itemLabel(choice.item()) + "铺路 " + BorerText.block(support);
		engine.overlay(client, engine.status, 0xFFFF55);
		return false;
	}

	/** 岩浆铺不上时：挖开头顶和头顶前方，再跳过去。 */
	boolean startJumpOverLava(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		BlockPos front = feet.relative(engine.forward);
		if (!engine.isLava(client, front) && !engine.isLava(client, front.below()) && !engine.isLava(client, feet.below())) return false;
		BlockPos ceiling = feet.above(2);
		BlockPos frontCeiling = front.above(2);
		BlockPos toMine = null;
		BlockPos[] blockers = {ceiling, frontCeiling, front.above()};
		for (BlockPos pos : blockers) {
			if (!engine.canPlanMine(client, pos) || !engine.inMiningReach(player, pos)) continue;
			if (engine.canSeeBlock(client, player, pos) || engine.playerTouchesBlock(player, pos) || engine.hasCollision(client, pos)) {
				toMine = pos;
				break;
			}
		}
		if (toMine != null) {
			engine.setMiningTarget(client, player, toMine, "jump-over-lava-headroom");
			client.options.keyUp.setDown(false);
			client.options.keyJump.setDown(false);
			client.options.keyShift.setDown(false);
			engine.status = "挖开头顶，准备跳过岩浆 " + BorerText.block(toMine);
			return true;
		}
		if (engine.hasCollision(client, ceiling) || engine.hasCollision(client, frontCeiling)) return false;
		if (engine.hasCollision(client, front) && !engine.isLava(client, front)) return false;
		if (engine.enableMeteorFlight(player)) {
			client.options.keyJump.setDown(true);
			client.options.keyUp.setDown(false);
			client.options.keyShift.setDown(false);
			engine.status = "飞行升高绕过岩浆";
			return true;
		}
		if (!player.onGround()) return false;
		client.options.keyJump.setDown(true);
		client.options.keyUp.setDown(true);
		client.options.keyShift.setDown(false);
		engine.status = "跳过前方岩浆";
		return true;
	}
}
