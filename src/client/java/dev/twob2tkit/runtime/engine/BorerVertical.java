package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.phys.AABB;

/** 矿石不在同一层时的台阶、1×2 开口、跳跃和攀爬落差。 */
final class BorerVertical {
	private static final int JUMP_PRESS_TICKS = 3;
	private static final int JUMP_RETRY_COOLDOWN_TICKS = 12;
	private static final int MAX_JUMP_ATTEMPTS_PER_BLOCK = 2;

	private final DefaultTunnelBorerEngine engine;

	BorerVertical(DefaultTunnelBorerEngine engine) {
		this.engine = engine;
	}

	/** 矿石不在同一层时，挖通道、台阶或选择跳跃方向。 */
	BlockPos nextRouteTarget(Minecraft client, LocalPlayer player, BlockPos goal) {
		BlockPos feet = engine.standingColumn(client, player);
		boolean ascending = goal.getY() > feet.getY();
		engine.lockHeadingToward(feet, goal);
		if (ascending) {
			BlockPos jammed = engine.collidingHeadBlock(client, player);
			if (jammed != null) return jammed;
			engine.forcedTallObstacleLower = null;
			BlockPos directFront = feet.relative(engine.forward);
			if (player.onGround() && engine.isStandable(client, directFront)) {
				BlockPos headroom = firstMineableHeadroom(client, player, directFront);
				if (headroom != null) {
					engine.resetJumpControl();
					return headroom;
				}
			}
			BlockPos ceiling = feet.above(2);
			if (engine.canPlanMine(client, ceiling)) {
				if (engine.inMiningReach(player, ceiling) && engine.canSeeBlock(client, player, ceiling)) return ceiling;
				engine.routeIssue = "头顶遮挡 " + BorerText.block(ceiling) + " 不可见或超出可挖距离";
				engine.frontOccluded = true;
				return null;
			}
			BlockState ceilingState = client.level.getBlockState(ceiling);
			if (!ceilingState.isAir() && !ceilingState.canBeReplaced() && ceilingState.getFluidState().isEmpty()) {
				engine.routeIssue = "头顶遇到不可破坏或受保护方块 " + BorerText.block(ceiling) + "，尝试其他方向";
			}
		}
		int horizontalDistance = Math.abs(goal.getX() - feet.getX()) + Math.abs(goal.getZ() - feet.getZ());
		int climbNeeded = Math.max(1, goal.getY() - feet.getY() - 2);
		boolean allowFlatAdvance = ascending && horizontalDistance > climbNeeded;
		boolean flying = ascending && BorerFlight.isFlying(player);
		Direction stepDirection = chooseStepDirection(client, feet, ascending, allowFlatAdvance, flying);
		if (stepDirection == null) {
			BlockPos gap = nextOpenableOneByTwo(client, player);
			if (gap != null) {
				engine.resetJumpControl();
				return gap;
			}
			if (ascending && placeTemporaryStep(client, player, feet)) return null;
			engine.routeIssue = ascending
				? "向上寻路没有可站立地面，也无法用背包方块补临时台阶"
				: "向下寻路没有安全落脚方块";
			engine.frontOccluded = true;
			return null;
		}
		engine.forward = stepDirection;
		BlockPos front = feet.relative(engine.forward);
		if (!ascending) {
			BlockPos stair = nextDownStairBlock(client, player, front);
			if (stair != null) {
				engine.resetJumpControl();
				return stair;
			}
			int drop = BorerHazards.safeFallDepth(client, front);
			if (BorerStairPolicy.shouldWalkDown(drop)) {
				engine.verticalMove = DefaultTunnelBorerEngine.VerticalMove.DOWN;
				return null;
			}
			BlockPos gap = nextOpenableOneByTwo(client, player);
			if (gap != null) {
				engine.resetJumpControl();
				return gap;
			}
			engine.routeIssue = "向下寻路没有安全落脚方块";
			engine.frontOccluded = true;
			return null;
		}
		if (ascending && engine.isReplaceable(client, front) && engine.isStandable(client, front.below())) {
			BlockPos headroom = firstMineableHeadroom(client, player, front);
			if (headroom != null) {
				engine.resetJumpControl();
				return headroom;
			}
			if (placeTemporaryStep(client, player, feet)) return null;
		}
		if (engine.mode == DefaultTunnelBorerEngine.Mode.ORE && engine.canPlanMine(client, front) && !isClimbFoothold(client, player, front)
			&& engine.inMiningReach(player, front)
			&& (engine.canSeeBlock(client, player, front) || engine.playerTouchesBlock(player, front))) {
			engine.resetJumpControl();
			return front.immutable();
		}
		boolean existingStep = ascending && engine.isStandable(client, front);
		boolean flatAdvance = ascending && !existingStep && !flying
			&& engine.isReplaceable(client, front) && engine.isReplaceable(client, front.above())
			&& engine.isStandable(client, front.below());
		if (ascending && existingStep && !flying && engine.isWalkableOneBlockStep(client, player, front)) {
			engine.resetJumpControl();
			engine.verticalMove = DefaultTunnelBorerEngine.VerticalMove.ADVANCE;
			return null;
		}
		if (ascending && existingStep && !flying) {
			BlockPos stepBlock = mineInsteadOfJump(client, player, front);
			if (stepBlock != null) {
				engine.resetJumpControl();
				return stepBlock;
			}
		}
		BlockPos[] clearance = ascending
			? existingStep
				? new BlockPos[]{front.above(), front.above(2)}
				: flying
					? new BlockPos[]{front, front.above(), front.above(2)}
					: new BlockPos[]{front, front.above()}
			: new BlockPos[]{front, front.above()};
		BlockPos blockedClearance = null;
		for (BlockPos pos : clearance) {
			if (isClimbFoothold(client, player, pos)) continue;
			if (!engine.canPlanMine(client, pos)) continue;
			if (engine.inMiningReach(player, pos) && (engine.canSeeBlock(client, player, pos) || engine.playerTouchesBlock(player, pos))) {
				return pos;
			}
			if (blockedClearance == null) blockedClearance = pos;
		}
		if (blockedClearance != null) {
			engine.routeIssue = "垂直阶梯遮挡 " + BorerText.block(blockedClearance) + " 不可见或超出可挖距离";
			engine.frontOccluded = true;
			return null;
		}
		for (BlockPos pos : clearance) {
			if (isClimbFoothold(client, player, pos)) continue;
			BlockState state = client.level.getBlockState(pos);
			if (!state.isAir() && !state.canBeReplaced() && state.getFluidState().isEmpty()) {
				engine.routeIssue = "垂直阶梯遇到不可破坏方块 " + BorerText.block(pos);
				engine.frontOccluded = true;
				return null;
			}
		}
		if (ascending && existingStep && !flying && jumpAttemptsExhausted(player)) {
			BlockPos stepBlock = mineInsteadOfJump(client, player, front);
			if (stepBlock != null) {
				engine.resetJumpControl();
				return stepBlock;
			}
			if (engine.enableMeteorFlight(player)) {
				engine.verticalMove = DefaultTunnelBorerEngine.VerticalMove.UP;
				engine.routeIssue = "";
				engine.status = "台阶跳不过去，已开 Meteor 飞行越过 " + BorerText.block(front);
				return null;
			}
			engine.routeIssue = "向上台阶连续两次起跳都没有提升高度，已改为寻找可挖挡路";
			engine.frontOccluded = true;
			return null;
		}
		engine.verticalMove = existingStep || flying
			? DefaultTunnelBorerEngine.VerticalMove.UP
			: flatAdvance ? DefaultTunnelBorerEngine.VerticalMove.ADVANCE : DefaultTunnelBorerEngine.VerticalMove.UP;
		return null;
	}

