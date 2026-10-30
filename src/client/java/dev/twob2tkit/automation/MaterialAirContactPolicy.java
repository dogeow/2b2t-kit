package dev.twob2tkit.automation;
/** Symmetric voxel-contact tolerance, never a permission to enter liquid or solids. */
final class MaterialAirContactPolicy {
    static final double EPSILON=1e-7;
    private MaterialAirContactPolicy(){}
    static int minimumCell(double minimum){if(!Double.isFinite(minimum))throw new IllegalArgumentException("Finite body bounds required");return (int)Math.floor(minimum+EPSILON);}
    static int maximumCell(double maximum){if(!Double.isFinite(maximum))throw new IllegalArgumentException("Finite body bounds required");return (int)Math.floor(maximum-EPSILON);}
}
