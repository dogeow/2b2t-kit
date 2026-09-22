package dev.twob2tkit.runtime.engine;

import java.util.*;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.phys.*;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class BorerVerifiedRayTest {
	private BlockPos first(Vec3 eye, Vec3 point, List<BlockPos> blocks) {
		Vec3 end = eye.add(point.subtract(eye).normalize().scale(5));
		return blocks.stream().map(p -> Map.entry(p, new AABB(p).clip(eye, end)))
			.filter(e -> e.getValue().isPresent())
			.min(Comparator.comparingDouble(e -> eye.distanceToSqr(e.getValue().orElseThrow())))
			.map(Map.Entry::getKey).orElse(null);
	}
	@Test void shallowUpwardRayKeepsTheOreInsteadOfDroppingOntoTheLowerBlock() {
		Vec3 eye = new Vec3(95216.12371235472, 48.62, 99625.49692368743);
		BlockPos ore = new BlockPos(95215, 49, 99624);
		Vec3 crossing = new AABB(ore).clip(eye, Vec3.atCenterOf(ore)).orElseThrow();
		var hit = new BlockHitResult(crossing, Direction.SOUTH, ore, false);
		var scene = List.of(ore, ore.below());
		assertEquals(ore.below(), first(eye, BorerAim.lookPoint(hit), scene), "Old face inset reproduced the reported wrong block");
		assertEquals(ore, first(eye, BorerAim.lookAlongRay(eye, hit), scene));
	}
	@Test void rayPreservationAlsoWorksAtNegativeWorldCoordinates() {
		Vec3 eye = new Vec3(-29.87628764528, 48.62, -18.50307631257);
		BlockPos ore = new BlockPos(-31, 49, -20);
		Vec3 crossing = new AABB(ore).clip(eye, Vec3.atCenterOf(ore)).orElseThrow();
		var hit = new BlockHitResult(crossing, Direction.SOUTH, ore, false);
		assertEquals(ore, first(eye, BorerAim.lookAlongRay(eye, hit), List.of(ore, ore.below())));
	}
	@Test void productionFallbackUsesTheVerifiedRayRatherThanAReclampedFacePoint() throws Exception {
		var node = new ClassNode();
		try (var in = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.class")) { new ClassReader(in).accept(node, 0); }
		var method = node.methods.stream().filter(m -> m.name.equals("lookAtMiningHit")).findFirst().orElseThrow();
		var calls = new ArrayList<String>();
		for (var insn : method.instructions) if (insn instanceof MethodInsnNode call) calls.add(call.name);
		assertTrue(calls.contains("lookAlongRay")); assertFalse(calls.contains("lookPoint"));
	}
}
