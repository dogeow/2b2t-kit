package dev.twob2tkit.runtime.engine;

import net.minecraft.client.player.LocalPlayer;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.gizmos.TextGizmo;
import net.minecraft.world.phys.Vec3;

/** 旧主机回退：把盾构两行状态画在准星前。新主机走屏幕固定位置。 */
public final class BorerHud {
	private BorerHud() {
	}

	/** 在准星前方画两行盾构状态（旧主机回退）。 */
	public static void draw(LocalPlayer player, String action, int actionRgb, String detail) {
		if (player == null) return;
		Vec3 look = player.getViewVector(1.0F);
		Vec3 eye = player.getEyePosition();
		Vec3 worldUp = new Vec3(0.0, 1.0, 0.0);
		Vec3 right = look.cross(worldUp);
		if (right.lengthSqr() < 1.0E-6) right = new Vec3(1.0, 0.0, 0.0);
		right = right.normalize();
		Vec3 up = right.cross(look).normalize();
		Vec3 base = eye.add(look.scale(2.4)).add(up.scale(-0.52));
		drawLine(action, base, argb(actionRgb), 0.20F);
		if (detail != null && !detail.isBlank()) {
			drawLine(detail, base.add(up.scale(-0.16)), 0xFFC0C0C0, 0.16F);
		}
	}

	/** 画一行 billboard 文字。 */
	private static void drawLine(String text, Vec3 pos, int argb, float scale) {
		if (text == null || text.isBlank()) return;
		Gizmos.billboardText(text, pos, TextGizmo.Style.forColorAndCentered(argb).withScale(scale)).setAlwaysOnTop();
	}

	/** 补全不透明 alpha 的 ARGB。 */
	private static int argb(int rgb) {
		return (rgb & 0xFF000000) == 0 ? 0xFF000000 | (rgb & 0xFFFFFF) : rgb;
	}
}
