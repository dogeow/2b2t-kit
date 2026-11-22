package dev.twob2tkit.map;

import dev.twob2tkit.runtime.api.MapTaskView.Area;
import net.minecraft.client.gui.GuiGraphicsExtractor;

public final class MapLayerDrawing {
    private final GuiGraphicsExtractor g;
    private final MapViewport view;

    public MapLayerDrawing(GuiGraphicsExtractor g, MapViewport view) {
        this.g = g;
        this.view = view;
    }

    public void line(double x, double z, double toX, double toZ, int color) {
        double ax = view.x(x), ay = view.z(z), bx = view.x(toX), by = view.z(toZ);
        if (Math.max(ax,bx) < 0 || Math.max(ay,by) < 0
            || Math.min(ax,bx) > view.width() || Math.min(ay,by) > view.height()) return;
        float length = (float)Math.hypot(bx-ax, by-ay);
        if (length < .5f) return;
        var pose = g.pose();
        pose.pushMatrix();
        try {
            pose.translate((float)ax, (float)ay).rotate((float)Math.atan2(by-ay, bx-ax));
            g.fill(0, 0, (int)Math.ceil(length), 2, color);
        } finally { pose.popMatrix(); }
    }

    /**
     * Long recorded routes hold one point per block; when zoomed out most of them land on the same pixel.
     * Only draw to a point once it is at least two screen pixels from the last drawn one (the end is always kept).
     */
    public void polyline(java.util.List<net.minecraft.core.BlockPos> points, int color) {
        if (points.size() < 2) return;
        double minStep = 2 / Math.max(1e-6, view.pixelsPerBlock());
        var from = points.getFirst();
        for (int i = 1; i < points.size(); i++) {
            var to = points.get(i);
            double dx = to.getX() - from.getX(), dz = to.getZ() - from.getZ();
            if (i < points.size() - 1 && dx * dx + dz * dz < minStep * minStep) continue;
            line(from.getX() + .5, from.getZ() + .5, to.getX() + .5, to.getZ() + .5, color);
            from = to;
        }
    }

    public void area(Area area, int fill, int border) {
        double left = view.x(area.minX()), right = view.x(area.maxX());
        double top = view.z(area.minZ()), bottom = view.z(area.maxZ());
        if (right < 0 || bottom < 0 || left > view.width() || top > view.height()) return;
        int l = Math.max(0, (int)Math.floor(left)), t = Math.max(0, (int)Math.floor(top));
        int r = Math.min(view.width(), (int)Math.ceil(right)), b = Math.min(view.height(), (int)Math.ceil(bottom));
        if (fill != 0) g.fill(l,t,r,b,fill);
        if (border == 0) return;
        line(area.minX(), area.minZ(), area.maxX(), area.minZ(), border);
        line(area.maxX(), area.minZ(), area.maxX(), area.maxZ(), border);
        line(area.maxX(), area.maxZ(), area.minX(), area.maxZ(), border);
        line(area.minX(), area.maxZ(), area.minX(), area.minZ(), border);
    }

    public void circle(double x, double z, int radius, int color) {
        int segments = Math.clamp((int)(radius * view.pixelsPerBlock() / 3), 64, 720);
        double fromX = x + radius, fromZ = z;
        for (int i = 1; i <= segments; i++) {
            double a = i * 2 * Math.PI / segments;
            double nextX = x + radius * Math.cos(a), nextZ = z + radius * Math.sin(a);
            line(fromX, fromZ, nextX, nextZ, color);
            fromX = nextX;
            fromZ = nextZ;
        }
    }
}
