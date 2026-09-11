package dev.twob2tkit.builder;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.client.multiplayer.ClientPacketListener;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.network.chat.Component;
import net.minecraft.network.protocol.game.ServerboundPlayerInputPacket;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.InteractionResult;
import net.minecraft.world.entity.player.Input;
import net.minecraft.world.entity.player.Inventory;
import net.minecraft.world.entity.player.Player;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.Item;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.AbstractChestBlock;
import net.minecraft.world.level.block.BarrelBlock;
import net.minecraft.world.level.block.BedBlock;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.CactusBlock;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.ComparatorBlock;
import net.minecraft.world.level.block.HopperBlock;
import net.minecraft.world.level.block.ObserverBlock;
import net.minecraft.world.level.block.RepeaterBlock;
import net.minecraft.world.level.block.ShulkerBoxBlock;
import net.minecraft.world.level.block.SlabBlock;
import net.minecraft.world.level.block.piston.PistonBaseBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Property;
import net.minecraft.world.level.block.state.properties.SlabType;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

import java.util.Set;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitHudScreen;
import dev.twob2tkit.KitUi;

/** 机全息预览与自动放置（含 Litematica 导入）。 */
public final class MachineBuilder {
	private static final int PLACE_RADIUS = 5;
	private static final int WALK_RADIUS = 12;
	private static final Set<String> PLACEMENT_PROPERTIES = Set.of(
		"facing", "horizontal_facing", "axis", "half", "type", "hinge", "part", "shape",
		"face", "attachment", "rotation", "delay", "mode", "waterlogged", "open", "inverted"
	);

	public enum Kind {
		BLOCK, HOPPER, CHEST, PISTON, OBSERVER, BED, HORIZONTAL, SLAB, PLANT, WATER, LAVA
	}

	/** 待放一格：坐标与目标方块。 */
	public record Cell(BlockPos pos, Kind kind, Block block, Item item, Direction facing, BlockState expected) {
	}

	private boolean placing;
	private String placementName = "";
	private Cell current;
	private Cell approachCell;
	private int cooldown;
	private int failStreak;
	private int walkTicks;
	private int approachStuck;
	private double approachBestDist = Double.MAX_VALUE;
	private boolean settling;
	private String status = "";

	/** 按配置构造机全息/自动放置。 */
	public MachineBuilder() {
	}

	/** 是否有全息预览。 */
	public boolean hasPreview() {
		return false;
	}

	/** 是否正在自动放置。 */
	public boolean isPlacing() {
		return placing;
	}

	/** 最近状态文案。 */
	public String status() {
		return status;
	}

	/** 开始预览或放置。 */
	public boolean start(Minecraft client) {
		if (client.player == null || client.level == null) {
			status = "当前不在世界中";
			return false;
		}
		if (!LitematicaAccess.installed()) {
			status = LitematicaAccess.describe();
			message(client, status);
			return false;
		}
		if (!LitematicaAccess.hasActivePlacement()) {
			status = LitematicaAccess.describe();
			message(client, status);
			return false;
		}
		KitClient.prepareForMachine(client);
		placing = true;
		placementName = LitematicaAccess.placementName();
		cooldown = 8;
		failStreak = 0;
		clearApproach();
		status = "开始按投影建造「" + placementName + "」。只摆背包里有的，不拆已有方块。End 停止";
		message(client, status);
		overlay(client, status, 0x55FFFF);
		return true;
	}

	/** 热键开/关。 */
	public void toggle(Minecraft client) {
		if (placing) cancel(client, "按键停止建造");
		else start(client);
	}

	/** 取消预览与放置。 */
	public void cancel(Minecraft client, String reason) {
		if (!placing && current == null) return;
		boolean wasPlacing = placing;
		placing = false;
		current = null;
		clearApproach();
		if (wasPlacing) {
			releaseMove(client);
			status = "已停止建造：" + reason;
			message(client, status);
			overlay(client, status, 0xFFFF55);
		}
	}