	/** 向下接近时：先清眼前 1×2 实心挡路，平地再挖前方地板做出一格台阶。花草可替换不算挡路。 */
	BlockPos nextDownStairBlock(Minecraft client, LocalPlayer player, BlockPos front) {
		for (BlockPos pos : new BlockPos[]{front, front.above()}) {
			if (engine.isReplaceable(client, pos) || !engine.canPlanMine(client, pos)) continue;
			if (!engine.inMiningReach(player, pos)) continue;
			if (engine.canSeeBlock(client, player, pos) || engine.playerTouchesBlock(player, pos) || engine.hasCollision(client, pos)) {
				return pos.immutable();
			}
		}
		int drop = BorerHazards.safeFallDepth(client, front);
		if (!BorerStairPolicy.shouldCutFloor(drop)) return null;
		BlockPos floor = front.below();
		if (!engine.canPlanMine(client, floor) || !engine.inMiningReach(player, floor)) return null;
		if (engine.isStandingSupport(client, player, floor)) return null;
		if (engine.canSeeBlock(client, player, floor) || engine.playerTouchesBlock(player, floor) || engine.hasCollision(client, floor)) {
			return floor.immutable();
		}
		return null;
	}

	/**
	 * F3 朝向那一列的 1×2：脚前空、头前有方块就挖头。
	 * 矿还不在当前列时先朝矿开，不要挖反方向。贴坑沿用身体所在格。
	 */
	BlockPos nextOpenableOneByTwo(Minecraft client, LocalPlayer player) {
		BlockPos body = player.blockPosition();
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		if (goal != null) {
			int horiz = Math.abs(goal.getX() - body.getX()) + Math.abs(goal.getZ() - body.getZ());
			Direction toward = engine.headingToward(body, goal);
			if (BorerStairPolicy.tryOreHeadingFirst(horiz) && toward != null) {
				BlockPos gap = oneByTwoCellToMine(client, player, toward);
				if (gap != null) return gap;
			}
		}
		Direction look = player.getDirection();
		if (look.getAxis() != Direction.Axis.Y) {
			BlockPos gap = oneByTwoCellToMine(client, player, look);
			if (gap != null) return gap;
		}
		if (engine.forward.getAxis() != Direction.Axis.Y) {
			BlockPos gap = oneByTwoCellToMine(client, player, engine.forward);
			if (gap != null) return gap;
		}
		for (Direction dir : Direction.Plane.HORIZONTAL) {
			BlockPos gap = oneByTwoHeadIfFeetOpen(client, player, dir, body);
			if (gap != null) return gap;
		}
		return null;
	}

