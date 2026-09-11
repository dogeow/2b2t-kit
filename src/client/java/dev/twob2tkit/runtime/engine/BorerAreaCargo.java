package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.inventory.AbstractContainerScreen;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.component.DataComponents;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.network.protocol.game.ServerboundMovePlayerPacket;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.inventory.ChestMenu;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.ItemStack;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.ChestBlock;
import net.minecraft.world.level.block.state.properties.ChestType;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;
import java.util.*;
import static dev.twob2tkit.runtime.engine.BorerAreaPlan.*;

/** Worksite inventory handling. Deposit only; never loot unrelated containers or store equipment. */
final class BorerAreaCargo {
	private final DefaultTunnelBorerEngine engine;
	private BorerCargoTrip trip;
	private final BorerCargoModules modules = new BorerCargoModules();
	private BorerCargoDepots depots;
	private BlockPos depot;
	private boolean discard, store, placed, dropDone, openRequested, placeRequested;
	private ChestMenu ownedMenu;
	private int wait, clickCooldown, serviceTicks, sentFromMenu, transferSlot, droppedSlot = -1, droppedCount, dropWait;
	private String transferId;
	private ItemStack transferStack;
	private BorerCargoTransfer transfer;
	private String failure;
	private final Set<String> movedIds = new HashSet<>();
	private Map<String, Integer> expectedBag, expectedChest;
	private boolean auditPending, audited;
	private Pose originPose;
	private final Set<BlockPos> rejectedDepots = new HashSet<>();
	private String selectionFailure = "";
	private record DepotChoice(BlockPos pos, boolean existing, BorerCargoRouting.Route route) {}
	BorerAreaCargo(DefaultTunnelBorerEngine engine) { this.engine = engine; }
	boolean active() { return trip != null; }
	BlockPos storageBlock() { return store && placed ? depot : null; }
	String stamp() { return !active() ? "idle" : trip.stage() + ":" + depot + ":" + serviceTicks; }