	/** 走近并放置下一格。 */
	public void tick(Minecraft client) {
		if (!placing) return;
		if (client.player == null || client.level == null || client.gameMode == null) {
			cancel(client, "离开世界");
			return;
		}
		if (!LitematicaAccess.hasActivePlacement()) {
			cancel(client, LitematicaAccess.describe());
			return;
		}
		if (client.screen != null && !(client.screen instanceof KitHudScreen)) {
			if (closeAccidentalMenu(client)) {
				status = "已关掉误开的箱子，继续放置";
				cooldown = 2;
				return;
			}
			releaseMove(client);
			status = "请先关掉背包或其它界面";
			overlay(client, status, 0xFFFF55);
			return;
		}
		if (cooldown > 0) {
			cooldown--;
			releaseMove(client);
			return;
		}

		LocalPlayer player = client.player;
		BlockGetter schematic = LitematicaAccess.schematicWorld();
		if (schematic == null) {
			cancel(client, "投影世界消失了");
			return;
		}
		Cell cell = pickStableNext(client, player, schematic);
		current = cell;
		emitTargetGizmo(cell);
		if (cell == null) {
			releaseMove(client);
			status = "附近没有可摆的投影方块。走近全息，或检查背包和 Litematica 渲染层";
			overlay(client, status, 0xFFFF55);
			cooldown = 20;
			return;
		}

		boolean support = findSupportHit(client, cell) != null;
		if (!inReach(player, cell.pos()) || !support) {
			if (!support) {
				releaseMove(client);
				clearApproach();
				status = "这一块暂时没有可贴的面，先摆旁边的";
				overlay(client, status, 0xFFFF55);
				cooldown = 5;
				return;
			}
			double dy = Vec3.atCenterOf(cell.pos()).y - player.getY();
			double horiz = Math.hypot(cell.pos().getX() + 0.5 - player.getX(), cell.pos().getZ() + 0.5 - player.getZ());
			if (!dev.twob2tkit.runtime.engine.BorerFlight.isFlying(player) && (player.onGround() && dy > 2.4 || Math.abs(dy) > 3.2) && horiz <= 2.8) {
				releaseMove(client);
				status = "请走到或飞到 Y=" + cell.pos().getY() + "，到了会自动接着摆";
				overlay(client, status, 0xFFFF55);
				cooldown = 15;
				return;
			}
			settling = true;
			walkToward(client, player, cell.pos());
			walkTicks++;
			status = "走向 " + format(cell.pos()) + "  " + itemName(cell);
			overlay(client, status, 0xFFFF55);
			if (walkTicks > 50) {
				releaseMove(client);
				clearApproach();
				walkTicks = 0;
				cooldown = 5;
			}
			return;
		}

		releaseMove(client);
		if (settling) {
			settling = false;
			walkTicks = 0;
			cooldown = 3;
			return;
		}
		walkTicks = 0;
		InteractionHand hand = selectItem(client, cell.item());
		if (hand == null && !player.hasInfiniteMaterials()) {
			status = "缺 " + itemName(cell) + "，补进背包后自动继续";
			overlay(client, status, 0xFFFF55);
			cooldown = 20;
			return;
		}
		if (!place(client, cell, hand)) {
			failStreak++;
			status = isFluid(cell)
				? "正在倒 " + itemName(cell)
				: "正在放置 " + itemName(cell) + " @ " + format(cell.pos());
			overlay(client, status, 0xFFFF55);
			cooldown = 3;
			if (failStreak >= 25) {
				cancel(client, "连续放置失败：" + format(cell.pos()) + "。请检查朝向、支撑面和服务器限制");
			}
			return;
		}
		failStreak = 0;
		cooldown = isFluid(cell) ? 6 : 2;
		status = "已放置 " + itemName(cell) + "  " + format(cell.pos());
		overlay(client, status, 0x55FFFF);
	}

