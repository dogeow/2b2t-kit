package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.BorerHost;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import java.lang.reflect.Proxy;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaOutlineTest {
	@org.junit.jupiter.api.BeforeAll static void bootstrapMinecraftRegistries() {
		net.minecraft.SharedConstants.tryDetectVersion(); net.minecraft.server.Bootstrap.bootStrap();
	}
	@Test void savedAreaDoesNotShowByItselfAfterReloadOrRestart() {
		var calls = new ArrayList<String>(); var engine = engine(calls);
		assertEquals("AREA", engine.host.borerLastMode()); assertTrue(engine.host.borerAreaSet());
		assertFalse(engine.areaOutlineVisible);
		assertFalse(BorerAreaOutlinePolicy.visible(engine.areaOutlineVisible, true, false, false, false, false));
	}
	@Test void hideChangesOnlyVisibilityAndPreservesActivePlanCoordinatesAndTargets() throws Exception {
		var calls = new ArrayList<String>(); var engine = engine(calls);
		engine.active = true; engine.mode = DefaultTunnelBorerEngine.Mode.AREA;
		engine.areaMin = new BlockPos(760864, -59, 797792); engine.areaMax = new BlockPos(760879, -50, 797807);
		engine.areaWalkTarget = engine.areaMin.above(); engine.areaShaftColumn = engine.areaMin;
		engine.currentTarget = engine.areaMin.above(2); engine.areaRelocating = true;
		engine.areaOutlineVisible = engine.showingAreaPreview = true;
		var plan = new BorerAreaPlan(engine.areaMin, engine.areaMax, new BorerAreaPlan.Pose(760864.5, -51, 797792.5, 0, 0, 0));
		var field = BorerAreaRunner.class.getDeclaredField("plan"); field.setAccessible(true); field.set(engine.areaRunner, plan);
		engine.dismissAreaPreview(); engine.dismissAreaPreview();
		assertFalse(engine.areaOutlineVisible); assertFalse(engine.showingAreaPreview);
		assertTrue(engine.active); assertTrue(engine.areaRelocating); assertSame(plan, field.get(engine.areaRunner));
		assertEquals(new BlockPos(760864, -59, 797792), engine.areaMin);
		assertEquals(new BlockPos(760879, -50, 797807), engine.areaMax);
		assertEquals(engine.areaMin.above(), engine.areaWalkTarget); assertEquals(engine.areaMin, engine.areaShaftColumn);
		assertEquals(engine.areaMin.above(2), engine.currentTarget); assertTrue(calls.isEmpty(), "Hiding must not save, clear or rewrite host settings");
	}
	@Test void showDuringMiningDoesNotReloadBoundsResetProgressOrRequireAClient() {
		var calls = new ArrayList<String>(); var engine = engine(calls);
		engine.active = true; engine.mode = DefaultTunnelBorerEngine.Mode.AREA;
		engine.areaMin = new BlockPos(1, 2, 3); engine.areaMax = new BlockPos(4, 5, 6);
		engine.currentTarget = engine.areaMin;
		engine.previewArea(null);
		assertTrue(engine.areaOutlineVisible); assertTrue(engine.active); assertEquals(engine.areaMin, engine.currentTarget);
		assertEquals(new BlockPos(4, 5, 6), engine.areaMax); assertTrue(calls.isEmpty());
		engine.dismissAreaPreview(); assertFalse(engine.areaOutlineVisible);
	}
	@Test void explicitDisplayWorksOnlyForConfiguredIdleOrActiveAreaNotOtherBorerModes() {
		assertTrue(BorerAreaOutlinePolicy.visible(true, true, false, false, false, false));
		assertTrue(BorerAreaOutlinePolicy.visible(true, true, true, true, false, false));
		assertFalse(BorerAreaOutlinePolicy.visible(false, true, true, true, false, false));
		assertFalse(BorerAreaOutlinePolicy.visible(true, false, false, false, false, false));
		assertFalse(BorerAreaOutlinePolicy.visible(true, true, true, false, false, false));
		assertFalse(BorerAreaOutlinePolicy.visible(true, true, false, false, true, false));
		assertFalse(BorerAreaOutlinePolicy.visible(true, true, true, true, false, true));
	}
	private static DefaultTunnelBorerEngine engine(List<String> calls) {
		BorerHost host = (BorerHost)Proxy.newProxyInstance(BorerHost.class.getClassLoader(), new Class<?>[]{BorerHost.class}, (proxy, method, args) -> {
			calls.add(method.getName());
			if (method.getName().equals("borerLastMode")) return "AREA";
			if (method.getName().equals("borerAreaSet")) return true;
			throw new AssertionError("Unexpected host mutation/access: " + method.getName());
		});
		return new DefaultTunnelBorerEngine(host);
	}
}