	/** 前方 1×2 该挖哪格。 */
	private BlockPos oneByTwoCellToMine(Minecraft client, LocalPlayer player, Direction heading) {
		BlockPos body = player.blockPosition();
		BlockPos gap = oneByTwoAtColumn(client, player, heading, body);
		if (gap != null) return gap;
		BlockPos stand = engine.standingColumn(client, player);
		if (!stand.equals(body)) return oneByTwoAtColumn(client, player, heading, stand);
		return null;
	}

	/** 指定柱上 1×2 该挖哪格。 */
	private BlockPos oneByTwoAtColumn(Minecraft client, LocalPlayer player, Direction heading, BlockPos feet) {
		BlockPos head = oneByTwoHeadIfFeetOpen(client, player, heading, feet);
		if (head != null) return head;
		BlockPos front = feet.relative(heading);
		BlockPos above = front.above();
		boolean frontMineable = engine.corridor.canAttemptMine(client, player, front, 1);
		boolean headMineable = engine.corridor.canAttemptMine(client, player, above, 1);
		if (BorerMiningPolicy.mineHeadToSeeAdjacentOre(frontMineable, headMineable)) {
			engine.forward = heading;
			engine.fileLog(client, "open-1x2-head-before-ore heading=" + BorerText.direction(heading)
				+ " feet=" + BorerText.block(front) + " head=" + BorerText.block(above)
				+ " player=" + BorerText.precise(player));
			return above.immutable();
		}
		if (frontMineable) {
			engine.forward = heading;
			return front.immutable();
		}
		if (headMineable) {
			engine.forward = heading;
			return above.immutable();
		}
		return null;
	}

	/** 脚通头堵时挖头。 */
	private BlockPos oneByTwoHeadIfFeetOpen(Minecraft client, LocalPlayer player, Direction heading, BlockPos feet) {
		BlockPos front = feet.relative(heading);
		BlockPos head = front.above();
		boolean feetOpen = engine.isReplaceable(client, front);
		boolean headMineable = engine.canPlanMine(client, head) && engine.inMiningReach(player, head)
			&& (engine.canSeeBlock(client, player, head) || engine.playerTouchesBlock(player, head) || engine.hasCollision(client, head));
		if (!BorerStairPolicy.mineHeadToOpenOneByTwo(feetOpen, headMineable)) return null;
		engine.forward = heading;
		engine.fileLog(client, "open-1x2 heading=" + BorerText.direction(heading)
			+ " feet=" + BorerText.block(front) + "=air head=" + BorerText.block(head)
			+ " player=" + BorerText.precise(player));
		return head.immutable();
	}