	/** 画建造 HUD。 */
	public void renderHud(Minecraft client, GuiGraphicsExtractor graphics) {
		if (!placing && !LitematicaAccess.installed()) return;
		if (client.options.hideGui) return;
		if (client.screen != null && !client.screen.isInGameUi()) return;
		if (!placing) return;
		ItemStack stack = current == null ? ItemStack.EMPTY : new ItemStack(current.item());
		String name = current == null ? "寻找可摆位置" : itemName(current);
		int have = current == null || client.player == null ? 0 : count(client.player, current.item());
		String stock = current == null ? LitematicaAccess.placementName() : (have > 0 ? "背包 " + have : "背包没有");
		int center = graphics.guiWidth() / 2;
		int y = graphics.guiHeight() / 2 + 18;
		int boxW = Math.max(client.font.width(name), client.font.width(stock)) + (stack.isEmpty() ? 16 : 36);
		int x = center - boxW / 2;
		graphics.nextStratum();
		graphics.fill(x - 4, y - 3, x + boxW + 4, y + 28, 0xC0000000);
		if (!stack.isEmpty()) graphics.item(stack, x, y + 4);
		int textX = x + (stack.isEmpty() ? 4 : 22);
		KitUi.text(graphics, client.font, name, textX, y + 2, 0xFFFFFF);
		KitUi.text(graphics, client.font, stock, textX, y + 14, have > 0 ? 0x55FF55 : 0xFF5555);
	}

	/** 稳定挑选下一格（避免抖动）。 */
	private Cell pickStableNext(Minecraft client, LocalPlayer player, BlockGetter schematic) {
		if (approachCell != null && approachStillValid(client, player, approachCell)) {
			double dist = player.distanceToSqr(Vec3.atCenterOf(approachCell.pos()));
			if (dist + 0.25 < approachBestDist) {
				approachBestDist = dist;
				approachStuck = 0;
			} else {
				approachStuck++;
			}
			if (approachStuck < 45) return approachCell;
		}
		Cell next = pickNext(client, player, schematic, PLACE_RADIUS);
		if (next == null) next = pickNext(client, player, schematic, WALK_RADIUS);
		approachCell = next;
		approachStuck = 0;
		approachBestDist = next == null ? Double.MAX_VALUE : player.distanceToSqr(Vec3.atCenterOf(next.pos()));
		return next;
	}

	/** 走近目标是否仍有效。 */
	private boolean approachStillValid(Minecraft client, LocalPlayer player, Cell cell) {
		if (!placing) return false;
		if (alreadySatisfied(client, cell)) return false;
		if (!isReplaceable(client.level.getBlockState(cell.pos()))) return false;
		if (!client.level.isUnobstructed(cell.expected(), cell.pos(), net.minecraft.world.phys.shapes.CollisionContext.placementContext(player))) return false;
		if (!hasItemFor(player, cell)) return false;
		if (!placementReady(client, cell)) return false;
		if (!LitematicaAccess.inVisibleLayer(cell.pos())) return false;
		return findSupportHit(client, cell) != null;
	}

	/** 清走近状态。 */
	private void clearApproach() {
		approachCell = null;
		approachStuck = 0;
		approachBestDist = Double.MAX_VALUE;
		settling = false;
		walkTicks = 0;
	}

	/** 半径内挑下一待放格。 */
	private Cell pickNext(Minecraft client, LocalPlayer player, BlockGetter schematic, int radius) {
		Cell best = null;
		double bestScore = Double.MAX_VALUE;
		BlockPos feet = player.blockPosition();
		for (int dy = -radius; dy <= radius; dy++) {
			for (int dx = -radius; dx <= radius; dx++) {
				for (int dz = -radius; dz <= radius; dz++) {
					if (dx * dx + dy * dy + dz * dz > radius * radius) continue;
					BlockPos pos = feet.offset(dx, dy, dz);
					if (!LitematicaAccess.inVisibleLayer(pos)) continue;
					Cell cell = cellAt(schematic, pos);
					if (cell == null) continue;
					if (alreadySatisfied(client, cell)) continue;
					if (!isReplaceable(client.level.getBlockState(pos))) continue;
					if (!client.level.isUnobstructed(cell.expected(), pos, net.minecraft.world.phys.shapes.CollisionContext.placementContext(player))) continue;
					if (!hasItemFor(player, cell)) continue;
					if (!placementReady(client, cell)) continue;
					if (findSupportHit(client, cell) == null) continue;
					double dist = player.distanceToSqr(Vec3.atCenterOf(pos));
					double score = pos.getY() * 24.0 + Math.sqrt(dist);
					if (inReach(player, pos)) score -= 10_000.0;
					else if (Math.abs(pos.getY() - player.getBlockY()) <= 2) score -= 200.0;
					// 漏斗要等输出端的箱子；台阶等脚下；甘蔗等泥土和水。
					if (cell.kind() == Kind.HOPPER) score += 80.0;
					if (cell.kind() == Kind.SLAB) score += 12.0;
					if (cell.kind() == Kind.WATER) score += 30.0;
					if (cell.kind() == Kind.PLANT) score += 400.0;
					if (score < bestScore) {
						bestScore = score;
						best = cell;
					}
				}
			}
		}
		return best;
	}

