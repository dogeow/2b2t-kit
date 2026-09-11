package dev.twob2tkit.runtime.engine;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.item.BlockItem;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.AABB;
import java.util.Objects;

/** Seal the reachable SIDE water cell while preserving the dry barrier in the intended passage. */
final class BorerAreaWater {
	private final DefaultTunnelBorerEngine engine;
	private BlockPos water, barrier, batchBarrier;
	private Block expected;
	private int previousSlot = -1, selectedSlot = -1, batchSeals;
	private BorerWaterSealPolicy transaction;
	private String failure = "";
	BorerAreaWater(DefaultTunnelBorerEngine engine) { this.engine = engine; }
	boolean active() { return water != null; }
	String failure() { return failure; }
	BlockPos water() { return water; }
	BlockPos barrier() { return barrier; }
	boolean observedSolid(Minecraft c) { return expected != null && water != null && c.level.getBlockState(water).is(expected); }
	BlockPos candidate(Minecraft c, BlockPos target) {
		if (!engine.host.borerSealLiquids() || BorerHazards.lavaOpenedByMining(c, target) != null) return null;
		for (Direction d : Direction.Plane.HORIZONTAL) {
			BlockPos pos = target.relative(d);
			if (valid(c, target, pos)) return pos;
		}
		return null;
	}
	private boolean valid(Minecraft c, BlockPos target, BlockPos pos) {
		return c.level.hasChunkAt(pos) && c.level.getBlockState(pos).is(Blocks.WATER)
			&& BorerWaterSealPolicy.sideCell(target, pos, c.player.blockPosition())
			&& !new AABB(pos).intersects(c.player.getBoundingBox().inflate(.05))
			&& c.level.getBlockEntity(pos) == null
			&& !c.player.blockActionRestricted(c.level, pos, c.gameMode.getPlayerMode())
			&& BorerAim.inReach(c.player, pos);
	}
	void begin(Minecraft c, BlockPos target, BlockPos pos) {
		if (!Objects.equals(target, batchBarrier)) { batchBarrier = target.immutable(); batchSeals = 0; }
		if (++batchSeals > 8) throw new IllegalStateException("侧水持续回流，已保留挡水块；请检查水源，不继续反复放挖");
		barrier = target.immutable(); water = pos.immutable(); expected = null; failure = "";
		previousSlot = c.player.getInventory().getSelectedSlot(); transaction = new BorerWaterSealPolicy();
		engine.fileLog(c, "area-water-start barrier=" + barrier + " side=" + water);
	}
	BorerWaterSealPolicy.Action tick(Minecraft c) {
		boolean stone = expected != null && c.level.getBlockState(water).is(expected);
		boolean supplies = stone;
		for (var item : BorerItems.SEAL_ITEMS) if (item instanceof BlockItem && BorerItems.countItem(c.player, item) > 0) { supplies = true; break; }
		boolean reachable = BorerAim.inReach(c.player, water);
		if (!stone && !valid(c, barrier, water)) {
			failure = "侧水位置改变、不可放置或够不着，保留原挡水块";
			return BorerWaterSealPolicy.Action.FAIL;
		}
		if (BorerHazards.lavaOpenedByMining(c, barrier) != null) {
			failure = "挡块旁还有岩浆，未继续开路"; return BorerWaterSealPolicy.Action.FAIL;
		}
		var action = transaction.step(c.level.getBlockState(water).is(Blocks.WATER), stone, reachable, supplies);
		if (action == BorerWaterSealPolicy.Action.PLACE) {
			var choice = engine.place.selectSealBlock(c, c.player);
			if (choice == null) { failure = "背包没有封水石料，保留挡水块"; return BorerWaterSealPolicy.Action.FAIL; }
			expected = choice.block();
			selectedSlot = c.player.getInventory().getSelectedSlot();
			engine.clearMiningTarget(c, "seal-side-water"); // Placement must aim at the water/support, not the old mining target.
			boolean accepted = engine.place.placeSideWater(c, c.player, water, choice);
			engine.fileLog(c, "area-water-place side=" + water + " attempt=" + transaction.attempts() + " accepted=" + accepted);
		} else if (action == BorerWaterSealPolicy.Action.FAIL) {
			failure = !supplies ? "背包没有封水石料，保留挡水块" : "侧水封堵未确认（可能受服务器限制），保留挡水块";
		}
		return action;
	}
	void end(Minecraft c) {
		if (c != null && c.player != null && previousSlot >= 0 && c.player.getInventory().getSelectedSlot() == selectedSlot)
			c.player.getInventory().setSelectedSlot(previousSlot);
		water = barrier = null; expected = null; transaction = null; previousSlot = selectedSlot = -1;
	}
	void reset(Minecraft c) { end(c); batchBarrier = null; batchSeals = 0; }
}
