package dev.twob2tkit.builder;

import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.core.BlockPos;
import net.minecraft.world.level.BlockGetter;
import net.minecraft.world.level.block.state.BlockState;

import java.lang.reflect.Method;
import java.util.List;

/** 可选反射访问 Litematica 原理图放置。 */
public final class LitematicaAccess {
	private static Boolean present;
	private static Method getSchematicWorld;
	private static Method getPlacementManager;
	private static Method getSelectedPlacement;
	private static Method getAllPlacements;
	private static Method isEnabled;
	private static Method isRenderingEnabled;
	private static Method getName;
	private static Method getRenderLayerRange;
	private static Method isPositionWithinRange;
	private static String lastError = "";

	/** 反射访问 Litematica 投影（可选依赖）。 */
	private LitematicaAccess() {
	}

	/** 是否装了 Litematica。 */
	public static boolean installed() {
		return FabricLoader.getInstance().isModLoaded("litematica")
			&& FabricLoader.getInstance().isModLoaded("malilib");
	}

	/** 最近一次反射错误。 */
	public static String lastError() {
		return lastError;
	}

	/** 当前原理图世界。 */
	public static BlockGetter schematicWorld() {
		if (!bind()) return null;
		try {
			Object world = getSchematicWorld.invoke(null);
			return world instanceof BlockGetter getter ? getter : null;
		} catch (ReflectiveOperationException exception) {
			lastError = "读取投影世界失败：" + exception.getClass().getSimpleName();
			return null;
		}
	}

	/** 当前放置名。 */
	public static String placementName() {
		Object placement = selectedOrFirstEnabled();
		if (placement == null) return "";
		try {
			Object name = getName.invoke(placement);
			return name == null ? "" : name.toString();
		} catch (ReflectiveOperationException exception) {
			return "";
		}
	}

	/** 是否有活动放置。 */
	public static boolean hasActivePlacement() {
		return selectedOrFirstEnabled() != null && schematicWorld() != null;
	}

	/** 方块是否在可见层。 */
	public static boolean inVisibleLayer(BlockPos pos) {
		if (!bind() || isPositionWithinRange == null) return true;
		try {
			Object range = getRenderLayerRange.invoke(null);
			if (range == null) return true;
			return (Boolean) isPositionWithinRange.invoke(range, pos.getX(), pos.getY(), pos.getZ());
		} catch (ReflectiveOperationException exception) {
			return true;
		}
	}

	/** 放置状态简述。 */
	public static String describe() {
		if (!installed()) {
			return "未安装 Litematica / MaLiLib。请放入 26.1.2 的两个 jar：用投影看图，twob2tkit 负责自动摆";
		}
		if (!bind()) {
			return lastError.isBlank() ? "已安装投影，但当前 API 对不上，无法读取" : lastError;
		}
		if (schematicWorld() == null) {
			return "Litematica 已装，但还没有投影世界。进存档后用 M 加载并放置投影";
		}
		String name = placementName();
		if (name.isBlank()) return "投影世界已有，但没有启用的放置。打开 Litematica 放置列表勾选一个";
		return "当前投影：" + name;
	}

	/** 当前选中或第一个启用放置。 */
	private static Object selectedOrFirstEnabled() {
		if (!bind()) return null;
		try {
			Object manager = getPlacementManager.invoke(null);
			if (manager == null) return null;
			Object selected = getSelectedPlacement.invoke(manager);
			if (isUsable(selected)) return selected;
			Object all = getAllPlacements.invoke(manager);
			if (!(all instanceof List<?> list)) return null;
			for (Object placement : list) {
				if (isUsable(placement)) return placement;
			}
			return null;
		} catch (ReflectiveOperationException exception) {
			lastError = "读取投影放置失败：" + exception.getClass().getSimpleName();
			return null;
		}
	}

	/** 放置是否可用。 */
	private static boolean isUsable(Object placement) throws ReflectiveOperationException {
		if (placement == null) return false;
		return (Boolean) isEnabled.invoke(placement) && (Boolean) isRenderingEnabled.invoke(placement);
	}

	/** 反射绑定 Litematica 类。 */
	private static boolean bind() {
		if (present != null) return present;
		if (!installed()) {
			present = false;
			lastError = "未安装 litematica / malilib";
			return false;
		}
		try {
			Class<?> handler = Class.forName("fi.dy.masa.litematica.world.SchematicWorldHandler");
			Class<?> data = Class.forName("fi.dy.masa.litematica.data.DataManager");
			Class<?> manager = Class.forName("fi.dy.masa.litematica.schematic.placement.SchematicPlacementManager");
			Class<?> placement = Class.forName("fi.dy.masa.litematica.schematic.placement.SchematicPlacement");
			getSchematicWorld = handler.getMethod("getSchematicWorld");
			getPlacementManager = data.getMethod("getSchematicPlacementManager");
			getSelectedPlacement = manager.getMethod("getSelectedSchematicPlacement");
			getAllPlacements = manager.getMethod("getAllSchematicsPlacements");
			isEnabled = placement.getMethod("isEnabled");
			isRenderingEnabled = placement.getMethod("isRenderingEnabled");
			getName = placement.getMethod("getName");
			getRenderLayerRange = data.getMethod("getRenderLayerRange");
			isPositionWithinRange = getRenderLayerRange.getReturnType()
				.getMethod("isPositionWithinRange", int.class, int.class, int.class);
			present = true;
			lastError = "";
			return true;
		} catch (ReflectiveOperationException exception) {
			present = false;
			lastError = "Litematica API 对不上：" + exception.getMessage();
			return false;
		}
	}

	/** 原理图世界某格状态。 */
	public static BlockState schematicState(BlockGetter world, BlockPos pos) {
		return world.getBlockState(pos);
	}
}
