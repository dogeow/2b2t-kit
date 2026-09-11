package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.inventory.ContainerInput;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.Vec3;

/** Bounded, server-observed lighting step at the bottom; never consumes a mining tick forever. */
final class BorerAreaTorch {
	private BlockPos target;
	private int ticks;
	static boolean needsLight(int brightness, boolean hasTorch) { return brightness < 8 && hasTorch; }
	void begin(BlockPos pos) { target = pos.immutable(); ticks = 0; }
	void reset() { target = null; ticks = 0; }
	boolean tick(Minecraft client, DefaultTunnelBorerEngine engine) {
		if (target == null) return false;
		var player = client.player;
		var inv = player.getInventory();
		int torchSlot = -1;
		for (int i = 0; i < 36; i++) if (inv.getItem(i).is(Items.TORCH)) { torchSlot = i; break; }
		int brightness = client.level.getMaxLocalRawBrightness(target);
		if (client.level.getBlockState(target).is(Blocks.TORCH) || client.level.getBlockState(target).is(Blocks.WALL_TORCH)) {
			engine.fileLog(client, "area-torch-confirmed pos=" + target);
			reset(); return false;
		}
		if (!needsLight(brightness, torchSlot >= 0) || ticks >= 12) {
			engine.fileLog(client, "area-torch-finish light=" + brightness + " hasTorch=" + (torchSlot >= 0) + " ticks=" + ticks);
			reset(); return false;
		}
		int now = ticks++;
		engine.status = "作业面光照 " + brightness + "，正在补火把";
		if (now != 0 && now != 6) return true;
		if (!client.level.getBlockState(target).isAir()) { reset(); return false; }
		for (Direction side : new Direction[]{Direction.DOWN, Direction.NORTH, Direction.SOUTH, Direction.WEST, Direction.EAST}) {
			BlockPos support = target.relative(side);
			if (client.level.getBlockState(support).getCollisionShape(client.level, support).isEmpty()) continue;
			Direction face = side.getOpposite();
			Vec3 point = Vec3.atCenterOf(support).add(face.getStepX() * 0.499, face.getStepY() * 0.499, face.getStepZ() * 0.499);
			RotationAim.apply(player, RotationAim.lookAt(player, point));
			BlockHitResult hit = BorerAim.clipView(client, player);
			if (hit == null || !support.equals(hit.getBlockPos()) || hit.getDirection() != face || !BorerAim.hitInReach(player, hit)) continue;
			int previous = inv.getSelectedSlot();
			int selected = torchSlot < 9 ? torchSlot : previous;
			if (torchSlot >= 9) client.gameMode.handleContainerInput(player.containerMenu.containerId, torchSlot, selected, ContainerInput.SWAP, player);
			inv.setSelectedSlot(selected);
			try {
				client.gameMode.useItemOn(player, InteractionHand.MAIN_HAND, hit);
				player.swing(InteractionHand.MAIN_HAND);
				engine.fileLog(client, "area-torch-place pos=" + target + " light=" + brightness);
			} finally {
				if (torchSlot >= 9) client.gameMode.handleContainerInput(player.containerMenu.containerId, torchSlot, selected, ContainerInput.SWAP, player);
				inv.setSelectedSlot(previous);
			}
			return true;
		}
		engine.fileLog(client, "area-torch-no-support pos=" + target);
		reset(); return false;
	}
}
