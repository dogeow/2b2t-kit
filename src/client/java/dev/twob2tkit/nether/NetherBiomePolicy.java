package dev.twob2tkit.nether;

/**
 * 下界群系搜索网格。只改这一处。
 * <p>
 * 附近结构原先只有要塞/堡垒。诡异森林等是群系，按种子采样噪声，
 * 相近采样点合成一块，列出离人最近的几片。
 */
public final class NetherBiomePolicy {
	public static final int SAMPLE_STEP = 32;
	public static final int CLUSTER = 192;
	public static final int SAMPLE_Y = 64;

	private NetherBiomePolicy() {
	}

	/** 方块坐标转到四分之一格（噪声采样用）。 */
	public static int quart(int block) {
		return block >> 2;
	}

	/** 采样高度：贴地板/贴顶时钳到安全层，否则用人所在 Y。 */
	public static int sampleY(int originY) {
		if (originY < 16) return 32;
		if (originY > 120) return 96;
		return originY;
	}

	/** 两采样点距离够远才算新的一片群系。 */
	public static boolean newPatch(int dx, int dz) {
		return (long) dx * dx + (long) dz * dz >= (long) CLUSTER * CLUSTER;
	}
}
