package dev.twob2tkit.automation;

/** Dry sand only; the unequal Y corners are essential because AREA treats equal Y as unbounded. */
final class MaterialQuarryPolicy {
    private MaterialQuarryPolicy() {}
    static boolean bounds(int dx,int dy,int dz,int target) {
        return dx>=1&&dx<=16&&dy>=2&&dy<=12&&dz>=1&&dz<=16
            &&(long)dx*dy*dz<=3072&&target>=1&&target<=1024;
    }
    static boolean cellAllowed(boolean loaded,boolean inside,boolean air,boolean sand,
                               boolean fluid,boolean blockEntity) {
        return loaded&&!fluid&&!blockEntity&&(!inside||air||sand);
    }
}