	/** 本拍是否应按跳跃。 */
	boolean pressJump(Minecraft client, LocalPlayer player) {
		if (BorerFlight.isFlying(player)) return true;
		if (!hasJumpClearance(client, player)) return false;
		if (!player.onGround()) {
			engine.jumpPressTicks = 0;
			return false;
		}
		BlockPos origin = player.blockPosition();
		boolean sameColumn = engine.jumpOrigin != null
			&& engine.jumpOrigin.getX() == origin.getX()
			&& engine.jumpOrigin.getZ() == origin.getZ();
		if (!sameColumn) {
			engine.jumpOrigin = origin.immutable();
			engine.jumpPressTicks = 0;
			engine.jumpRetryCooldownTicks = 0;
			engine.jumpAttempts = 0;
		}
		if (engine.jumpPressTicks > 0) {
			engine.jumpPressTicks--;
			return true;
		}
		if (engine.jumpRetryCooldownTicks > 0) {
			engine.jumpRetryCooldownTicks--;
			return false;
		}
		if (engine.jumpAttempts >= MAX_JUMP_ATTEMPTS_PER_BLOCK) return false;
		engine.jumpAttempts++;
		engine.jumpPressTicks = JUMP_PRESS_TICKS - 1;
		engine.jumpRetryCooldownTicks = JUMP_RETRY_COOLDOWN_TICKS;
		return true;
	}

	/** 跳跃头顶是否通。 */
	private boolean hasJumpClearance(Minecraft client, LocalPlayer player) {
		BlockPos feet = player.blockPosition();
		BlockPos front = feet.relative(engine.forward);
		BlockPos[] clearance = {feet.above(2), front.above(), front.above(2)};
		for (BlockPos pos : clearance) {
			if (!client.level.getBlockState(pos).getCollisionShape(client.level, pos).isEmpty()) return false;
		}
		return true;
	}

	/** 跳跃尝试是否用尽。 */
	private boolean jumpAttemptsExhausted(LocalPlayer player) {
		return engine.jumpOrigin != null
			&& engine.jumpOrigin.getX() == player.blockPosition().getX()
			&& engine.jumpOrigin.getZ() == player.blockPosition().getZ()
			&& engine.jumpPressTicks == 0 && engine.jumpRetryCooldownTicks == 0
			&& engine.jumpAttempts >= MAX_JUMP_ATTEMPTS_PER_BLOCK;
	}

	/** 1×2 通道里跳不过去的台阶：先挖头顶挡路，不挖立足点。 */
	private BlockPos mineInsteadOfJump(Minecraft client, LocalPlayer player, BlockPos front) {
		if (!hasJumpClearance(client, player) || jumpAttemptsExhausted(player)) {
			BlockPos looked = engine.corridor.corridorCrosshair(client, player, engine.standingColumn(client, player));
			if (looked != null) {
				BlockPos climb = climbTargetInsteadOfFoothold(client, player, looked);
				if (climb != null) return climb;
			}
			BlockPos[] blockers = {front.above(), front.above(2), engine.standingColumn(client, player).above(2)};
			for (BlockPos pos : blockers) {
				if (!engine.canPlanMine(client, pos) || isClimbFoothold(client, player, pos)) continue;
				if (engine.inMiningReach(player, pos)
					&& (engine.canSeeBlock(client, player, pos) || engine.playerTouchesBlock(player, pos) || engine.hasCollision(client, pos))) {
					return pos.immutable();
				}
			}
		}
		return null;
	}

