package dev.twob2tkit.runtime.engine;

/** Shared capture gates, independent of rendering and Minecraft input. */
final class SceneryCapturePolicy {
	/** LightEngine.setLightEnabled registers a SectionPos zero-node, NOT ChunkPos.pack(). */
	static long lightColumnKey(int chunkX, int chunkZ) {
		return net.minecraft.core.SectionPos.getZeroNode(chunkX, chunkZ);
	}
	static boolean ready(boolean loaded, boolean lit, boolean sameObservation, int ageTicks) {
		return loaded && lit && sameObservation && ageTicks >= 10;
	}
	static boolean drain(int pending, int queued, boolean noTarget, boolean complete) {
		return pending >= 32 || queued > 256 || noTarget && !complete;
	}
	static final class Quiet {
		private int ticks;
		void reset() { ticks = 0; }
		boolean observe(boolean pending, boolean idle) {
			if (!pending || !idle) { ticks = 0; return false; }
			if (++ticks < 20) return false;
			ticks = 0; return true;
		}
	}
	private SceneryCapturePolicy() {}
}
