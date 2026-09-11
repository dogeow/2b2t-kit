package dev.twob2tkit.borer;
import net.minecraft.core.BlockPos;
/** Validates all coordinates before either corner is committed. */
public final class AreaForm {
    public record Bounds(BlockPos a, BlockPos b) {}
    public static Bounds parse(String a, String b, int minY, int maxY) {
        Bounds bounds = parseDraft(a, b, minY, maxY);
        if (bounds.a() == null || bounds.b() == null) throw new IllegalArgumentException("请补齐点 " + (bounds.a() == null ? "A" : "B") + " 再预览或开始；已有标点可保存草稿");
        return bounds;
    }
    /** Explicit draft save validates supplied corners, but does not require the other corner. */
    public static Bounds parseDraft(String a, String b, int minY, int maxY) {
        BlockPos pa = corner(a, "A", minY, maxY), pb = corner(b, "B", minY, maxY);
        if (pa == null && pb == null) throw new IllegalArgumentException("请先设置点 A 或点 B；可以分两次标点");
        if (pa != null && pb != null && (Math.abs((long)pa.getX() - pb.getX()) >= 64 || Math.abs((long)pa.getZ() - pb.getZ()) >= 64))
            throw new IllegalArgumentException("长 X 和宽 Z 最多 64 格");
        return new Bounds(pa, pb);
    }
    private static BlockPos corner(String raw, String name, int minY, int maxY) {
        if (raw == null || raw.isBlank()) return null;
        int[] xyz = new int[3];
        if (raw.trim().replace(',', ' ').split("\\s+").length != 3 || !BorerAreaMarks.parse(raw, xyz))
            throw new IllegalArgumentException("点 " + name + " 请填写三个整数：X Y Z");
        if (xyz[1] < minY || xyz[1] >= maxY - 3) throw new IllegalArgumentException("点 " + name + " 的 Y 超出世界可挖范围");
        return new BlockPos(xyz[0], xyz[1], xyz[2]);
    }
    public static Bounds fromSize(BlockPos p, int x, int z, int y) {
        if (x < 1 || x > 64 || z < 1 || z > 64 || y < 2 || y > 384) throw new IllegalArgumentException("长宽 1–64，高度 2–384");
        return new Bounds(p, p.offset(x - 1, -(y - 1), z - 1));
    }
    private AreaForm() {}
}
