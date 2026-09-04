package dev.twob2tkit;

import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.network.chat.Component;

import java.util.ArrayList;
import java.util.List;
import java.util.Locale;

/** 界面工具：颜色、数字解析、传送坐标、换行与裁切文字。 */
public final class KitUi {
	private KitUi() {
	}

	/** RGB 转不透明 ARGB。 */
	public static int argb(int rgb) {
		return 0xFF000000 | (rgb & 0xFFFFFF);
	}

	/** 整数则无小数位，否则保留两位。 */
	public static String formatNumber(double value) {
		if (value == Math.rint(value)) return Long.toString((long)value);
		return String.format(Locale.ROOT, "%.2f", value);
	}

	/** 从输入框解析 double，越界或非法则抛中文 IllegalArgumentException。 */
	public static double parse(EditBox field, String name, double minimum, double maximum) {
		final double value;
		try {
			value = Double.parseDouble(field.getValue().trim());
		} catch (NumberFormatException exception) {
			throw new IllegalArgumentException(name + " 不是有效数字");
		}
		if (!Double.isFinite(value) || value < minimum || value > maximum) {
			throw new IllegalArgumentException(String.format(Locale.ROOT, "%s 必须在 %.0f 到 %.0f 之间", name, minimum, maximum));
		}
		return value;
	}

	/** 从输入框解析 int，越界或非法则抛中文 IllegalArgumentException。 */
	public static int parseInt(EditBox field, String name, int minimum, int maximum) {
		final int value;
		try {
			value = Integer.parseInt(field.getValue().trim());
		} catch (NumberFormatException exception) {
			throw new IllegalArgumentException(name + " 不是有效整数");
		}
		if (value < minimum || value > maximum) {
			throw new IllegalArgumentException(name + " 必须在 " + minimum + " 到 " + maximum + " 之间");
		}
		return value;
	}

	/** 静默解析；失败返回 null。 */
	public static Double tryParse(EditBox field, double minimum, double maximum) {
		try {
			return parse(field, "value", minimum, maximum);
		} catch (RuntimeException ignored) {
			return null;
		}
	}

	/** 解析 Chunkbase / 原版传送文本，如 {@code /tp 382832 ~ 311344}。 */
	public static TeleportCoords parseTeleport(String raw) {
		if (raw == null) return null;
		String text = raw.trim();
		if (text.isEmpty()) return null;
		text = text.replace('\u00a0', ' ').replace(',', ' ');
		text = text.replaceAll("(?i)^/?(?:execute\\s+in\\s+\\S+\\s+run\\s+)", "");
		text = text.replaceAll("(?i)^/?(?:tp|teleport)\\b\\s*", "");
		text = text.replaceAll("(?i)^@(?:s|p|a|r|e)\\b\\s*", "");
		text = text.replaceAll("[()\\[\\]]", " ");
		java.util.ArrayList<String> tokens = new java.util.ArrayList<>();
		for (String part : text.trim().split("\\s+")) {
			if (part.isEmpty()) continue;
			if (part.equalsIgnoreCase("x") || part.equalsIgnoreCase("y") || part.equalsIgnoreCase("z")) continue;
			if (part.endsWith(":") || part.endsWith("=")) continue;
			if (part.startsWith("x:") || part.startsWith("X:")) part = part.substring(2);
			if (part.startsWith("y:") || part.startsWith("Y:")) part = part.substring(2);
			if (part.startsWith("z:") || part.startsWith("Z:")) part = part.substring(2);
			if (isCoordToken(part)) tokens.add(part);
		}
		if (tokens.size() < 2) return null;
		Double x = parseAbsolute(tokens.get(0));
		Double y;
		double z;
		if (tokens.size() >= 3) {
			y = parseAbsolute(tokens.get(1));
			z = parseAbsoluteOrNaN(tokens.get(2));
		} else {
			y = null;
			z = parseAbsoluteOrNaN(tokens.get(1));
		}
		if (x == null || Double.isNaN(z)) return null;
		if (Math.abs(x) > 30_000_000.0 || Math.abs(z) > 30_000_000.0) return null;
		if (y != null && (y < -64.0 || y > 2048.0)) y = null;
		return new TeleportCoords(x, y, z);
	}

	/** 粗判是否像可粘贴的传送/坐标文本。 */
	public static boolean looksLikeTeleport(String raw) {
		if (raw == null) return false;
		String text = raw.trim();
		if (text.length() < 3) return false;
		return text.startsWith("/") || text.toLowerCase(Locale.ROOT).contains("tp")
			|| text.contains("~") || text.contains(",") || text.split("\\s+").length >= 2;
	}

