package dev.twob2tkit.map;

import dev.twob2tkit.runtime.api.MapTaskView.Area;

public record MapViewport(int width, int height, double originX, double originZ, double cameraX,
                          double cameraZ, double pixelsPerBlock) {
    public double x(double x) { return originX + (x - cameraX) * pixelsPerBlock; }
    public double z(double z) { return originZ + (z - cameraZ) * pixelsPerBlock; }
    public Area bounds() {
        return new Area(block(0, originX, cameraX), block(0, originZ, cameraZ),
            block(width, originX, cameraX), block(height, originZ, cameraZ));
    }
    private int block(int pixel, double origin, double camera) {
        return (int)Math.floor(camera + (pixel - origin) / pixelsPerBlock);
    }
    public boolean visible(double x, double z, int margin) {
        return x >= -margin && x <= width + margin && z >= -margin && z <= height + margin;
    }
}
