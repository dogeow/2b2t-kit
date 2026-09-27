package dev.twob2tkit;

import com.google.gson.Gson;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.game.GameProvider;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.lang.reflect.Proxy;
import java.nio.file.Path;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

class KitConfigGravelTest {
	private static final Gson GSON = new Gson();
	@TempDir static Path gameDir;

	@BeforeAll static void isolatedConfigDirectory() {
		var provider = (GameProvider) Proxy.newProxyInstance(GameProvider.class.getClassLoader(),
			new Class<?>[]{GameProvider.class}, (proxy, method, args) -> {
				if (method.getName().equals("getLaunchDirectory")) return gameDir;
				throw new AssertionError("Unexpected loader call: " + method.getName());
			});
		FabricLoaderImpl.INSTANCE.setGameProvider(provider);
		net.minecraft.SharedConstants.tryDetectVersion();
		net.minecraft.server.Bootstrap.bootStrap();
	}

	@Test
	void oldConfigWithoutGravelFieldsGetsIndependentDefaults() {
		KitConfig loaded = GSON.fromJson("{\"borerOreTarget\":\"DIAMOND,GRAVEL,IRON\"}", KitConfig.class);
		assertTrue(loaded.gravelWaterMode);
		assertEquals(48, loaded.gravelRadius);
		assertEquals(64, loaded.gravelLimit);
		assertEquals(28, loaded.gravelDepth);
		assertEquals("DIAMOND,GRAVEL,IRON", loaded.borerOreTarget);
	}

	@Test
	void boundsAndZeroLimitRoundTripWithoutChangingOreSelections() {
		KitConfig config = new KitConfig();
		config.borerOreTarget = "COAL,GRAVEL,QUARTZ";
		config.gravelWaterMode = false;
		config.gravelRadius = 64;
		config.gravelLimit = 0;
		config.gravelDepth = 32;
		KitConfig restored = GSON.fromJson(GSON.toJson(config), KitConfig.class);
		restored.normalizeGravelSettings();
		assertFalse(restored.gravelWaterMode);
		assertEquals(64, restored.gravelRadius);
		assertEquals(0, restored.gravelLimit);
		assertEquals(32, restored.gravelDepth);
		assertEquals("COAL,GRAVEL,QUARTZ", restored.borerOreTarget);
	}

	@Test
	void corruptNumbersFallBackToBoundedDefaults() {
		KitConfig config = new KitConfig();
		config.gravelRadius = 3;
		config.gravelLimit = -1;
		config.gravelDepth = 33;
		config.normalizeGravelSettings();
		assertEquals(48, config.gravelRadius);
		assertEquals(64, config.gravelLimit);
		assertEquals(28, config.gravelDepth);
	}
}