	/** 是否为绝对坐标 token（含 ~）。 */
	private static boolean isCoordToken(String part) {
		if (part.startsWith("~")) return true;
		try {
			Double.parseDouble(part);
			return true;
		} catch (NumberFormatException ignored) {
			return false;
		}
	}

	/** 解析绝对数；相对坐标 ~ 返回 null。 */
	private static Double parseAbsolute(String token) {
		if (token.startsWith("~")) return null;
		try {
			double value = Double.parseDouble(token);
			return Double.isFinite(value) ? value : null;
		} catch (NumberFormatException ignored) {
			return null;
		}
	}

	/** 相对坐标时返回 NaN。 */
	private static double parseAbsoluteOrNaN(String token) {
		Double value = parseAbsolute(token);
		return value == null ? Double.NaN : value;
	}

	/** 解析出的绝对 X、可选 Y、绝对 Z。 */
	public record TeleportCoords(double x, Double y, double z) {
	}

	/** 建带初值的 EditBox。 */
	public static EditBox field(Font font, int x, int y, int width, String narration, String value, int maxLength) {
		EditBox box = new EditBox(font, x, y, width, 20, Component.literal(narration));
		box.setMaxLength(maxLength);
		box.setValue(value);
		return box;
	}

	/** 居中画一行文字。 */
	public static void centered(GuiGraphicsExtractor graphics, Font font, String text, int centerX, int y, int rgb) {
		if (text == null || text.isEmpty()) return;
		graphics.centeredText(font, text, centerX, y, argb(rgb));
	}

	/** 左对齐画一行文字。 */
	public static void text(GuiGraphicsExtractor graphics, Font font, String value, int x, int y, int rgb) {
		if (value == null || value.isEmpty()) return;
		graphics.text(font, value, x, y, argb(rgb));
	}

	/** 按像素宽换行，优先在顿号/空格等处分断。 */
	public static List<String> wrap(Font font, String text, int maxWidth) {
		List<String> lines = new ArrayList<>();
		if (text == null || text.isEmpty() || maxWidth <= 0) return lines;
		String remaining = text.trim();
		while (!remaining.isEmpty()) {
			if (font.width(remaining) <= maxWidth) {
				lines.add(remaining);
				break;
			}
			int cut = remaining.length();
			while (cut > 1 && font.width(remaining.substring(0, cut)) > maxWidth) cut--;
			int breakAt = remaining.lastIndexOf('、', cut);
			if (breakAt < 4) breakAt = remaining.lastIndexOf('·', cut);
			if (breakAt < 4) breakAt = remaining.lastIndexOf(' ', cut);
			if (breakAt < 4) breakAt = remaining.lastIndexOf('|', cut);
			if (breakAt < 4) breakAt = cut;
			String line = remaining.substring(0, breakAt).trim();
			if (line.endsWith("·")) line = line.substring(0, line.length() - 1).trim();
			if (!line.isEmpty()) lines.add(line);
			remaining = remaining.substring(breakAt).trim();
			if (remaining.startsWith("·")) remaining = remaining.substring(1).trim();
		}
		return lines;
	}

	/** 居中多行换行文字，返回下一行可用 y。 */
	public static int centeredWrapped(GuiGraphicsExtractor graphics, Font font, String text, int center, int y, int color, int maxWidth) {
		if (text == null || text.isBlank()) return y;
		for (String line : wrap(font, text, maxWidth)) {
			centered(graphics, font, line, center, y, color);
			y += 12;
		}
		return y;
	}

	/** 超宽则截断并加省略号。 */
	public static String fit(Font font, String text, int maxWidth) {
		if (text == null || text.isEmpty()) return "";
		if (font.width(text) <= maxWidth) return text;
		String ellipsis = "…";
		int budget = maxWidth - font.width(ellipsis);
		if (budget <= 0) return ellipsis;
		String prefix = text;
		while (!prefix.isEmpty() && font.width(prefix) > budget) {
			prefix = prefix.substring(0, prefix.length() - 1);
		}
		return prefix.isEmpty() ? ellipsis : prefix + ellipsis;
	}

	/** 是否像合法 Minecraft 玩家名（1–16、无空格）。 */
	public static boolean isMinecraftName(String name) {
		return !name.isEmpty() && name.length() <= 16 && !name.contains(" ");
	}
}