	/** 原理图坐标转 Cell。 */
	private static Cell cellAt(BlockGetter schematic, BlockPos pos) {
		BlockState state = schematic.getBlockState(pos);
		if (state.isAir() || state.is(Blocks.CAVE_AIR) || state.is(Blocks.VOID_AIR) || state.is(Blocks.STRUCTURE_VOID)) {
			return null;
		}
		Block block = state.getBlock();
		if (state.is(Blocks.MOVING_PISTON) || state.is(Blocks.PISTON_HEAD) || state.is(Blocks.FIRE)
			|| state.is(Blocks.SOUL_FIRE) || state.is(Blocks.NETHER_PORTAL) || state.is(Blocks.END_PORTAL)
			|| state.is(Blocks.END_GATEWAY) || state.is(Blocks.BARRIER) || state.is(Blocks.LIGHT)
			|| state.is(Blocks.BEDROCK)) {
			return null;
		}
		Item item = block.asItem();
		Kind kind = classify(block, state);
		if (kind == Kind.WATER) item = Items.WATER_BUCKET;
		else if (kind == Kind.LAVA) item = Items.LAVA_BUCKET;
		if (item == Items.AIR) return null;
		return new Cell(pos.immutable(), kind, block, item, facingOf(state), state);
	}

	/** 方块种类（实心/半砖等）。 */
	private static Kind classify(Block block, BlockState state) {
		if (state.getFluidState().is(Fluids.WATER) && state.getBlock() == Blocks.WATER) return Kind.WATER;
		if (state.getFluidState().is(Fluids.LAVA) && state.getBlock() == Blocks.LAVA) return Kind.LAVA;
		if (block instanceof HopperBlock) return Kind.HOPPER;
		if (block instanceof ChestBlock) return Kind.CHEST;
		if (block instanceof PistonBaseBlock) return Kind.PISTON;
		if (block instanceof ObserverBlock) return Kind.OBSERVER;
		if (block instanceof BedBlock) return Kind.BED;
		if (block instanceof ComparatorBlock || block instanceof RepeaterBlock || block instanceof net.minecraft.world.level.block.StairBlock) return Kind.HORIZONTAL;
		if (block instanceof SlabBlock) return Kind.SLAB;
		if (block == Blocks.SUGAR_CANE || block == Blocks.BAMBOO || block == Blocks.BAMBOO_SAPLING
			|| block instanceof CactusBlock) {
			return Kind.PLANT;
		}
		return Kind.BLOCK;
	}

	/** 方块朝向。 */
	private static Direction facingOf(BlockState state) {
		for (Property<?> property : state.getProperties()) {
			String name = property.getName();
			if (!name.equals("facing") && !name.equals("horizontal_facing")) continue;
			Comparable<?> value = state.getValue(property);
			if (value instanceof Direction direction) return direction;
		}
		return null;
	}

	/** 找支撑点击。 */
	private BlockHitResult findSupportHit(Minecraft client, Cell cell) {
		if (cell.kind() == Kind.HOPPER) return hopperSupport(client, cell);
		if (cell.kind() == Kind.PLANT) return plantSupport(client, cell);
		if (cell.kind() == Kind.SLAB) {
			BlockHitResult slab = slabSupport(client, cell);
			if (slab != null) return slab;
		}
		BlockPos pos = cell.pos();
		for (Direction direction : Direction.values()) {
			BlockPos neighbor = pos.relative(direction);
			if (!isReplaceable(client.level.getBlockState(neighbor))) {
				return click(neighbor, direction.getOpposite());
			}
		}
		if (dev.twob2tkit.MeteorModules.isActive("meteordevelopment.meteorclient.systems.modules.player.AirPlace") && cell.kind() != Kind.WATER && cell.kind() != Kind.LAVA) {
			Direction face = Direction.UP;
			if (cell.expected().hasProperty(net.minecraft.world.level.block.state.properties.BlockStateProperties.HALF) && cell.expected().getValue(net.minecraft.world.level.block.state.properties.BlockStateProperties.HALF) == net.minecraft.world.level.block.state.properties.Half.TOP) face = Direction.DOWN;
			return click(pos, face);
		}
		return null;
	}

