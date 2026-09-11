package dev.twob2tkit.runtime.engine;

import net.minecraft.nbt.CompoundTag;
import net.minecraft.nbt.ListTag;
import net.minecraft.world.level.Level;
import net.minecraft.world.level.chunk.LevelChunk;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class SceneryBobbyTest {
	static class Cache implements SceneryCache {
		public String connect(Level world) { return "test"; } public String name() { return "test"; }
		public void check() {} public boolean accept(LevelChunk chunk) { return true; }
		public boolean idle() { return true; } public int queued() { return 0; }
	}
	@Test void installedBobbyDoesNotEvenConstructUnsupportedVoxy() {
		var bobby = new Cache();
		assertSame(bobby, SceneryCache.select(true, () -> bobby, () -> { throw new AssertionError("Must not initialize Voxy on this Mac"); }));
	}
	@Test void voxyRemainsOptionalWhenBobbyIsAbsent() {
		var voxy = new Cache();
		assertSame(voxy, SceneryCache.select(false, () -> { throw new AssertionError(); }, () -> voxy));
	}
	@Test void parsesNativeBobbyCoordinatesFreshnessLightAndChunkSections() {
		var tag = new CompoundTag(); tag.putInt("xPos", -12); tag.putInt("zPos", 38); tag.putLong("age", 125);
		tag.putBoolean("isLightOn", true); tag.put("sections", new ListTag()); tag.putString("Status", "full"); tag.putInt("DataVersion", 5000);
		assertEquals(new SceneryBobbyBatch.Saved(-12, 38, 125, true), SceneryBobby.saved(tag));
		tag.putBoolean("isLightOn", false); assertFalse(SceneryBobby.saved(tag).complete());
		tag.putBoolean("isLightOn", true); tag.putString("sections", "corrupt"); assertFalse(SceneryBobby.saved(tag).complete());
	}
	@Test void incompleteNbtDoesNotLookLikeAValidOriginChunk() {
		var saved = SceneryBobby.saved(new CompoundTag()); assertFalse(saved.complete());
		assertEquals(Integer.MIN_VALUE, saved.x()); assertEquals(Long.MIN_VALUE, saved.age());
	}
}
