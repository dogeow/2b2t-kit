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
import dev.twob2tkit.KitUi;
import net.minecraft.client.gui.GuiGraphicsExtractor;

/** 只指路、不接管走路：脚前画短箭头、路上铺路标、目标标一块，字幕显示方向和距离。 */
public final class StructureGuide {
	private boolean active;
	private String name = "";
	private int x;
	private int y;
	private int z;
	private boolean hasY;
	private final GuideSession session = new GuideSession();
	private String detail = "";
	private String distanceText = "";
	private float bearing;
	private long completedUntil;

	/** 是否正在指引。 */
	public String status() { return active ? name + " · " + distanceText + " · " + detail : ""; }
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
		Minecraft c = Minecraft.getInstance();
		session.start(scope(c)); completedUntil = 0;
		if (c.player != null) updateView(c.player);
	}

	/** 关掉指引。 */
	public void stop() {
		active = false; session.stop(); completedUntil = 0;
	}

	/**
	 * 每拍更新字幕：转向提示与距离；巡航/盾构/挖树运行时不抢提示。
	 */
	public void tick(Minecraft client) {
		if (!active) return;
		if (client.player == null || client.level == null || !session.matches(scope(client))) { stop(); return; }
		LocalPlayer player = client.player;
		updateView(player);
		if (session.arrived(Math.hypot(x+.5-player.getX(), z+.5-player.getZ()), hasY ? y-player.getY() : 0)) {
			active = false; session.stop(); completedUntil = System.currentTimeMillis()+2400;
			detail = "已到达";
		}
	}

	private static String scope(Minecraft c) {
		if (c.level == null) return null;
		String world = c.getCurrentServer() != null ? c.getCurrentServer().ip
			: c.getSingleplayerServer() != null ? c.getSingleplayerServer().getWorldData().getLevelName() : "local";
		return world + "|" + c.level.dimension().identifier();
	}
	private void updateView(LocalPlayer p) {
		double dx=x+.5-p.getX(), dz=z+.5-p.getZ();
		double distance = Math.hypot(dx,dz);
		float targetYaw=(float)Math.toDegrees(Math.atan2(dz,dx))-90;
		bearing=wrapDegrees(targetYaw-p.getYRot());
		String turn=Math.abs(bearing)<=12 ? "正前方" : Math.abs(bearing)>=165 ? "身后" : bearing>0 ? "右转" : "左转";
		int dy=hasY ? y-p.getBlockY() : 0;
		detail=turn+" · "+cardinal(targetYaw)+(Math.abs(dy)>2 ? " · "+(dy>0?"上":"下")+Math.abs(dy)+"格" : "");
		distanceText=GuideSession.distance(distance);
	}
	private static boolean occupied() {
		return KitClient.controller()!=null && KitClient.controller().isActive()
			|| KitClient.borer()!=null && KitClient.borer().isActive()
			|| KitClient.chopper()!=null && KitClient.chopper().isActive();
	}
	/** Compact top-centre card, away from the crosshair, hotbar and left-side minimap. */
	public void renderHud(Minecraft c, GuiGraphicsExtractor g) {
		if ((!active && System.currentTimeMillis()>completedUntil) || c.player==null || c.level==null || c.options.hideGui
			|| occupied() || c.screen!=null && !(c.screen instanceof KitHudScreen)) return;
		if (active && !session.matches(scope(c))) return;
		int width=Math.min(220,Math.max(120,g.guiWidth()-24)), left=(g.guiWidth()-width)/2, top=42;
		int accent=active?0xFF75D8C5:0xFF9AE6A3;
		g.nextStratum();
		g.fill(left,top,left+width,top+38,0xD918252C);
		g.fill(left,top,left+2,top+38,accent);
		int textLeft=left+34;
		KitUi.text(g,c.font,KitUi.fit(c.font,name,width-44-c.font.width(distanceText)),textLeft,top+7,0xF1F6F6);
		KitUi.text(g,c.font,distanceText,left+width-9-c.font.width(distanceText),top+7,0x75D8C5);
		KitUi.text(g,c.font,KitUi.fit(c.font,detail,width-44),textLeft,top+22,0xA7BDC3);
		// A small heading chevron; no font-dependent arrow glyph and no long line through the scene.
		double angle=Math.toRadians(bearing); int cx=left+18, cy=top+19;
		int tx=cx+(int)Math.round(Math.sin(angle)*7), ty=cy-(int)Math.round(Math.cos(angle)*7);
		for(int side:new int[]{-1,1}) for(int i=0;i<=8;i++) {
			double a=i/8.0; double ox=-Math.sin(angle)*7+Math.cos(angle)*side*5, oy=Math.cos(angle)*7+Math.sin(angle)*side*5;
			int px=tx+(int)Math.round(a*ox), py=ty+(int)Math.round(a*oy);
			g.fill(px,py,px+2,py+2,accent);
		}
	}

	/** 画脚前箭头、路标与目标方块（其它自动模块运行时不画）。 */
	public void render(Minecraft client) {
		if (!active || client.player == null || client.level == null || !session.matches(scope(client))) return;
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


		if (distance <= 64) {
			double destY = hasY ? y : ground.y;
			BlockPos dest = BlockPos.containing(x + 0.5, destY, z + 0.5);
			Gizmos.cuboid(dest, GizmoStyle.strokeAndFill(0xCC75D8C5, 1.2F, 0x1175D8C5));
			Gizmos.billboardText(name, Vec3.atCenterOf(dest.above()),
				TextGizmo.Style.forColorAndCentered(0xFF00E5FF).withScale(0.18F)).setAlwaysOnTop();
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
