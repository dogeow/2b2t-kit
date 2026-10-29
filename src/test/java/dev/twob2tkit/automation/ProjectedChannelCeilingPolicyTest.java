package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import static org.junit.jupiter.api.Assertions.*;
class ProjectedChannelCeilingPolicyTest {
    @Test void onlySourceAndImmediateWestAreCandidateOpenings(){
        assertTrue(ProjectedChannelCeilingPolicy.allowedOffset(0,1,0));
        assertTrue(ProjectedChannelCeilingPolicy.allowedOffset(-1,1,0));
        assertFalse(ProjectedChannelCeilingPolicy.allowedOffset(-2,1,0));
        assertFalse(ProjectedChannelCeilingPolicy.allowedOffset(1,1,0));
        assertFalse(ProjectedChannelCeilingPolicy.allowedOffset(-1,0,0));
        assertFalse(ProjectedChannelCeilingPolicy.allowedOffset(-1,1,1));
    }
    private String channel(boolean sourceOpen,boolean westOpen,int selected){
        var cells=new ArrayList<ProjectedChannelWaterPolicy.Cell>();
        for(int i=0;i<8;i++){
            boolean air=i==0&&sourceOpen||i==1&&westOpen;
            boolean roof=ProjectedChannelCeilingPolicy.roof(true,!air,air,i,selected);
            cells.add(new ProjectedChannelWaterPolicy.Cell(i,-1,true,true,true,roof));
        }
        return ProjectedChannelWaterPolicy.rejection(cells,true,true,true);
    }
    @Test void declaredWestAccessKeepsSourceCeilingClosed(){assertNull(channel(false,true,1));}
    @Test void legacySourceOpeningDoesNotAuthorizeWestOpening(){
        assertNull(channel(true,false,0));assertNotNull(channel(false,true,0));
    }
    @Test void selectingWestDoesNotAuthorizeAnotherOrTwoOpenings(){
        assertNotNull(channel(true,false,1));assertNotNull(channel(true,true,1));
    }
    @Test void wrongMaterialOrPartialRoofNeverCountsAsAnOpening(){
        assertFalse(ProjectedChannelCeilingPolicy.roof(false,false,true,1,1));
        assertFalse(ProjectedChannelCeilingPolicy.roof(true,false,false,1,1));
    }
}
