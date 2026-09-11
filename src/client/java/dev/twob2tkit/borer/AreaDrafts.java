package dev.twob2tkit.borer;

import dev.twob2tkit.KitConfig;
import net.minecraft.client.Minecraft;
import net.minecraft.world.level.storage.LevelResource;

/** Persist the editor independently of the validated bounds consumed by the mining engine. */
public final class AreaDrafts {
    public record Draft(String context, String source, String name, String a, String b,
                        String length, String width, String height) {
        public Draft {
            context = text(context); source = text(source); name = text(name);
            a = text(a); b = text(b);
            length = length == null ? "30" : length;
            width = width == null ? "30" : width;
            height = height == null ? "30" : height;
        }
        public Draft edit(String name, String a, String b, String length, String width, String height) {
            return new Draft(context, source, name, a, b, length, width, height);
        }
        public Draft rebase(KitConfig config) {
            return new Draft(context, signature(config), name, a, b, length, width, height);
        }
    }

    public static Draft open(KitConfig config, String context) {
        Draft saved = config.borerAreaDraft;
        String source = signature(config);
        if (saved != null && saved.context().equals(context) && saved.source().equals(source)) return saved;
        String name = BorerAreaProjects.activeName(config);
        return config.borerAreaDraft = new Draft(context, source,
            name.isBlank() ? BorerAreaProjects.defaultName(config) : name,
            BorerAreaMarks.format(config.borerAreaASet, config.borerAreaAx, config.borerAreaAy, config.borerAreaAz),
            BorerAreaMarks.format(config.borerAreaBSet, config.borerAreaBx, config.borerAreaBy, config.borerAreaBz), "30", "30", "30");
    }

    /** A removed/rebuilt old screen must not resurrect a draft after an explicit project load or clear. */
    public static boolean store(KitConfig config, Draft previous, Draft next) {
        if (previous == null || config.borerAreaDraft != previous || !previous.source().equals(signature(config))) return false;
        if (!previous.context().equals(next.context()) || !previous.source().equals(next.source())) return false;
        config.borerAreaDraft = next;
        return true;
    }

    public static String signature(KitConfig config) {
        return text(config.activeAreaProjectId) + ":"
            + BorerAreaMarks.format(config.borerAreaASet, config.borerAreaAx, config.borerAreaAy, config.borerAreaAz) + ":"
            + BorerAreaMarks.format(config.borerAreaBSet, config.borerAreaBx, config.borerAreaBy, config.borerAreaBz);
    }

    public static boolean hasUnappliedCorners(KitConfig config) {
        Draft saved = config.borerAreaDraft;
        return saved != null && saved.source().equals(signature(config))
            && (!saved.a().equals(BorerAreaMarks.format(config.borerAreaASet, config.borerAreaAx, config.borerAreaAy, config.borerAreaAz))
                || !saved.b().equals(BorerAreaMarks.format(config.borerAreaBSet, config.borerAreaBx, config.borerAreaBy, config.borerAreaBz)));
    }

    public static String context(Minecraft client) {
        if (client == null || client.level == null) return "";
        String server = client.getCurrentServer() != null ? client.getCurrentServer().ip
            : client.getSingleplayerServer() != null ? client.getSingleplayerServer().getWorldPath(LevelResource.ROOT).toString() : "unknown";
        return server + "|" + BorerAreaProjects.currentDimension(client);
    }

    public static String status(String a, String b) {
        boolean hasA = !text(a).isBlank(), hasB = !text(b).isBlank();
        if (hasA && hasB) return "A/B 已填写；保存或开始时校验范围";
        if (hasA) return "A 已填写，关闭菜单自动暂存；待标 B";
        if (hasB) return "B 已填写，关闭菜单自动暂存；待标 A";
        return "先标 A 或 B；关闭菜单自动暂存";
    }

    private static String text(String value) { return value == null ? "" : value; }
    private AreaDrafts() {}
}
