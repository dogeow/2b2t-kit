package dev.twob2tkit.builder;
import net.minecraft.core.BlockPos;
import java.util.*;
/** Candidate feet cells; live collision, eye reach and ray checks remain mandatory. */
public final class BuildStations {
    private BuildStations(){}
    public static List<BlockPos> around(BlockPos target){
        var cells=new ArrayList<BlockPos>();
        for(int dx=-3;dx<=3;dx++)for(int dz=-3;dz<=3;dz++)for(int dy=-3;dy<=2;dy++){
            // Feet are centered at +.5,+.02,+.5; approximate standing eye height is 1.62.
            double eyeDeltaY=dy+1.14;
            if(dx*dx+dz*dz+eyeDeltaY*eyeDeltaY>4.15*4.15)continue;
            if(dx==0&&dz==0&&dy<=0)continue; // Never stand inside the block being placed.
            cells.add(target.offset(dx,dy,dz));
        }
        return cells;
    }
}
