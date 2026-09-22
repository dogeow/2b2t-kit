package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import java.util.*;

/** Conservative voxel enclosure candidates; openings or clipped selection edges remain exterior. */
public final class ProjectionVoidPolicy {
    private ProjectionVoidPolicy(){}
    public static Set<BlockPos> enclosed(Set<BlockPos> selected,Set<BlockPos> air){
        if(!selected.containsAll(air))throw new IllegalArgumentException("Air outside selected volume");
        Set<BlockPos> exterior=new HashSet<>();var queue=new ArrayDeque<BlockPos>();
        for(var p:air)for(var direction:Direction.values())if(!selected.contains(p.relative(direction))){
            if(exterior.add(p))queue.add(p);break;
        }
        while(!queue.isEmpty()){
            var p=queue.remove();
            for(var direction:Direction.values()){
                var q=p.relative(direction);
                if(air.contains(q)&&exterior.add(q))queue.add(q);
            }
        }
        var result=new HashSet<>(air);result.removeAll(exterior);return Set.copyOf(result);
    }
}