	boolean shouldStart(Minecraft c) {
		try { discard = engine.host.borerAreaDiscardStone(); store = engine.host.borerAreaStoreDrops(); }
		catch (LinkageError oldHost) { discard = store = false; }
		return (discard || store) && BorerCargoPolicy.nearFull(BorerItems.emptySlots(c.player.getInventory()));
	}
	void start(Minecraft c, String world, BlockPos min, BlockPos max) throws java.io.IOException {
		if (!c.player.containerMenu.getCarried().isEmpty() || c.player.containerMenu != c.player.inventoryMenu)
			throw new IllegalStateException("请先放回鼠标上的物品并关闭容器");
		if ((!discard || next(c, true) < 0) && (!store || next(c, false) < 0))
			throw new IllegalStateException("背包快满，但没有可处理的挖矿产物；工具和补给不会被扔掉，请手动整理");
		depots = new BorerCargoDepots(c.gameDirectory.toPath().resolve("config/twob2tkit/area-depots.json"), world, min, max);
		originPose = pose(c); rejectedDepots.clear();
		DepotChoice choice = chooseDepot(c, min, max);
		if (choice == null) throw new IllegalStateException(selectionFailure);
		depot = choice.pos(); placed = choice.existing();
		if (store && !placed && findChest(c) < 0) throw new IllegalStateException("请先带上普通箱子，或暂时关闭自动存箱，只开启丢石料");
		dropDone = !discard;
		trip = new BorerCargoTrip(originPose, depot, choice.route());
		serviceTicks = wait = clickCooldown = 0; failure = null;
		placeRequested = false; droppedSlot = -1;
		movedIds.clear(); audited = auditPending = false;
		modules.acquire();
		engine.fileLog(c, "area-cargo-start free=" + BorerItems.emptySlots(c.player.getInventory()) + " drop=" + discard + " store=" + store
			+ " depot=" + depot + " existing=" + placed + " here=" + choice.route().here() + " stance=" + choice.route().service() + " travelY=" + choice.route().travelY());
	}
	Command tick(Minecraft c, World world, BlockPos min, BlockPos max) throws java.io.IOException {
		if (failure != null) return blocked(c, failure);
		try { if (!engine.host.borerAreaDiscardStone()) dropDone = true; store &= engine.host.borerAreaStoreDrops(); }
		catch (LinkageError oldHost) { dropDone = true; store = false; }
		if (trip.stage() != BorerCargoTrip.Stage.SERVICE) {
			Command travel = trip.step(world, pose(c));
			if (travel.action() == Action.BLOCKED) {
				engine.fileLog(c, "area-cargo-route-blocked depot=" + depot + " blocker=" + travel.block() + " stage=" + trip.stage() + " player=" + pose(c));
				rejectedDepots.add(depot);
				DepotChoice alternative = rejectedDepots.size() < 8 ? chooseDepot(c, min, max) : null;
				if (alternative != null) { setDepot(alternative); return Command.waitAt(pose(c), "原卸货路线变化，改用另一处可达箱子 / 放箱位置"); }
			}
			return travel;
		}
		if (++serviceTicks > 2400) return blocked(c, "卸货超过两分钟，已停挖，请检查箱子和网络");
		if (!dropDone) {
			if (discard(c, min, max)) return Command.waitAt(pose(c), "在区域外朝外丢弃普通石料（保留封水备用块）");
			dropDone = true;
		}
		if (!auditPending && (!store || transfer == null && next(c, false) < 0)) {
			if (needsAudit()) beginAudit(c); else finishService(c);
			return Command.waitAt(pose(c), auditPending ? "重新开箱核对服务器实际存入结果" : "背包已整理，返回原井");
		}
		if (!placed) return place(c);
		if (!c.level.getBlockState(depot).is(Blocks.CHEST)) return blocked(c, "本工程的卸货箱已不存在，请重新开始选择新位置");
		if (ownedMenu == null) {
			if (openRequested && c.player.containerMenu instanceof ChestMenu menu && menu.containerId != sentFromMenu
				&& c.screen instanceof AbstractContainerScreen<?> screen && screen.getMenu() == menu) {
				ownedMenu = menu; wait = 0;
				if (depots.sites().stream().noneMatch(s -> s.pos().equals(depot))) depots.remember(depot, false);
			} else {
				if (c.screen != null) return blocked(c, "打开了非卸货界面，已停止自动存箱");
				if (++wait > 60) return blocked(c, "卸货箱无法打开（可能被保护或上方遮挡），未丢弃矿物");
				if (wait == 1 || wait == 30) {
					if (!clickBlock(c, depot, false)) return blocked(c, "卸货箱准星被挡，未操作其它方块");
					sentFromMenu = c.player.inventoryMenu.containerId; openRequested = true;
				}
				return Command.waitAt(pose(c), "打开本工程的卸货箱");
			}
		}
		if (!ownsScreen(c)) return blocked(c, "卸货箱已关闭，停止存放以免操作其它界面");
		if (!ownedMenu.getCarried().isEmpty()) return blocked(c, "鼠标上有物品，请放回后再继续");
		if (auditPending) {
			for (String item : movedIds) if (!BorerCargoTransfer.audited(expectedBag.get(item), expectedChest.get(item), bagCount(c, item), chestCount(item)))
				return blocked(c, "重新开箱复核不一致，服务器未确认全部存入；已停挖保留物品");
			auditPending = false; audited = true;
			rememberCapacity(c);
			engine.fileLog(c, "area-cargo-audit-confirmed chest=" + depot + " items=" + movedIds);
			return Command.waitAt(pose(c), "服务器箱子内容已复核，准备继续");
		}
		if (transfer != null) {
			var result = transfer.observe(count(c.player.getInventory().getItem(transferSlot), transferId), chestCount(transferStack));
			if (result == BorerCargoTransfer.Result.WAIT) return Command.waitAt(pose(c), "等待箱子确认存入");
			if (result == BorerCargoTransfer.Result.REFUSED) return blocked(c, "存箱未确认，可能被插件拦截；保留背包和工程进度");
			engine.fileLog(c, "area-cargo-move-settled item=" + transferId + " chest=" + depot);
			transfer = null;
		}
		int slot = next(c, false);
		if (slot < 0) { if (needsAudit()) beginAudit(c); else finishService(c); return Command.waitAt(pose(c), "本批存入结束，核对后返回原井"); }
		slot = next(c, false, i -> chestFits(c.player.getInventory().getItem(i)));
		if (slot < 0) {
			if (needsAudit()) { beginAudit(c); return Command.waitAt(pose(c), "箱满前先核对本批已存物品"); }
			rememberCapacity(c);
			rejectedDepots.add(depot);
			BlockPos otherHalf = otherHalf(c, depot);
			if (otherHalf != null) rejectedDepots.add(otherHalf);
			pause(c);
			DepotChoice next = chooseDepot(c, min, max);
			if (next == null) return blocked(c, selectionFailure);
			setDepot(next);
			return Command.waitAt(pose(c), next.existing() ? "当前箱装不下本批剩余物品，改用另一已有箱子" : "已有可用箱均已检查，前往安全位置放备用箱子");
		}
		ItemStack stack = c.player.getInventory().getItem(slot);
		for (var menuSlot : ownedMenu.slots) if (menuSlot.container == c.player.getInventory() && menuSlot.getContainerSlot() == slot) {
			transferSlot = slot; transferId = id(stack); transferStack = stack.copy();
			transfer = new BorerCargoTransfer(stack.getCount(), chestCount(stack));
			movedIds.add(transferId); audited = false;
			c.gameMode.handleContainerInput(ownedMenu.containerId, menuSlot.index, 0, ContainerInput.QUICK_MOVE, c.player);
			return Command.waitAt(pose(c), "批量存入矿物和石料，工具与补给留在身上");
		}
		return blocked(c, "无法识别箱子背包槽，未移动物品");
	}
	boolean finished() { return trip != null && trip.stage() == BorerCargoTrip.Stage.DONE; }
	private void setDepot(DepotChoice next) {
		depot = next.pos(); placed = next.existing(); placeRequested = false;
		movedIds.clear(); audited = auditPending = false; wait = 0;
		trip.retarget(depot, next.route());
	}
	private boolean needsAudit() { return !audited && !movedIds.isEmpty() && ownedMenu != null; }
	private void beginAudit(Minecraft c) {
		captureAudit(c);
		pause(c);
	}
	private void captureAudit(Minecraft c) {
		expectedBag = new HashMap<>(); expectedChest = new HashMap<>();
		for (String id : movedIds) { expectedBag.put(id, bagCount(c, id)); expectedChest.put(id, chestCount(id)); }
		auditPending = true;
	}
	void reset(Minecraft c) {
		if (placeRequested && depots != null && depot != null && c != null && c.level != null && c.level.getBlockState(depot).is(Blocks.CHEST)) {
			try { if (depots.sites().stream().noneMatch(s -> s.pos().equals(depot))) depots.remember(depot, false); }
			catch (java.io.IOException e) { engine.fileLog(c, "area-cargo-record-failed " + e.getMessage()); }
		}
		pause(c); modules.close(); trip = null; depots = null; failure = null; droppedSlot = -1;
	}
	void pause(Minecraft c) {
		if (!auditPending && needsAudit() && c != null && c.player != null) captureAudit(c);
		if (ownedMenu != null && c != null && c.player != null && c.player.containerMenu == ownedMenu && ownedMenu.getCarried().isEmpty()) c.player.closeContainer();
		ownedMenu = null; openRequested = false; transfer = null; wait = 0;
	}
	boolean ownsScreen(Minecraft c) {
		return active() && c.player != null && c.screen instanceof AbstractContainerScreen<?> s && c.player.containerMenu == s.getMenu()
			&& (ownedMenu != null ? s.getMenu() == ownedMenu : openRequested && s.getMenu() instanceof ChestMenu
				&& s.getMenu().containerId != sentFromMenu);
	}
	private void finishService(Minecraft c) {
		pause(c);
		if (BorerCargoPolicy.nearFull(BorerItems.emptySlots(c.player.getInventory()))) {
			failure = "保留的工具或补给仍占满背包，请手动整理后继续"; return;
		}
		trip.returnToWork();
		engine.fileLog(c, "area-cargo-return free=" + BorerItems.emptySlots(c.player.getInventory()));
	}
	private Command place(Minecraft c) throws java.io.IOException {
		if (placeRequested && c.level.getBlockState(depot).is(Blocks.CHEST)) {
			depots.remember(depot, false); placed = true; wait = 0;
			engine.fileLog(c, "area-cargo-chest-placed pos=" + depot);
			DefaultTunnelBorerEngine.message(c, "已在工地安全位置放置卸货箱：" + BorerText.block(depot));
			return Command.waitAt(pose(c), "卸货箱已放置");
		}
		if (++wait > 60) return blocked(c, "箱子放置未确认，请检查领地权限或准备平台");
		if (wait != 1) return Command.waitAt(pose(c), "等待服务器确认箱子放置");
		if (!c.level.getBlockState(depot).isAir()) return blocked(c, "放箱位置被占用，不使用来源不明的箱子");
		int source = findChest(c);
		if (source < 0) return blocked(c, "请携带普通箱子，卸货时会在工地安全位置自动放置");
		int previous = c.player.getInventory().getSelectedSlot(), selected = source < 9 ? source : previous;
		if (source >= 9) c.gameMode.handleContainerInput(c.player.inventoryMenu.containerId, source, selected, ContainerInput.SWAP, c.player);
		c.player.getInventory().setSelectedSlot(selected);
		try {
			if (!clickBlock(c, depot.below(), true)) return blocked(c, "放箱支撑面被挡，未隔墙放置");
			placeRequested = true;
		}
		finally {
			if (source >= 9) c.gameMode.handleContainerInput(c.player.inventoryMenu.containerId, source, selected, ContainerInput.SWAP, c.player);
			c.player.getInventory().setSelectedSlot(previous);
		}
		return Command.waitAt(pose(c), "在工地安全位置放置卸货箱");
	}
	private boolean clickBlock(Minecraft c, BlockPos target, boolean top) {
		BlockHitResult visible = top ? null : BorerAim.visibleHit(c, c.player, target, ignored -> false);
		if (!top && visible == null) return false;
		RotationAim.apply(c.player, RotationAim.lookAt(c.player, top ? Vec3.atCenterOf(target).add(0, .49, 0)
			: BorerAim.lookAlongRay(c.player.getEyePosition(), visible)));
		var hit = BorerAim.clipView(c, c.player);
		if (hit == null || !hit.getBlockPos().equals(target) || top && hit.getDirection() != Direction.UP || !BorerAim.hitInReach(c.player, hit)) return false;
		c.gameMode.useItemOn(c.player, InteractionHand.MAIN_HAND, hit);
		return true;
	}
	private boolean discard(Minecraft c, BlockPos min, BlockPos max) {
		if (--clickCooldown > 0) return true;
		if (droppedSlot >= 0) {
			if (c.player.getInventory().getItem(droppedSlot).getCount() >= droppedCount) {
				if (++dropWait >= 40) failure = "丢弃石料未被确认，已停挖避免循环";
				return true;
			}
			droppedSlot = -1;
		}
		int slot = next(c, true); if (slot < 0) return false;
		if (!BorerCargoPolicy.outside(c.player.blockPosition().getX(), c.player.blockPosition().getZ(), min.getX(), min.getZ(), max.getX(), max.getZ())) {
			failure = "尚未到区域外，禁止丢弃石料"; return true;
		}
		Direction out = depot.getX() <= min.getX() - 4 ? Direction.WEST : depot.getX() >= max.getX() + 4 ? Direction.EAST
			: depot.getZ() <= min.getZ() - 4 ? Direction.NORTH : Direction.SOUTH;
		for (int d = 1; d <= 3; d++) if (!c.level.getBlockState(c.player.blockPosition().above().relative(out, d)).isAir()) {
			failure = "丢弃方向被挡，未扔石料以免弹回区域"; return true;
		}
		if (c.player.containerMenu != c.player.inventoryMenu || !c.player.containerMenu.getCarried().isEmpty()) { failure = "请先关闭容器并放回鼠标物品"; return true; }
		float yaw = out.toYRot();
		RotationAim.apply(c.player, yaw, -15);
		c.player.connection.send(new ServerboundMovePlayerPacket.Rot(yaw, -15, c.player.onGround(), c.player.horizontalCollision));
		droppedSlot = slot; droppedCount = c.player.getInventory().getItem(slot).getCount();
		dropWait = 0;
		engine.fileLog(c, "area-cargo-discard-request item=" + id(c.player.getInventory().getItem(slot)) + " count=" + droppedCount + " outside=" + c.player.blockPosition());
		c.gameMode.handleContainerInput(c.player.inventoryMenu.containerId, slot < 9 ? slot + 36 : slot, 1, ContainerInput.THROW, c.player);
		clickCooldown = 8;
		return true;
	}
	private DepotChoice chooseDepot(Minecraft c, BlockPos min, BlockPos max) {
		Map<BlockPos, Cell> cache = new HashMap<>();
		World w = p -> cache.computeIfAbsent(p, b -> {
			if (b.getY() < c.level.getMinY() || b.getY() >= c.level.getMaxY()) return Cell.PROTECTED;
			if (!c.level.hasChunkAt(b)) return Cell.UNLOADED;
			var state = c.level.getBlockState(b);
			if (state.isAir() || state.is(Blocks.TORCH) || state.is(Blocks.WALL_TORCH)) return Cell.AIR;
			return !state.getFluidState().isEmpty() ? Cell.LIQUID : Cell.SOLID;
		});
		Set<BlockPos> full = new HashSet<>(rejectedDepots);
		Set<String> cargo = new HashSet<>();
		List<BorerCargoPolicy.Stack> bag = bag(c);
		boolean[] keep = BorerCargoPolicy.reserved(bag);
		for (int i = 0; i < bag.size(); i++) if (!keep[i] && BorerCargoPolicy.material(bag.get(i).id())) cargo.add(bag.get(i).id());
		for (var site : depots.sites()) if (!site.acceptsAny(cargo)) full.add(site.pos());
		Set<BlockPos> known = new HashSet<>();
		for (var site : depots.sites()) known.add(site.pos());
		int unloaded = 0;
		if (store) {
			// Loaded chunk block entities cover ALL Y levels without scanning hundreds of thousands of air blocks.
			for (int cx = (min.getX() - 6) >> 4; cx <= (max.getX() + 6) >> 4; cx++)
				for (int cz = (min.getZ() - 6) >> 4; cz <= (max.getZ() + 6) >> 4; cz++) {
					var chunk = c.level.getChunkSource().getChunk(cx, cz, net.minecraft.world.level.chunk.status.ChunkStatus.FULL, false);
					if (chunk == null) { unloaded++; continue; }
					for (BlockPos p : chunk.getBlockEntities().keySet()) addChest(c, known, p, min, max);
				}
			List<BlockPos> chests = new ArrayList<>(known);
			chests.removeIf(p -> full.contains(p) || full.contains(otherHalf(c, p)));
			chests.sort(Comparator.comparingDouble(p -> c.player.distanceToSqr(Vec3.atCenterOf(p))));
			engine.fileLog(c, "area-cargo-search allLoadedY=true bounds=" + min + ".." + max + " player=" + pose(c)
				+ " found=" + known.size() + " capacityOrRejected=" + (known.size() - chests.size()) + " unloadedChunks=" + unloaded + " carriedChest=" + (findChest(c) >= 0));
			for (BlockPos chest : chests) {
				if (!chestUsable(c, chest, min, max)) continue;
				Pose here = pose(c);
				if (serviceAllowed(here, min, max) && BorerAim.visibleHit(c, c.player, chest, ignored -> false) != null) {
					var route = BorerCargoRouting.choose(w, here, originPose, here, max.getY());
					if (route != null) return chosen(c, chest, true, route);
				}
			}
			for (BlockPos chest : chests) {
				if (!chestUsable(c, chest, min, max)) { engine.fileLog(c, "area-cargo-reject chest=" + chest + " reason=missing-or-lid-blocked"); continue; }
				for (Pose stance : BorerCargoSites.stances(chest)) {
					if (!serviceAllowed(stance, min, max) || !canSeeFrom(c, stance, chest) || !BorerCargoRouting.clear(w, stance, stance)) continue;
					var route = BorerCargoRouting.choose(w, pose(c), originPose, stance, max.getY());
					if (route != null) return chosen(c, chest, true, route);
				}
				engine.fileLog(c, "area-cargo-reject chest=" + chest + " reason=no-safe-stance-or-round-trip");
			}
		}
		if (store && findChest(c) < 0) { selectionFailure = "已有工地箱均满、不可达或尚未加载，且背包没有普通箱子；请携带备用箱子"; return null; }
		List<BlockPos> candidates = BorerCargoSites.columns(min, max, pose(c), discard);
		int supports = 0;
		for (int y : BorerCargoSites.heights(pose(c), min, max, c.level.getMinY(), c.level.getMaxY(), known)) for (BlockPos xz : candidates) {
			BlockPos p = new BlockPos(xz.getX(), y, xz.getZ());
			if (full.contains(p) || !c.level.hasChunkAt(p) || !c.level.getBlockState(p).isAir() || !c.level.getBlockState(p.above()).isAir()
				|| c.player.blockActionRestricted(c.level, p, c.gameMode.getPlayerMode())) continue;
			var support = c.level.getBlockState(p.below());
			if (!support.getFluidState().isEmpty() || c.level.getBlockEntity(p.below()) != null || support.getMenuProvider(c.level, p.below()) != null
				|| support.is(Blocks.MAGMA_BLOCK) || !support.isFaceSturdy(c.level, p.below(), Direction.UP)) continue;
			boolean adjacentChest = false;
			for (Direction d : Direction.Plane.HORIZONTAL) if (c.level.getBlockState(p.relative(d)).is(Blocks.CHEST) || c.level.getBlockState(p.relative(d)).is(Blocks.TRAPPED_CHEST)) adjacentChest = true;
			if (adjacentChest) continue;
			supports++;
			List<Pose> stances = new ArrayList<>();
			stances.add(BorerCargoRouting.pose(p.getX() + .5, p.getY() + 1.25, p.getZ() + .5));
			stances.addAll(BorerCargoSites.stances(p));
			World afterPlacement = b -> store && b.equals(p) ? Cell.PROTECTED : w.cell(b);
			for (Pose stance : stances) {
				if (!serviceAllowed(stance, min, max) || !BorerCargoRouting.clear(afterPlacement, stance, stance)
					|| store && !canPlaceFrom(c, stance, p.below())) continue;
				var route = BorerCargoRouting.choose(afterPlacement, pose(c), originPose, stance, max.getY());
				if (route != null) return chosen(c, p, false, route);
			}
		}
		selectionFailure = "已有工地箱不可用；已检查井底、工地边缘和旧箱高度，但没有安全支撑、视线与往返路线"
			+ (unloaded > 0 ? "（部分区块尚未加载）" : "") + "；未丢弃矿物，请清出放箱空间后继续";
		engine.fileLog(c, "area-cargo-search-failed known=" + known.size() + " rejected=" + full.size() + " supports=" + supports + " unloadedChunks=" + unloaded);
		return null;
	}
	private DepotChoice chosen(Minecraft c, BlockPos chest, boolean existing, BorerCargoRouting.Route route) {
		engine.fileLog(c, "area-cargo-choice kind=" + (existing ? "existing" : "new-placement") + " pos=" + chest
			+ " stance=" + route.service() + " travelY=" + route.travelY() + " here=" + route.here());
		return new DepotChoice(chest, existing, route);
	}
	private boolean serviceAllowed(Pose p, BlockPos min, BlockPos max) {
		return !discard || outside(BlockPos.containing(p.x(), p.y(), p.z()), min, max);
	}
	private static void addChest(Minecraft c, Set<BlockPos> found, BlockPos p, BlockPos min, BlockPos max) {
		if (BorerCargoRouting.worksiteChest(p, min, max) && c.level.hasChunkAt(p) && c.level.getBlockState(p).is(Blocks.CHEST)) found.add(p.immutable());
	}
	private static BlockPos otherHalf(Minecraft c, BlockPos chest) {
		var state = c.level.getBlockState(chest);
		if (!state.is(Blocks.CHEST) || state.getValue(ChestBlock.TYPE) == ChestType.SINGLE) return null;
		BlockPos other = chest.relative(ChestBlock.getConnectedDirection(state));
		return c.level.getBlockState(other).is(Blocks.CHEST) ? other : null;
	}
	private static boolean chestUsable(Minecraft c, BlockPos p, BlockPos min, BlockPos max) {
		if (!BorerCargoRouting.worksiteChest(p, min, max) || !c.level.hasChunkAt(p) || !c.level.getBlockState(p).is(Blocks.CHEST)
			|| !c.level.getBlockState(p).getFluidState().isEmpty() || c.level.getBlockState(p.above()).isRedstoneConductor(c.level, p.above())) return false;
		BlockPos other = otherHalf(c, p);
		return other == null || !c.level.getBlockState(other.above()).isRedstoneConductor(c.level, other.above());
	}
	private static boolean canSeeFrom(Minecraft c, Pose stance, BlockPos chest) {
		Vec3 eye = new Vec3(stance.x(), stance.y() + c.player.getEyeHeight(), stance.z());
		var hit = c.level.clip(new ClipContext(eye, Vec3.atCenterOf(chest), ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, c.player));
		return hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK && hit.getBlockPos().equals(chest)
			&& eye.distanceTo(hit.getLocation()) <= BorerAim.breakReach(c.player);
	}
	private static boolean canPlaceFrom(Minecraft c, Pose stance, BlockPos support) {
		Vec3 eye = new Vec3(stance.x(), stance.y() + c.player.getEyeHeight(), stance.z());
		var hit = c.level.clip(new ClipContext(eye, Vec3.atCenterOf(support).add(0, .49, 0), ClipContext.Block.OUTLINE, ClipContext.Fluid.NONE, c.player));
		return hit.getType() == net.minecraft.world.phys.HitResult.Type.BLOCK && hit.getBlockPos().equals(support)
			&& hit.getDirection() == Direction.UP && eye.distanceTo(hit.getLocation()) <= BorerAim.breakReach(c.player);
	}
	private static boolean outside(BlockPos p, BlockPos min, BlockPos max) { return BorerCargoPolicy.outside(p.getX(), p.getZ(), min.getX(), min.getZ(), max.getX(), max.getZ()); }
	private int findChest(Minecraft c) {
		for (int i = 0; i < 36; i++) if (c.player.getInventory().getItem(i).is(Items.CHEST) && !special(c.player.getInventory().getItem(i))) return i;
		return -1;
	}
	private int next(Minecraft c, boolean drop) {
		return next(c, drop, i -> true);
	}
	private int next(Minecraft c, boolean drop, java.util.function.IntPredicate fits) {
		return BorerCargoPolicy.next(bag(c), drop, fits);
	}
	private List<BorerCargoPolicy.Stack> bag(Minecraft c) {
		List<BorerCargoPolicy.Stack> stacks = new ArrayList<>();
		for (int i = 0; i < 36; i++) { ItemStack s = c.player.getInventory().getItem(i); stacks.add(new BorerCargoPolicy.Stack(id(s), s.getCount(), special(s))); }
		return stacks;
	}
	private void rememberCapacity(Minecraft c) throws java.io.IOException {
		List<BorerCargoCapacity.Slot> slots = new ArrayList<>();
		for (int i = 0; i < ownedMenu.getRowCount() * 9; i++) {
			var slot = ownedMenu.getSlot(i); ItemStack stack = slot.getItem();
			slots.add(new BorerCargoCapacity.Slot(id(stack), stack.getCount(), slot.getMaxStackSize(stack), !special(stack) && slot.mayPlace(stack)));
		}
		BorerCargoCapacity capacity = BorerCargoCapacity.of(slots);
		depots.remember(depot, capacity.full(), capacity.accepts());
		BlockPos half = otherHalf(c, depot);
		if (half != null) depots.remember(half, capacity.full(), capacity.accepts());
		engine.fileLog(c, "area-cargo-capacity chest=" + depot + " otherHalf=" + half + " full=" + capacity.full() + " accepts=" + capacity.accepts());
	}
	private static boolean special(ItemStack s) { return s.isDamageableItem() || s.isEnchanted() || s.has(DataComponents.CUSTOM_NAME)
		|| s.has(DataComponents.CUSTOM_DATA) || s.has(DataComponents.CUSTOM_MODEL_DATA); }
	private static String id(ItemStack s) { return BuiltInRegistries.ITEM.getKey(s.getItem()).toString(); }
	private static int count(ItemStack s, String id) { return id(s).equals(id) ? s.getCount() : 0; }
	private int chestCount(ItemStack item) {
		int count = 0;
		for (int i = 0; i < ownedMenu.getRowCount() * 9; i++) { ItemStack s = ownedMenu.getSlot(i).getItem(); if (ItemStack.isSameItemSameComponents(s, item)) count += s.getCount(); }
		return count;
	}
	private int chestCount(String item) {
		int count = 0;
		for (int i = 0; i < ownedMenu.getRowCount() * 9; i++) count += count(ownedMenu.getSlot(i).getItem(), item);
		return count;
	}
	private int bagCount(Minecraft c, String item) {
		int count = 0;
		for (int i = 0; i < 36; i++) count += count(c.player.getInventory().getItem(i), item);
		return count;
	}
	private boolean chestFits(ItemStack item) {
		for (int i = 0; i < ownedMenu.getRowCount() * 9; i++) {
			var slot = ownedMenu.getSlot(i); ItemStack s = slot.getItem();
			if (slot.mayPlace(item) && (s.isEmpty() || ItemStack.isSameItemSameComponents(s, item) && s.getCount() < slot.getMaxStackSize(item))) return true;
		}
		return false;
	}
	private Command blocked(Minecraft c, String why) { failure = why; return new Command(Action.BLOCKED, depot, c.player.getX(), c.player.getY(), c.player.getZ(), why); }
	private static Pose pose(Minecraft c) { var p = c.player; var v = p.getDeltaMovement(); return new Pose(p.getX(), p.getY(), p.getZ(), v.x, v.y, v.z); }
}