	/** 垂直寻路时选下一步水平朝向（可走/可挖/飞行净空）。 */
	private Direction chooseStepDirection(
		Minecraft client,
		BlockPos feet,
		boolean ascending,
		boolean allowFlatAdvance,
		boolean flying
	) {
		Direction[] candidates = {engine.forward, engine.forward.getClockWise(), engine.forward.getCounterClockWise(), engine.forward.getOpposite()};
		for (Direction direction : candidates) {
			BlockPos front = feet.relative(direction);
			if (ascending) {
				BlockPos[] clearance = {front.above(), front.above(2)};
				if (engine.isStandable(client, front) && isRouteClearable(client, clearance)) return direction;
			} else if (isRouteClearable(client, new BlockPos[]{front, front.above()})
				&& (BorerHazards.canWalkOrFallInto(client, front)
					|| engine.shouldMine(client, front)
					|| engine.shouldMine(client, front.above())
					|| engine.shouldMine(client, front.below()))) {
				return direction;
			}
		}
		if (flying) {
			for (Direction direction : candidates) {
				BlockPos front = feet.relative(direction);
				BlockPos[] clearance = {front, front.above()};
				if (!engine.isLava(client, front) && !engine.isLava(client, front.above())
					&& isRouteClearable(client, clearance)) return direction;
			}
		}
		if (allowFlatAdvance) {
			for (Direction direction : candidates) {
				BlockPos front = feet.relative(direction);
				if (engine.isReplaceable(client, front) && engine.isReplaceable(client, front.above())
					&& engine.isStandable(client, front.below())
					&& !engine.isLava(client, front) && !engine.isLava(client, front.above())) {
					return direction;
				}
			}
		}
		return null;
	}

	/** 是否应垫临时台阶。 */
	boolean placeTemporaryStep(Minecraft client, LocalPlayer player, BlockPos feet) {
		Direction[] candidates = {engine.forward, engine.forward.getClockWise(), engine.forward.getCounterClockWise(), engine.forward.getOpposite()};
		DefaultTunnelBorerEngine.SealChoice choice = engine.place.selectSealBlock(client, player);
		if (choice == null) return false;
		for (Direction direction : candidates) {
			BlockPos step = feet.relative(direction);
			if (!engine.isReplaceable(client, step) || player.getBoundingBox().intersects(new AABB(step))) continue;
			if (!isRouteClearable(client, new BlockPos[]{step.above(), step.above(2)})) continue;
			if (!engine.place.placeAndProtect(client, player, step, choice)) continue;
			engine.forward = direction;
			engine.verticalMove = DefaultTunnelBorerEngine.VerticalMove.PREPARE;
			engine.routeIssue = "已用" + engine.place.itemLabel(choice.item()) + "补临时台阶 " + BorerText.block(step) + "，先清理头顶再上升";
			engine.status = engine.routeIssue;
			engine.overlay(client, engine.status, 0x55FFFF);
			return true;
		}
		return false;
	}

	/** 路径格是否都可挖通。 */
	private boolean isRouteClearable(Minecraft client, BlockPos[] positions) {
		for (BlockPos pos : positions) {
			BlockState state = client.level.getBlockState(pos);
			if (!state.getFluidState().isEmpty()) return false;
			if (state.isAir() || state.canBeReplaced()) continue;
			if (!engine.shouldMine(client, pos)) return false;
		}
		return true;
	}