	/**
	 * 甘蔗/竹子/仙人掌只能点脚下的土/沙。旁边已经摆了活塞观察者时，
	 * 旧逻辑会点那些当支撑，结果先插甘蔗、泥土还没铺。
	 */
	private BlockHitResult plantSupport(Minecraft client, Cell cell) {
		BlockPos soil = cell.pos().below();
		if (isReplaceable(client.level.getBlockState(soil))) return null;
		if (!canSurviveHere(client, cell)) return null;
		return click(soil, Direction.UP);
	}

	/** 甘蔗还要旁边有水；泥土/水没摆好就先跳过。 */
	private static boolean placementReady(Minecraft client, Cell cell) {
		if (cell.kind() == Kind.WATER || cell.kind() == Kind.LAVA) return true;
		if (cell.kind() == Kind.PLANT && isReplaceable(client.level.getBlockState(cell.pos().below()))) {
			return false;
		}
		return canSurviveHere(client, cell);
	}

	/** 目标状态是否能在此存活。 */
	private static boolean canSurviveHere(Minecraft client, Cell cell) {
		if (client.level == null) return false;
		BlockState want = cell.expected() != null ? cell.expected() : cell.block().defaultBlockState();
		try {
			return want.canSurvive(client.level, cell.pos());
		} catch (RuntimeException ignored) {
			return true;
		}
	}

	/**
	 * 水平漏斗必须点输出端那个箱子的内侧，箱子还没摆就先跳过。
	 */
	private BlockHitResult hopperSupport(Minecraft client, Cell cell) {
		Direction facing = cell.facing() == null ? Direction.DOWN : cell.facing();
		BlockPos dest = facing == Direction.DOWN ? cell.pos().below() : cell.pos().relative(facing);
		if (isReplaceable(client.level.getBlockState(dest))) return null;
		Direction clickFace = facing == Direction.DOWN ? Direction.UP : facing.getOpposite();
		return click(dest, clickFace);
	}

	/** 下台阶点脚下顶面；上台阶点头顶底面。避免点旁边泥土变成整块或错半边。 */
	private BlockHitResult slabSupport(Minecraft client, Cell cell) {
		SlabType type = slabType(cell);
		BlockPos pos = cell.pos();
		if (type == SlabType.TOP) {
			BlockPos above = pos.above();
			if (!isReplaceable(client.level.getBlockState(above))) return click(above, Direction.DOWN);
			return sideSupport(client, pos, 0.3);
		}
		BlockPos below = pos.below();
		if (!isReplaceable(client.level.getBlockState(below))) return click(below, Direction.UP);
		return sideSupport(client, pos, -0.3);
	}

	/** 半砖类型。 */
	private static SlabType slabType(Cell cell) {
		if (cell.expected() != null && cell.expected().hasProperty(SlabBlock.TYPE)) {
			return cell.expected().getValue(SlabBlock.TYPE);
		}
		return SlabType.BOTTOM;
	}

	/** 侧面支撑点击。 */
	private BlockHitResult sideSupport(Minecraft client, BlockPos pos, double yBias) {
		for (Direction direction : Direction.Plane.HORIZONTAL) {
			BlockPos neighbor = pos.relative(direction);
			if (isReplaceable(client.level.getBlockState(neighbor))) continue;
			return click(neighbor, direction.getOpposite(), yBias);
		}
		return null;
	}

