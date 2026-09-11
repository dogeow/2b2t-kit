package dev.twob2tkit.runtime.engine;

/** Remembered coordinates/mode are not permission to keep displaying a completed excavation. */
final class BorerAreaOutlinePolicy {
	static boolean visible(boolean requested, boolean areaSet, boolean anyActive, boolean activeArea,
		boolean shaftPreview, boolean returning) {
		return requested && areaSet && !shaftPreview && !returning && (!anyActive || activeArea);
	}
	private BorerAreaOutlinePolicy() {}
}
