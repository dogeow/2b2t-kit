package dev.twob2tkit.structure;

import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.gizmos.TextGizmo;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.Vec3;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitHudScreen;

/** 只指路、不接管走路：脚前画短箭头、路上铺路标、目标标一块，字幕显示方向和距离。 */
public final class StructureGuide {
	private boolean active;
	private String name = "";
	private int x;
	private int y;
	private int z;
	private boolean hasY;

	/** 是否正在指引。 */
	public boolean isActive() {
		return active;
	}

	/** 开始水平指引（无 Y）。 */
	public void start(String name, int x, int z) {
		start(name, x, 0, z, false);
	}

	/** 开始带高度的指引。 */
	public void start(String name, int x, int y, int z) {
		start(name, x, y, z, true);
	}

	/** 写入目标并激活。 */
	private void start(String name, int x, int y, int z, boolean hasY) {
		this.active = true;
		this.name = name;
		this.x = x;
		this.y = y;
		this.z = z;
		this.hasY = hasY;
	}

	/** 关掉指引。 */
	public void stop() {
		active = false;
	}

	/**
	 * 每拍更新字幕：转向提示与距离；巡航/盾构/挖树运行时不抢提示。
	 */
	public void tick(Minecraft client) {
		if (!active || client.player == null) return;
		if (KitClient.controller() != null && KitClient.controller().isActive()) return;
		if (KitClient.borer() != null && KitClient.borer().isActive()) return;
		if (KitClient.chopper() != null && KitClient.chopper().isActive()) return;
		LocalPlayer player = client.player;
		double dx = x + 0.5 - player.getX();
		double dz = z + 0.5 - player.getZ();
		int distance = (int)Math.round(Math.hypot(dx, dz));
		int dy = hasY ? y - player.getBlockY() : 0;
		if (client.screen != null && !(client.screen instanceof KitHudScreen)) return;
		if (distance <= 8 && Math.abs(dy) <= 3) {
			overlay(client, "已到 " + name + " 附近（" + distance + " 格），可关指引", 0x55FF55);
			return;
		}
		if (distance <= 8 && hasY) {
			overlay(client, "[指引] " + name + "  水平已到，再" + (dy > 0 ? "上 " : "下 ") + Math.abs(dy) + " 格", 0x55FFFF);
			return;
		}
		float targetYaw = (float)Math.toDegrees(Math.atan2(dz, dx)) - 90.0F;
		float error = wrapDegrees(targetYaw - player.getYRot());
		String turn;
		if (Math.abs(error) <= 12.0F) turn = "正前方";
		else if (error > 0.0F) turn = "右转 " + Math.round(error) + "°";
		else turn = "左转 " + Math.round(-error) + "°";
		String height = hasY && Math.abs(dy) > 1 ? "  " + (dy > 0 ? "上" : "下") + Math.abs(dy) + "格" : "";
		overlay(client, "[指引] " + name + "  " + cardinal(targetYaw) + "  " + distance + "格" + height + "  " + turn, 0x55FFFF);
	}

	/** 画脚前箭头、路标与目标方块（其它自动模块运行时不画）。 */
	public void render(Minecraft client) {
		if (!active || client.player == null || client.level == null) return;
		if (KitClient.controller() != null && KitClient.controller().isActive()) return;
		if (KitClient.borer() != null && KitClient.borer().isActive()) return;
		if (KitClient.chopper() != null && KitClient.chopper().isActive()) return;
		LocalPlayer player = client.player;
		float partial = client.getDeltaTracker().getGameTimeDeltaPartialTick(true);
		Vec3 feet = player.getPosition(partial);
		double dx = x + 0.5 - feet.x;
		double dz = z + 0.5 - feet.z;
		int distance = (int)Math.round(Math.hypot(dx, dz));
		emitGizmos(feet, dx, dz, distance);
	}

	/** 贴地短箭头 + 沿途路标 + 近处目标框。 */
	private void emitGizmos(Vec3 ground, double dx, double dz, int distance) {
		Vec3 dir = new Vec3(dx, 0.0, dz);
		if (dir.lengthSqr() < 1.0E-4) return;
		dir = dir.normalize();

		// 贴地短箭头，不要从眼前沿视线拉一条，远看会像天线。
		Vec3 foot = new Vec3(ground.x, ground.y + 0.08, ground.z);
		Gizmos.arrow(foot.add(dir.scale(1.4)), foot.add(dir.scale(2.8)), 0xFF00E5FF, 2.0F);

		for (int i = 1; i <= 4; i++) {
			double startDist = i * 10.0;
			if (startDist + 2.5 >= distance) break;
			Vec3 head = foot.add(dir.scale(startDist));
			Vec3 tail = foot.add(dir.scale(startDist + 2.5));
			Gizmos.arrow(head, tail, 0x8800E5FF, 1.5F);
		}

		if (distance <= 256) {
			double destY = hasY ? y : ground.y;
			BlockPos dest = BlockPos.containing(x + 0.5, destY, z + 0.5);
			Gizmos.cuboid(dest, GizmoStyle.strokeAndFill(0xFF00E5FF, 2.2F, 0x3300E5FF));
			Gizmos.billboardText(name, Vec3.atCenterOf(dest.above()),
				TextGizmo.Style.forColorAndCentered(0xFF00E5FF).withScale(0.32F)).setAlwaysOnTop();
		}
	}

	/** 字幕提示。 */
	private static void overlay(Minecraft client, String text, int color) {
		client.gui.setOverlayMessage(Component.literal(text).withColor(color), false);
	}

	/** 偏航角转八方位中文。 */
	private static String cardinal(float yaw) {
		float wrapped = wrapDegrees(yaw);
		if (wrapped < 0.0F) wrapped += 360.0F;
		int sector = ((int)Math.round(wrapped / 45.0F)) & 7;
		return switch (sector) {
			case 0 -> "南";
			case 1 -> "西南";
			case 2 -> "西";
			case 3 -> "西北";
			case 4 -> "北";
			case 5 -> "东北";
			case 6 -> "东";
			default -> "东南";
		};
	}

	/** 角度归一到 (-180, 180]。 */
	private static float wrapDegrees(float degrees) {
		float result = degrees % 360.0F;
		if (result >= 180.0F) result -= 360.0F;
		if (result < -180.0F) result += 360.0F;
		return result;
	}
}