	/** 走向目标格。 */
	private void walkToward(Minecraft client, LocalPlayer player, BlockPos target) {
		Vec3 dest = Vec3.atCenterOf(target);
		double dx = dest.x - player.getX();
		double dy = dest.y - player.getY();
		double dz = dest.z - player.getZ();
		double horiz = Math.hypot(dx, dz);
		float yaw = horiz > 0.04 ? RotationAim.yawToward(dx, dz) : player.getYRot();
		RotationAim.apply(player, yaw, 12.0F);

		boolean closeHoriz = horiz <= 1.35;
		boolean closeVert = Math.abs(dy) <= 1.15;
		if (closeHoriz && closeVert) {
			releaseMove(client);
			return;
		}

		client.options.keyUp.setDown(!closeHoriz && horiz > 1.15);
		if (dev.twob2tkit.runtime.engine.BorerFlight.isFlying(player)) {
			client.options.keyJump.setDown(dy > 1.2);
			client.options.keyShift.setDown(dy < -1.2);
		} else {
			client.options.keyJump.setDown(player.onGround() && closeHoriz && dy > 0.55 && dy < 1.4);
			client.options.keyShift.setDown(false);
		}
	}

	/** 松开移动键。 */
	private static void releaseMove(Minecraft client) {
		if (client.options == null) return;
		client.options.keyUp.setDown(false);
		client.options.keyJump.setDown(false);
		client.options.keyShift.setDown(false);
	}

	/** 画出当前目标。 */
	private void emitTargetGizmo(Cell cell) {
		if (cell == null) return;
		try {
			Gizmos.cuboid(cell.pos(), GizmoStyle.strokeAndFill(0xFF00FFFF, 3.0F, 0x3300FFFF));
		} catch (IllegalStateException ignored) {
		}
	}

	/** 世界已是目标状态。 */
	private boolean alreadySatisfied(Minecraft client, Cell cell) {
		BlockState state = client.level.getBlockState(cell.pos());
		return switch (cell.kind()) {
			case WATER -> state.getFluidState().is(Fluids.WATER) && state.getFluidState().isSource();
			case LAVA -> state.getFluidState().is(Fluids.LAVA) && state.getFluidState().isSource();
			default -> state.is(cell.block()) && matchesPlacementState(state, cell.expected());
		};
	}

	/** 实际与期望是否匹配。 */
	private boolean matchesPlacementState(BlockState actual, BlockState expected) {
		if (expected == null) return true;
		for (var property : expected.getProperties()) {
			if (!PLACEMENT_PROPERTIES.contains(property.getName())) continue;
			if (!actual.hasProperty(property)) return false;
			if (!actual.getValue(property).equals(expected.getValue(property))) return false;
		}
		return true;
	}

	/** 放置当前格。 */
	private boolean place(Minecraft client, Cell cell, InteractionHand hand) {
		LocalPlayer player = client.player;
		if (hand == null) {
			hand = selectItem(client, cell.item());
			if (hand == null) return false;
		}
		lookForPlacement(player, cell);
		BlockHitResult hit = findSupportHit(client, cell);
		if (hit == null) hit = hitFor(cell);
		if (hit == null) return false;
		if (cell.facing() == null) lookAt(player, hit.getLocation());
		else if (cell.facing().getAxis() != Direction.Axis.Y) {
			RotationAim.apply(player, player.getYRot(), RotationAim.lookAt(player, hit.getLocation()).pitch());
		}
		if (cell.facing() != null && !dev.twob2tkit.automation.PlacementRotation.prepare(client, player.getYRot(), player.getXRot())) return false;
		if (isFluid(cell)) {
			InteractionResult poured = client.gameMode.useItem(player, hand);
			return poured.consumesAction() || alreadySatisfied(client, cell);
		}
		boolean sneak = shouldSneakToPlace(client, cell, hit);
		InteractionResult result = sneak
			? placeWhileSneaking(client, player, hand, hit)
			: client.gameMode.useItemOn(player, hand, hit);
		if (closeAccidentalMenu(client)) {
			return alreadySatisfied(client, cell);
		}
		return result.consumesAction() || alreadySatisfied(client, cell);
	}