	/**
	 * 往更高矿走、前方落差超过 1 格台阶：挖够得着的矿/挡路，垫台阶，开脚手架或飞行。
	 * 不要空站「前方落差不跳」。
	 */
	boolean handleClimbDropAscent(Minecraft client, LocalPlayer player, int dropAhead) {
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		BlockPos feet = engine.standingColumn(client, player);
		if (goal != null) engine.lockHeadingToward(feet, goal);

		boolean inReach = goal != null && engine.inMiningReach(player, goal);
		if (BorerFallPolicy.mineInReachInsteadOfWaitClimbDrop(inReach, true)) {
			BlockPos target = engine.nextOreOrObstruction(client, player, goal);
			if (target == null && engine.canPlanMine(client, goal)
				&& (engine.canSeeBlock(client, player, goal) || engine.playerTouchesBlock(player, goal))) {
				target = goal.immutable();
			}
			if (target != null) {
				engine.setMiningTarget(client, player, target, "climb-drop-in-reach");
				client.options.keyUp.setDown(false);
				client.options.keyJump.setDown(false);
				engine.status = "矿在更高处，改挖通路 " + BorerText.block(target) + BorerAim.reachInfo(player, target);
				engine.overlay(client, engine.status, 0xFFFF55);
				return true;
			}
		}

		if (placeTemporaryStep(client, player, feet)) return true;

		if (BorerFlight.ensureScaffold(true)) {
			client.options.keyShift.setDown(false);
			client.options.keyJump.setDown(player.onGround());
			client.options.keyUp.setDown(true);
			engine.attemptedForward = true;
			engine.status = "矿在更高处，已开脚手架垫路越过 " + dropAhead + " 格落差";
			engine.overlay(client, engine.status, 0x55FFFF);
			engine.fileLog(client, "climb-drop-scaffold drop=" + dropAhead
				+ " goal=" + (goal == null ? "-" : BorerText.block(goal))
				+ " player=" + BorerText.precise(player));
			return true;
		}

		if (engine.enableMeteorFlight(player)) {
			client.options.keyShift.setDown(false);
			client.options.keyJump.setDown(true);
			client.options.keyUp.setDown(true);
			engine.attemptedForward = true;
			engine.status = "矿在更高处，已开飞行越过 " + dropAhead + " 格落差";
			engine.overlay(client, engine.status, 0x55FFFF);
			return true;
		}

		BlockPos stair = goal == null ? null : nextRouteTarget(client, player, goal);
		if (stair != null) {
			engine.setMiningTarget(client, player, stair, "climb-drop-stair");
			client.options.keyUp.setDown(false);
			engine.status = "矿在更高处，改挖台阶 " + BorerText.block(stair) + BorerAim.reachInfo(player, stair);
			engine.overlay(client, engine.status, 0xFFFF55);
			return true;
		}

		client.options.keyUp.setDown(false);
		engine.status = "矿在更高处，前方落差不跳 · " + engine.oreTravelStatus(player);
		engine.overlay(client, engine.status, 0xFFFF55);
		return true;
	}

	/** 是否在往更高矿爬。 */
	boolean climbingToOre(Minecraft client, LocalPlayer player) {
		if (engine.mode != DefaultTunnelBorerEngine.Mode.ORE || player == null) return false;
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		return goal != null && goal.getY() > engine.standingColumn(client, player).getY();
	}

	/** 是否在往更低矿下。 */
	boolean descendingToOre(Minecraft client, LocalPlayer player) {
		if (engine.mode != DefaultTunnelBorerEngine.Mode.ORE || player == null) return false;
		BlockPos goal = engine.sideOreTargetPos != null ? engine.sideOreTargetPos : engine.oreTargetPos;
		return goal != null && goal.getY() < engine.standingColumn(client, player).getY();
	}

	/** 向上走时，当前列脚这一层是台阶立足点，挖掉会变成一格高的洞。前方挡路不算立足点。 */
	boolean isClimbFoothold(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (!climbingToOre(client, player) || pos == null) return false;
		BlockPos feet = engine.standingColumn(client, player);
		if (pos.getX() != feet.getX() || pos.getZ() != feet.getZ()) return false;
		return pos.getY() == feet.getY() && engine.isStandable(client, pos);
	}

	/**
	 * 准星/通道扫到立足点时改挖头顶两格；挖不到立足点本身。
	 * @return 应挖的方块；立足点且头顶已通则返回 null
	 */
	BlockPos climbTargetInsteadOfFoothold(Minecraft client, LocalPlayer player, BlockPos pos) {
		if (pos == null) return null;
		if (!isClimbFoothold(client, player, pos)) return pos.immutable();
		return firstMineableHeadroom(client, player, pos);
	}

	/** 可挖净空。 */
	BlockPos firstMineableHeadroom(Minecraft client, LocalPlayer player, BlockPos step) {
		for (BlockPos pos : new BlockPos[]{step.above(), step.above(2)}) {
			if (!engine.canPlanMine(client, pos)) continue;
			if (engine.inMiningReach(player, pos)
				&& (engine.canSeeBlock(client, player, pos) || engine.playerTouchesBlock(player, pos) || engine.hasCollision(client, pos))) {
				return pos.immutable();
			}
		}
		return null;
	}
}
