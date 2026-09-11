package dev.twob2tkit.borer;

import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.network.chat.Component;
import net.minecraft.world.phys.BlockHitResult;
import net.minecraft.world.phys.HitResult;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;

/** 区域挖两个对角：准星、左键或输入坐标。 */
public final class BorerAreaMarks {
	/** 准星取点最远距离（格）。 */
	public static final int PICK_RANGE = 128;
	/** 区域水平边长上限。 */
	public static final int MAX_SPAN = 64;

	private BorerAreaMarks() {
	}

	/** 已标点则返回 {@code x y z}，否则空串。 */
	public static String format(boolean set, int x, int y, int z) {
		return set ? x + " " + y + " " + z : "";
	}

	/** 解析空格/逗号分隔的三维整数坐标到 {@code out}。 */
	public static boolean parse(String raw, int[] out) {
		if (raw == null || out == null || out.length < 3) return false;
		String text = raw.trim().replace(',', ' ');
		if (text.isEmpty()) return false;
		String[] parts = text.split("\\s+");
		if (parts.length < 3) return false;
		try {
			out[0] = Integer.parseInt(parts[0]);
			out[1] = Integer.parseInt(parts[1]);
			out[2] = Integer.parseInt(parts[2]);
			return true;
		} catch (NumberFormatException ignored) {
			return false;
		}
	}

	/** 写入点 A，清空当前工程绑定并存盘。 */
	public static void setA(KitConfig config, BlockPos pos) {
		config.borerAreaDraft = null;
		config.borerAreaAx = pos.getX();
		config.borerAreaAy = pos.getY();
		config.borerAreaAz = pos.getZ();
		config.borerAreaASet = true;
		config.activeAreaProjectId = "";
		config.save();
	}

	/** 写入点 B，清空当前工程绑定并存盘。 */
	public static void setB(KitConfig config, BlockPos pos) {
		config.borerAreaDraft = null;
		config.borerAreaBx = pos.getX();
		config.borerAreaBy = pos.getY();
		config.borerAreaBz = pos.getZ();
		config.borerAreaBSet = true;
		config.activeAreaProjectId = "";
		config.save();
	}

	/** 从文本设置点 A；解析失败返回 false。 */
	public static boolean applyA(KitConfig config, String raw) {
		int[] xyz = new int[3];
		if (!parse(raw, xyz)) return false;
		setA(config, new BlockPos(xyz[0], xyz[1], xyz[2]));
		return true;
	}

	/** 从文本设置点 B；解析失败返回 false。 */
	public static boolean applyB(KitConfig config, String raw) {
		int[] xyz = new int[3];
		if (!parse(raw, xyz)) return false;
		setB(config, new BlockPos(xyz[0], xyz[1], xyz[2]));
		return true;
	}

	/** 清空 A/B 与工程绑定，并关掉区域预览。 */
	public static void clear(KitConfig config) {
		config.borerAreaDraft = null;
		config.borerAreaASet = false;
		config.borerAreaBSet = false;
		config.activeAreaProjectId = "";
		config.save();
		KitClient.dismissAreaPreview();
	}

	/** 准星打到的方块；没有则 null。 */
	public static BlockPos lookBlock(Minecraft client) {
		if (client == null || client.player == null || client.level == null) return null;
		HitResult hit = client.player.pick(PICK_RANGE, 1.0F, false);
		if (hit instanceof BlockHitResult block && block.getType() == HitResult.Type.BLOCK) {
			return block.getBlockPos();
		}
		return null;
	}

	/** 以脚底为中心、朝向为正前，标出 n×n 水平对角。 */
	public static void sizeFromFeet(KitConfig config, BlockPos feet, Direction heading, int size) {
		int n = Math.max(1, Math.min(MAX_SPAN, size));
		Direction forward = heading.getAxis() == Direction.Axis.Y ? Direction.SOUTH : heading;
		Direction right = forward.getClockWise();
		int start = -((n - 1) / 2);
		int end = start + n - 1;
		setA(config, feet.relative(right, start).relative(forward, start));
		setB(config, feet.relative(right, end).relative(forward, end));
	}

	/** 区域尺寸/高度一句话说明（界面用）。 */
	public static String sizeLabel(KitConfig config) {
		if (!config.borerAreaASet || !config.borerAreaBSet) {
			if (config.borerAreaASet) return "已标点A，再标点B";
			if (config.borerAreaBSet) return "已标点B，再标点A";
			return "未标区域";
		}
		int wide = Math.abs(config.borerAreaAx - config.borerAreaBx) + 1;
		int along = Math.abs(config.borerAreaAz - config.borerAreaBz) + 1;
		if (wide > MAX_SPAN || along > MAX_SPAN) return wide + "×" + along + " 太大，最大 " + MAX_SPAN + "×" + MAX_SPAN;
		if (config.borerAreaAy != config.borerAreaBy) {
			int top = Math.max(config.borerAreaAy, config.borerAreaBy);
			int bottom = Math.min(config.borerAreaAy, config.borerAreaBy);
			return wide + "×" + along + "  Y " + top + "→" + bottom;
		}
		return wide + "×" + along + "  Y " + config.borerAreaAy + " 往下";
	}

	/** 聊天系统消息（带 twob2tkit 前缀）。 */
	public static void tell(Minecraft client, String text) {
		if (client != null && client.player != null) {
			client.player.sendSystemMessage(Component.literal("[twob2tkit] " + text).withColor(0x55FFFF));
		}
	}
}
