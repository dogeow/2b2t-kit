package dev.twob2tkit.runtime.engine;

import net.minecraft.world.level.Level;
import net.minecraft.world.level.chunk.LevelChunk;
import java.util.function.Supplier;

/** Capture backend. Bobby is preferred when installed, including systems where Voxy cannot start. */
interface SceneryCache {
	String connect(Level level);
	String name();
	void check();
	boolean accept(LevelChunk chunk);
	boolean idle();
	int queued();
	default boolean isReal(LevelChunk chunk) { return chunk != null; }
	default void batchCommitted() {}
	default void close() {}
	static SceneryCache create() {
		boolean bobby;
		try { Class.forName("de.johni0702.minecraft.bobby.Bobby"); bobby = true; }
		catch (ClassNotFoundException absent) { bobby = false; }
		return select(bobby, SceneryBobby::new, SceneryVoxy::new);
	}
	static SceneryCache select(boolean bobbyPresent, Supplier<SceneryCache> bobby, Supplier<SceneryCache> voxy) {
		return (bobbyPresent ? bobby : voxy).get();
	}
}
