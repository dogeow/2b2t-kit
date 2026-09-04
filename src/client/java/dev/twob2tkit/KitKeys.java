package dev.twob2tkit;

import com.mojang.blaze3d.platform.InputConstants;
import net.fabricmc.fabric.api.client.keymapping.v1.KeyMappingHelper;
import net.minecraft.client.KeyMapping;
import net.minecraft.client.Minecraft;
import net.minecraft.client.input.KeyEvent;
import net.minecraft.client.input.MouseButtonEvent;
import net.minecraft.resources.Identifier;
import org.lwjgl.glfw.GLFW;

/** twob2tkit 热键：注册、匹配、物理按下检测与绑定改写。 */
public final class KitKeys {
	private static final KeyMapping.Category CATEGORY = KeyMapping.Category.register(Identifier.fromNamespaceAndPath(KitClient.MOD_ID, "controls"));

	public static final KeyMapping OPEN_GUI = new KeyMapping("key.twob2tkit.open_gui", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_U, CATEGORY);
	public static final KeyMapping EMERGENCY_STOP = new KeyMapping("key.twob2tkit.emergency_stop", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_END, CATEGORY);
	public static final KeyMapping START_STOP = new KeyMapping("key.twob2tkit.start_stop", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_G, CATEGORY);
	public static final KeyMapping TOGGLE_BORER = new KeyMapping("key.twob2tkit.toggle_borer", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_B, CATEGORY);
	public static final KeyMapping BORER_HOME = new KeyMapping("key.twob2tkit.borer_home", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_H, CATEGORY);
	public static final KeyMapping PORTAL_HOME = new KeyMapping("key.twob2tkit.portal_home", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_P, CATEGORY);
	public static final KeyMapping TOGGLE_SURROUND = new KeyMapping("key.twob2tkit.toggle_surround", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_V, CATEGORY);
	public static final KeyMapping TOGGLE_FEEDER = new KeyMapping("key.twob2tkit.toggle_feeder", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_N, CATEGORY);
	public static final KeyMapping TOGGLE_PLANTER = new KeyMapping("key.twob2tkit.toggle_planter", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_J, CATEGORY);
	public static final KeyMapping TOGGLE_CHOPPER = new KeyMapping("key.twob2tkit.toggle_chopper", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_K, CATEGORY);
	public static final KeyMapping TOGGLE_FISHER = new KeyMapping("key.twob2tkit.toggle_fisher", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_UNKNOWN, CATEGORY);
	public static final KeyMapping TOGGLE_VILLAGER_SCAN = new KeyMapping("key.twob2tkit.toggle_villager_scan", InputConstants.Type.KEYSYM, GLFW.GLFW_KEY_UNKNOWN, CATEGORY);
	/** 绑键捕获期间为 true，tick 里吞掉热键点击。 */
	public static boolean suppressHotkeys;

	private KitKeys() {
	}

	/** 向 Fabric 注册全部 KeyMapping。 */
	public static void register() {
		KeyMappingHelper.registerKeyMapping(OPEN_GUI);
		KeyMappingHelper.registerKeyMapping(EMERGENCY_STOP);
		KeyMappingHelper.registerKeyMapping(START_STOP);
		KeyMappingHelper.registerKeyMapping(TOGGLE_BORER);
		KeyMappingHelper.registerKeyMapping(BORER_HOME);
		KeyMappingHelper.registerKeyMapping(PORTAL_HOME);
		KeyMappingHelper.registerKeyMapping(TOGGLE_SURROUND);
		KeyMappingHelper.registerKeyMapping(TOGGLE_FEEDER);
		KeyMappingHelper.registerKeyMapping(TOGGLE_PLANTER);
		KeyMappingHelper.registerKeyMapping(TOGGLE_CHOPPER);
		KeyMappingHelper.registerKeyMapping(TOGGLE_FISHER);
		KeyMappingHelper.registerKeyMapping(TOGGLE_VILLAGER_SCAN);
	}

	/** 全部热键数组，供重置用。 */
	public static KeyMapping[] all() {
		return new KeyMapping[]{OPEN_GUI, EMERGENCY_STOP, START_STOP, TOGGLE_BORER, BORER_HOME, PORTAL_HOME, TOGGLE_SURROUND, TOGGLE_FEEDER, TOGGLE_PLANTER, TOGGLE_CHOPPER, TOGGLE_FISHER, TOGGLE_VILLAGER_SCAN};
	}

	/** 热键与界面中文标签。 */
	public record BindInfo(KeyMapping mapping, String label) {}

