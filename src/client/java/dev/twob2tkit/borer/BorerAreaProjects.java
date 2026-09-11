package dev.twob2tkit.borer;

import net.minecraft.client.Minecraft;

import java.util.Locale;
import java.util.UUID;
import dev.twob2tkit.KitConfig;

/** 区域挖工程：把点 A/B 和断面存进配置，可保存多个、随时加载。 */
public final class BorerAreaProjects {
	private BorerAreaProjects() {
	}

	/** 当前激活工程名；没有则空串。 */
	public static String activeName(KitConfig config) {
		if (config.activeAreaProjectId == null || config.activeAreaProjectId.isBlank()) return "";
		KitConfig.AreaProject project = config.areaProjectById(config.activeAreaProjectId);
		return project == null ? "" : project.name;
	}

	/** 工程尺寸与断面摘要。 */
	public static String summary(KitConfig.AreaProject project) {
		if (project == null) return "未标区域";
		int wide = Math.abs(project.ax - project.bx) + 1;
		int along = Math.abs(project.az - project.bz) + 1;
		String size = wide + "×" + along;
		if (project.ay != project.by) {
			size += " Y" + Math.max(project.ay, project.by) + "→" + Math.min(project.ay, project.by);
		} else {
			size += " Y" + project.ay;
		}
		size += " · 自动清挖";
		String dim = KitConfig.dimensionLabel(project.dimension);
		if (!dim.equals("未标注")) size += " " + dim;
		return size;
	}

	/** 从当前配置快照出一个新工程对象（未写入列表）。 */
	public static KitConfig.AreaProject capture(KitConfig config, String name, String dimension) {
		KitConfig.AreaProject project = new KitConfig.AreaProject();
		project.id = UUID.randomUUID().toString();
		project.name = name == null ? "" : name.trim();
		project.ax = config.borerAreaAx;
		project.ay = config.borerAreaAy;
		project.az = config.borerAreaAz;
		project.bx = config.borerAreaBx;
		project.by = config.borerAreaBy;
		project.bz = config.borerAreaBz;
		project.stripWidth = Math.max(1, Math.min(5, config.borerWidth));
		project.sliceHeight = Math.max(1, Math.min(5, config.borerAreaSliceHeight));
		project.dimension = KitConfig.normalizeDimension(dimension);
		project.updatedAt = System.currentTimeMillis();
		return project;
	}

	/** 把工程加载进配置并切到区域挖模式。 */
	public static void apply(KitConfig config, KitConfig.AreaProject project) {
		config.borerAreaDraft = null;
		config.borerAreaAx = project.ax;
		config.borerAreaAy = project.ay;
		config.borerAreaAz = project.az;
		config.borerAreaBx = project.bx;
		config.borerAreaBy = project.by;
		config.borerAreaBz = project.bz;
		config.borerAreaASet = true;
		config.borerAreaBSet = true;
		config.borerWidth = Math.max(1, Math.min(5, project.stripWidth));
		config.borerAreaSliceHeight = Math.max(1, Math.min(5, project.sliceHeight));
		config.borerLastMode = TunnelBorer.Mode.AREA.name();
		config.activeAreaProjectId = project.id;
		config.save();
	}

	/** 默认工程名「区域 N」。 */
	public static String defaultName(KitConfig config) {
		return "区域 " + (config.areaProjects.size() + 1);
	}

	/** 当前世界维度 id（规范化后）。 */
	public static String currentDimension(Minecraft client) {
		if (client == null || client.level == null) return "";
		return KitConfig.normalizeDimension(client.level.dimension().identifier().toString());
	}

	/** 列表行：可选激活前缀 + 名 + 摘要。 */
	public static String listLine(KitConfig.AreaProject project, boolean active) {
		String prefix = active ? "▸ " : "";
		String name = project.name == null ? "" : project.name.trim();
		if (name.isEmpty()) name = "未命名";
		return prefix + name + "  " + summary(project);
	}

	/** A/B 坐标短串。 */
	public static String formatCoords(KitConfig.AreaProject project) {
		return String.format(Locale.ROOT, "A %d %d %d  B %d %d %d",
			project.ax, project.ay, project.az, project.bx, project.by, project.bz);
	}
}
