package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class ProjectedChannelWaterPolicyTest {
    private List<ProjectedChannelWaterPolicy.Cell> channel(boolean before){
        var cells=new ArrayList<ProjectedChannelWaterPolicy.Cell>();
        for(int i=0;i<8;i++)cells.add(new ProjectedChannelWaterPolicy.Cell(i,before?-1:i,true,true,true,true));
        return cells;
    }
    @Test void exactDryStreamCanReceiveItsOneSource(){
        assertNull(ProjectedChannelWaterPolicy.rejection(channel(true),true,true,true));
    }
    @Test void confirmedSourceDoesNotPretendThatDownstreamAlreadyPropagated(){
        var cells=channel(false);
        for(int i=1;i<8;i++)cells.set(i,new ProjectedChannelWaterPolicy.Cell(i,-1,true,true,true,true));
        assertNull(ProjectedChannelWaterPolicy.rejection(cells,false,true,true));
        assertNull(ProjectedChannelWaterPolicy.rejection(channel(false),false,true,true));
    }
    @Test void initialSourcesAndExistingStreamsCannotBeReused(){
        for(int i=0;i<8;i++){
            var cells=channel(true);cells.set(i,new ProjectedChannelWaterPolicy.Cell(i,i,true,true,true,true));
            assertNotNull(ProjectedChannelWaterPolicy.rejection(cells,true,true,true));
        }
    }
    @Test void everyFloorWallAndRoofMustStillBeProved(){
        for(int i=0;i<8;i++)for(int field=0;field<4;field++){
            var cells=channel(true);cells.set(i,new ProjectedChannelWaterPolicy.Cell(i,-1,
                field!=0,field!=1,field!=2,field!=3));
            assertNotNull(ProjectedChannelWaterPolicy.rejection(cells,true,true,true));
        }
    }
    @Test void waterCannotEscapeThroughAMissingEndpointOrWashAnEntity(){
        assertNotNull(ProjectedChannelWaterPolicy.rejection(channel(true),true,false,true));
        assertNotNull(ProjectedChannelWaterPolicy.rejection(channel(true),true,true,false));
    }
    @Test void differentBlueprintLevelsAndExtraSourcesAreRejected(){
        var cells=channel(false);cells.set(4,new ProjectedChannelWaterPolicy.Cell(4,0,true,true,true,true));
        assertNotNull(ProjectedChannelWaterPolicy.rejection(cells,false,true,true));
        cells=channel(true);cells.set(4,new ProjectedChannelWaterPolicy.Cell(5,-1,true,true,true,true));
        assertNotNull(ProjectedChannelWaterPolicy.rejection(cells,true,true,true));
        cells=channel(false);cells.set(0,new ProjectedChannelWaterPolicy.Cell(0,-1,true,true,true,true));
        assertNotNull(ProjectedChannelWaterPolicy.rejection(cells,false,true,true));
    }
    @Test void wrongSizeOrMissingObservationsAreNotAChannel(){
        assertNotNull(ProjectedChannelWaterPolicy.rejection(null,true,true,true));
        assertNotNull(ProjectedChannelWaterPolicy.rejection(channel(true).subList(0,7),true,true,true));
        var cells=channel(true);cells.set(3,null);
        assertNotNull(ProjectedChannelWaterPolicy.rejection(cells,true,true,true));
    }
}