	/** 放置是否需要潜行。 */
	private boolean shouldSneakToPlace(Minecraft client, Cell cell, BlockHitResult hit) {
		if (cell.kind() == Kind.HOPPER) return true;
		if (client.level == null) return false;
		BlockState state = client.level.getBlockState(hit.getBlockPos());
		Block block = state.getBlock();
		if (block instanceof AbstractChestBlock<?> || block instanceof HopperBlock
			|| block instanceof BarrelBlock || block instanceof ShulkerBoxBlock) {
			return true;
		}
		return state.getMenuProvider(client.level, hit.getBlockPos()) != null;
	}

	/** 潜行放置。 */
	private InteractionResult placeWhileSneaking(Minecraft client, LocalPlayer player, InteractionHand hand, BlockHitResult hit) {
		Input previous = player.input != null ? player.input.keyPresses : Input.EMPTY;
		boolean keyWasDown = client.options.keyShift.isDown();
		Input sneakInput = new Input(
			previous.forward(), previous.backward(), previous.left(), previous.right(),
			previous.jump(), true, previous.sprint()
		);
		KitClient.setForceSneakForPlacement(true);
		client.options.keyShift.setDown(true);
		if (player.input != null) player.input.keyPresses = sneakInput;
		sendSneakInput(client, sneakInput);
		try {
			return client.gameMode.useItemOn(player, hand, hit);
		} finally {
			KitClient.setForceSneakForPlacement(false);
			client.options.keyShift.setDown(keyWasDown);
			if (player.input != null) player.input.keyPresses = previous;
			sendSneakInput(client, previous);
		}
	}

	/** 发送潜行输入。 */
	private static void sendSneakInput(Minecraft client, Input input) {
		ClientPacketListener connection = client.getConnection();
		if (connection != null) connection.send(new ServerboundPlayerInputPacket(input));
	}

	/** 误开容器则关掉。 */
	private static boolean closeAccidentalMenu(Minecraft client) {
		if (!(client.screen instanceof AbstractContainerScreen<?>) || client.player == null) return false;
		client.player.closeContainer();
		return true;
	}

	/** 是否流体格。 */
	private static boolean isFluid(Cell cell) {
		return cell.kind() == Kind.WATER || cell.kind() == Kind.LAVA;
	}

	/** 该格的放置命中。 */
	private BlockHitResult hitFor(Cell cell) {
		if (cell.kind() == Kind.HOPPER) {
			Direction facing = cell.facing() == null ? Direction.DOWN : cell.facing();
			if (facing == Direction.DOWN) return click(cell.pos().below(), Direction.UP);
			return click(cell.pos().relative(facing), facing.getOpposite());
		}
		if (cell.kind() == Kind.SLAB && slabType(cell) == SlabType.TOP) {
			return click(cell.pos().above(), Direction.DOWN);
		}
		return click(cell.pos().below(), Direction.UP);
	}

	/** 支撑面点击命中。 */
	private BlockHitResult click(BlockPos support, Direction face) {
		return click(support, face, 0.0);
	}

	/** 支撑面点击命中。 */
	private BlockHitResult click(BlockPos support, Direction face, double yBias) {
		Vec3 location = Vec3.atCenterOf(support).add(
			face.getStepX() * 0.51,
			face.getStepY() * 0.51 + yBias,
			face.getStepZ() * 0.51
		);
		return new BlockHitResult(location, face, support, false);
	}

	/** 对准放置点。 */
	private void lookForPlacement(LocalPlayer player, Cell cell) {
		Direction look = switch (cell.kind()) {
			case PISTON, CHEST -> cell.facing() == null ? null : cell.facing().getOpposite();
			case OBSERVER, BED, HORIZONTAL -> cell.facing();
			case HOPPER -> cell.facing() == null || cell.facing() == Direction.DOWN ? Direction.DOWN : cell.facing();
			default -> null;
		};
		if (look == null || look.getAxis() == Direction.Axis.Y) {
			if (look == Direction.DOWN) RotationAim.apply(player, player.getYRot(), 90.0F);
			else if (look == Direction.UP) RotationAim.apply(player, player.getYRot(), -90.0F);
			else lookAt(player, cell.pos().below());
			if (cell.kind() == Kind.OBSERVER && cell.facing() == Direction.DOWN) RotationAim.apply(player, player.getYRot(), 90.0F);
			return;
		}
		RotationAim.apply(player, yaw(look), 0.0F);
	}

