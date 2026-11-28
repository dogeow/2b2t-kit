package dev.twob2tkit.automation;
/** Symmetric voxel-contact tolerance, never a permission to enter liquid or solids. */
final class MaterialAirContactPolicy {
    static final double EPSILON=1e-7;
    private MaterialAirContactPolicy(){}
    static int minimumCell(double minimum){if(!Double.isFinite(minimum))throw new IllegalArgumentException("Finite body bounds required");return (int)Math.floor(minimum+EPSILON);}
    static int maximumCell(double maximum){if(!Double.isFinite(maximum))throw new IllegalArgumentException("Finite body bounds required");return (int)Math.floor(maximum-EPSILON);}
    static boolean fluidIntersects(double bodyMinY,double bodyMaxY,int cellY,double height){
        if(!Double.isFinite(bodyMinY)||!Double.isFinite(bodyMaxY)||bodyMinY>=bodyMaxY||!Double.isFinite(height)||height<=0||height>1)return true;
        return bodyMinY<cellY+height-EPSILON&&bodyMaxY>cellY+EPSILON;
    }
    /** Cactus contact has a hazard margin beyond its inset collision shape. */
    static boolean cactusTransitionSafe(net.minecraft.world.phys.AABB start, net.minecraft.world.phys.Vec3 delta,
                                        net.minecraft.core.BlockPos cactus){
        if(start==null||delta==null||cactus==null||!Double.isFinite(delta.x)||!Double.isFinite(delta.y)||!Double.isFinite(delta.z)
                ||!Double.isFinite(start.minX)||!Double.isFinite(start.minY)||!Double.isFinite(start.minZ)
                ||!Double.isFinite(start.maxX)||!Double.isFinite(start.maxY)||!Double.isFinite(start.maxZ))return false;
        var hazard=new net.minecraft.world.phys.AABB(cactus.getX()-.15,cactus.getY()-.1,cactus.getZ()-.15,
            cactus.getX()+1.15,cactus.getY()+1.25,cactus.getZ()+1.15);
        if(!start.expandTowards(delta).intersects(hazard))return true;
        if(!start.intersects(hazard)||start.move(delta).intersects(hazard))return false;
        // If already exposed, permit only a move outward, never across cactus.
        return (delta.x<0&&start.getCenter().x<=cactus.getX()+.5)
            ||(delta.x>0&&start.getCenter().x>=cactus.getX()+.5)
            ||(delta.z<0&&start.getCenter().z<=cactus.getZ()+.5)
            ||(delta.z>0&&start.getCenter().z>=cactus.getZ()+.5)
            ||(delta.y>0&&start.minY>=cactus.getY()+.5);
    }
}
