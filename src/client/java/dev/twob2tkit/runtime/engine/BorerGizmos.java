package dev.twob2tkit.runtime.engine;

import net.minecraft.gizmos.GizmoProperties;

/**
 * 导航标记穿墙显示。不要 persistForMillis：client tick 里画的 gizmo
 * 会被 Minecraft 留到下一拍，再 persist 90ms 会和新的叠成重影。
 */
final class BorerGizmos {
	private BorerGizmos() {
	}

	/** 普通导航标记属性（不 persist）。 */
	static GizmoProperties hold(GizmoProperties gizmo) {
		return gizmo;
	}

	/** 导航标记置顶穿墙显示。 */
	static GizmoProperties holdOnTop(GizmoProperties gizmo) {
		return gizmo.setAlwaysOnTop();
	}
}
