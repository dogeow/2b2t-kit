package dev.twob2tkit.automation;

import java.util.List;

/** One source followed by seven west-flowing cells; never a general flood exception. */
final class ProjectedChannelWaterPolicy {
    record Cell(int projectedLevel,int actualLevel,boolean floor,boolean northWall,
                boolean southWall,boolean ceiling){}
    static String rejection(List<Cell> cells,boolean before,boolean ends,boolean entityClear){
        if(cells==null||cells.size()!=8)return "Exactly eight projected channel cells required";
        if(!ends)return "Both original dry closed trapdoors and packed-ice endpoints required";
        if(!entityClear)return "Projected channel contains a living entity or vehicle";
        for(int i=0;i<8;i++){
            var cell=cells.get(i);
            if(cell==null||cell.projectedLevel()!=i)return "Original source and seven flow levels required";
            if(!cell.floor()||!cell.northWall()||!cell.southWall()||!cell.ceiling())
                return "Exact projected channel floor, walls or ceiling changed";
            // Initial streams must be dry. After the one source, propagation
            // may still be AIR, but may never introduce another source/level.
            if(before?cell.actualLevel()!=-1:
                i==0?cell.actualLevel()!=0:cell.actualLevel()!=-1&&cell.actualLevel()!=i)
                return "Channel source or downstream water state changed";
        }
        return null;
    }
    private ProjectedChannelWaterPolicy(){}
}