	/** 绑键界面用的映射与标签列表。 */
	public static BindInfo[] allInfos() {
		return new BindInfo[]{
			new BindInfo(OPEN_GUI, "打开 / 关闭界面"),
			new BindInfo(EMERGENCY_STOP, "紧急停止巡航"),
			new BindInfo(START_STOP, "开始 / 停止上次目标"),
			new BindInfo(TOGGLE_BORER, "开关盾构机"),
			new BindInfo(TOGGLE_SURROUND, "开关自动围箱"),
			new BindInfo(TOGGLE_FEEDER, "开关自动喂养"),
			new BindInfo(TOGGLE_PLANTER, "开关自动种田"),
			new BindInfo(TOGGLE_CHOPPER, "开关自动挖树"),
			new BindInfo(TOGGLE_FISHER, "开关自动钓鱼"),
			new BindInfo(TOGGLE_VILLAGER_SCAN, "开关村民扫描"),
			new BindInfo(BORER_HOME, "盾构沿路回家"),
			new BindInfo(PORTAL_HOME, "沿路飞回地狱门"),
		};
	}

	/** 键盘事件是否命中该绑定。 */
	public static boolean matches(KeyMapping mapping, KeyEvent event) {
		return !mapping.isUnbound() && mapping.matches(event);
	}

	/** 鼠标事件是否命中该绑定。 */
	public static boolean matchesMouse(KeyMapping mapping, MouseButtonEvent event) {
		return !mapping.isUnbound() && mapping.matchesMouse(event);
	}

	/** GLFW 层是否仍按住（不依赖 consumeClick）。 */
	public static boolean isPhysicallyDown(Minecraft client, KeyMapping mapping) {
		if (mapping.isUnbound() || client == null) return false;
		InputConstants.Key bound = KeyMappingHelper.getBoundKeyOf(mapping);
		if (bound.getType() == InputConstants.Type.MOUSE) return mapping.isDown();
		if (bound.getType() != InputConstants.Type.KEYSYM) return false;
		return InputConstants.isKeyDown(client.getWindow(), bound.getValue());
	}

	/** 绑定键显示名；未绑定则「未绑定」。 */
	public static String boundLabel(KeyMapping mapping) {
		return mapping.isUnbound() ? "未绑定" : mapping.getTranslatedKeyMessage().getString();
	}

	/** 「名称 — 键位」短句。 */
	public static String hintEntry(String name, KeyMapping mapping) {
		return name + " — " + boundLabel(mapping);
	}

	/** 全部热键提示串，未绑定的单独列在末尾。 */
	public static String hintLine() {
		record Hint(String name, KeyMapping mapping) {}
		Hint[] hints = {
			new Hint("打开界面", OPEN_GUI),
			new Hint("紧急停止", EMERGENCY_STOP),
			new Hint("巡航", START_STOP),
			new Hint("盾构", TOGGLE_BORER),
			new Hint("沿路回家", BORER_HOME),
			new Hint("回地狱门", PORTAL_HOME),
			new Hint("围箱", TOGGLE_SURROUND),
			new Hint("喂养", TOGGLE_FEEDER),
			new Hint("种田", TOGGLE_PLANTER),
			new Hint("挖树", TOGGLE_CHOPPER),
			new Hint("钓鱼", TOGGLE_FISHER),
			new Hint("村庄扫描", TOGGLE_VILLAGER_SCAN),
		};
		StringBuilder bound = new StringBuilder();
		StringBuilder unbound = new StringBuilder();
		for (Hint hint : hints) {
			if (hint.mapping.isUnbound()) {
				if (!unbound.isEmpty()) unbound.append('、');
				unbound.append(hint.name);
			} else {
				if (!bound.isEmpty()) bound.append("  ·  ");
				bound.append(hintEntry(hint.name, hint.mapping));
			}
		}
		if (!unbound.isEmpty()) {
			if (!bound.isEmpty()) bound.append("  ·  ");
			bound.append("未绑定：").append(unbound);
		}
		return bound.toString();
	}

	/** 写入新绑定并保存原版 options。 */
	public static void applyBinding(KeyMapping mapping, InputConstants.Key key, Minecraft client) {
		mapping.setKey(key);
		KeyMapping.resetMapping();
		if (client != null && client.options != null) client.options.save();
	}

	/** 恢复该键默认绑定。 */
	public static void resetBinding(KeyMapping mapping, Minecraft client) {
		applyBinding(mapping, mapping.getDefaultKey(), client);
	}
}
