package dev.twob2tkit.builder;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BuildStationsTest {
    @Test void includesStandingAboveAFloorHoleAndNarrowSideAisles(){
        var cells=BuildStations.around(BlockPos.ZERO);
        assertTrue(cells.contains(new BlockPos(1,1,0)));
        assertTrue(cells.contains(new BlockPos(0,1,0)));
        assertTrue(cells.contains(new BlockPos(1,0,1)));
        assertFalse(cells.contains(BlockPos.ZERO));
    }
    @Test void floorCandidatesProduceAReachableStationWhereOldBelowOnlyCandidatesCouldNot(){
        var world=new BuildPath.World(){public boolean clear(BlockPos p){return p.getY()==1&&p.getX()>=-3&&p.getX()<=3&&p.getZ()>=-3&&p.getZ()<=3;}public boolean edge(BlockPos a,BlockPos b){return true;}};
        var route=BuildPath.find(world,new BlockPos(3,1,0),BuildStations.around(BlockPos.ZERO),100);
        assertFalse(route.nodes().isEmpty());assertEquals(1,route.nodes().getLast().getY());
    }
}