	/** 瞬间对准。 */
	private void lookAt(LocalPlayer player, BlockPos pos) {
		lookAt(player, Vec3.atCenterOf(pos));
	}

	/** 瞬间对准。 */
	private void lookAt(LocalPlayer player, Vec3 target) {
		RotationAim.apply(player, RotationAim.lookAt(player, target));
	}

	/** 朝向对应 yaw。 */
	private static float yaw(Direction direction) {
		return switch (direction) {
			case SOUTH -> 0.0F;
			case WEST -> 90.0F;
			case NORTH -> 180.0F;
			case EAST -> -90.0F;
			default -> 0.0F;
		};
	}

	/** 换成指定物品。 */
	private InteractionHand selectItem(Minecraft client, Item item) {
		LocalPlayer player = client.player;
		if (player.getMainHandItem().is(item)) return InteractionHand.MAIN_HAND;
		if (player.getOffhandItem().is(item)) return InteractionHand.OFF_HAND;
		if (player.hasInfiniteMaterials()) {
			ItemStack stack = new ItemStack(item);
			if (stack.isEmpty()) return null;
			int slot = player.getInventory().getSelectedSlot();
			player.getInventory().setItem(slot, stack.copy());
			client.gameMode.handleCreativeModeItemAdd(stack.copy(), 36 + slot);
			return InteractionHand.MAIN_HAND;
		}
		Inventory inventory = player.getInventory();
		for (int slot = 0; slot < 9; slot++) {
			if (inventory.getItem(slot).is(item)) {
				inventory.setSelectedSlot(slot);
				return InteractionHand.MAIN_HAND;
			}
		}
		for (int slot = 9; slot < 36; slot++) {
			if (!inventory.getItem(slot).is(item)) continue;
			client.gameMode.handleContainerInput(player.containerMenu.containerId, slot, inventory.getSelectedSlot(), ContainerInput.SWAP, player);
			if (player.getMainHandItem().is(item) || inventory.getItem(inventory.getSelectedSlot()).is(item)) {
				return InteractionHand.MAIN_HAND;
			}
		}
		return null;
	}

	/** 是否有该格所需物品。 */
	private static boolean hasItemFor(Player player, Cell cell) {
		return player.hasInfiniteMaterials() || count(player, cell.item()) > 0;
	}

	/** 背包物品数量。 */
	public static int count(Player player, Item item) {
		int total = 0;
		for (ItemStack stack : player.getInventory().getNonEquipmentItems()) {
			if (stack.is(item)) total += stack.getCount();
		}
		ItemStack offhand = player.getOffhandItem();
		if (offhand.is(item)) total += offhand.getCount();
		return total;
	}

	/** 是否够得着。 */
	private static boolean inReach(LocalPlayer player, BlockPos pos) {
		double range = Math.max(2.5, player.blockInteractionRange() - 0.35);
		return player.getEyePosition().distanceToSqr(Vec3.atCenterOf(pos)) <= range * range;
	}

	/** 是否可替换。 */
	private static boolean isReplaceable(BlockState state) {
		return state.isAir() || state.canBeReplaced()
			|| !state.getFluidState().isEmpty() && state.getFluidState().createLegacyBlock().is(state.getBlock());
	}

	/** 格子物品显示名。 */
	private static String itemName(Cell cell) {
		ItemStack stack = new ItemStack(cell.item());
		return stack.isEmpty() ? BuiltInRegistries.BLOCK.getKey(cell.block()).getPath() : stack.getHoverName().getString();
	}

	/** 坐标短字符串。 */
	private static String format(BlockPos pos) {
		return pos.getX() + " " + pos.getY() + " " + pos.getZ();
	}

	/** 叠字幕。 */
	private static void overlay(Minecraft client, String text, int color) {
		if (client.gui != null) {
			client.gui.setOverlayMessage(Component.literal("[投影建造] " + text).withColor(color), false);
		}
	}

	/** 发系统消息。 */
	private static void message(Minecraft client, String text) {
		if (client.player != null) client.player.sendSystemMessage(Component.literal("[投影建造] " + text));
	}
}
