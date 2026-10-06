package dev.twob2tkit.chopper;

import java.util.Collection;
import java.util.Set;
import net.minecraft.core.BlockPos;

/** One explicitly selected natural tree; the bounds also constrain obstacle mining. */
public record ChopperFixedTreePlan(BlockPos root, BlockPos min, BlockPos max) {
    public ChopperFixedTreePlan {
        if (root == null || min == null || max == null) throw new IllegalArgumentException("Fixed tree requires root and bounds");
        root=root.immutable();min=min.immutable();max=max.immutable();
        long x=(long)max.getX()-min.getX()+1,y=(long)max.getY()-min.getY()+1,z=(long)max.getZ()-min.getZ()+1;
        if(x<1||y<1||z<1||x>65||z>65||y>128||x*y*z>50000
            ||min.getY()<-64||max.getY()>319
            ||root.getX()<min.getX()||root.getX()>max.getX()
            ||root.getY()<min.getY()||root.getY()>max.getY()
            ||root.getZ()<min.getZ()||root.getZ()>max.getZ())
            throw new IllegalArgumentException("Fixed tree bounds must contain its root and be bounded");
    }
    public boolean contains(BlockPos p){
        return p!=null&&p.getX()>=min.getX()&&p.getX()<=max.getX()
            &&p.getY()>=min.getY()&&p.getY()<=max.getY()&&p.getZ()>=min.getZ()&&p.getZ()<=max.getZ();
    }
    boolean accepts(Collection<BlockPos> logs,Collection<BlockPos> stumps,String type){
        boolean wide=Set.of("minecraft:spruce_log","minecraft:jungle_log","minecraft:dark_oak_log","minecraft:pale_oak_log").contains(type);
        int margin=wide?1:0;
        return !logs.isEmpty()&&logs.size()<=ChopperTrees.MAX_LOGS&&logs.stream().allMatch(this::contains)
            &&stumps.contains(root)&&stumps.size()<=(wide?4:1)
            &&stumps.stream().allMatch(p->p.getY()==root.getY()
                &&Math.abs((long)p.getX()-root.getX())<=margin&&Math.abs((long)p.getZ()-root.getZ())<=margin);
    }
}
