package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ProjectedSourceColumnPolicyTest {
    private List<ProjectedSourceColumnPolicy.Cell> fixture(){
        var cells=new ArrayList<ProjectedSourceColumnPolicy.Cell>();
        for(int i=0;i<27;i++)cells.add(new ProjectedSourceColumnPolicy.Cell(0,i<9?8:i==9||i==11?0:i==10?1:-1,i==9||i==11));
        return cells;
    }
    private String reject(List<ProjectedSourceColumnPolicy.Cell> c,int target,boolean before){
        return ProjectedSourceColumnPolicy.rejection(c,target,before,3,72,true,true,false);
    }
    @Test void realSourceAndFallingWaterFixtureCanBeRepairedWithoutDrainingOriginalSources(){
        assertNull(reject(fixture(),0,true));assertNull(reject(fixture(),10,true));assertNull(reject(fixture(),26,true));
        assertNotNull(reject(fixture(),9,true));assertNotNull(reject(fixture(),11,true));
    }
    @Test void successfulUseNeedsTheSelectedCellToBecomeSourceNotJustFlowingWater(){
        var cells=fixture();assertNotNull(reject(cells,0,false));
        for(int flow=1;flow<=15;flow++){cells.set(0,new ProjectedSourceColumnPolicy.Cell(0,flow,false));assertNotNull(reject(cells,0,false));}
        cells.set(0,new ProjectedSourceColumnPolicy.Cell(0,0,false));assertNull(reject(cells,0,false));
    }
    @Test void losingEitherExistingSourceStopsTheNextUseAndConfirmation(){
        for(int source:new int[]{9,11})for(int state:new int[]{-1,1,8}){
            var cells=fixture();cells.set(source,new ProjectedSourceColumnPolicy.Cell(0,state,true));
            assertNotNull(reject(cells,0,true));cells.set(0,new ProjectedSourceColumnPolicy.Cell(0,0,false));assertNotNull(reject(cells,0,false));
        }
    }
    @Test void everyCellMustBeSourceInBlueprintAndPlainAirOrWaterInWorld(){
        for(int i=0;i<27;i++){
            var cells=fixture();cells.set(i,new ProjectedSourceColumnPolicy.Cell(1,8,false));assertNotNull(reject(cells,0,true));
            cells=fixture();cells.set(i,new ProjectedSourceColumnPolicy.Cell(0,-2,false));assertNotNull(reject(cells,0,true));
            cells=fixture();cells.set(i,null);assertNotNull(reject(cells,0,true));
        }
    }
    @Test void missingFloorWallOrWetOverflowRejectsTheWholeOperation(){
        for(int f=0;f<3;f++)assertNotNull(ProjectedSourceColumnPolicy.rejection(fixture(),0,true,f,72,true,true,false));
        for(int w=0;w<72;w++)assertNotNull(ProjectedSourceColumnPolicy.rejection(fixture(),0,true,3,w,true,true,false));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(fixture(),0,true,3,72,false,true,false));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(fixture(),0,true,4,72,true,true,false));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(fixture(),0,true,3,73,true,true,false));
    }
    @Test void otherLivingEntitiesOrLossOfServiceReserveStopsUse(){
        assertNotNull(ProjectedSourceColumnPolicy.rejection(fixture(),0,true,3,72,true,false,false));
        assertNotNull(ProjectedSourceColumnPolicy.rejection(fixture(),0,true,3,72,true,true,true));
        assertTrue(ProjectedSourceColumnPolicy.actorReady(19,16,270,300,false,true));
        assertFalse(ProjectedSourceColumnPolicy.actorReady(18.99,20,300,300,false,true));
        assertFalse(ProjectedSourceColumnPolicy.actorReady(20,15,300,300,false,true));
        assertFalse(ProjectedSourceColumnPolicy.actorReady(20,20,269,300,false,true));
        assertFalse(ProjectedSourceColumnPolicy.actorReady(20,20,300,300,true,true));
        assertFalse(ProjectedSourceColumnPolicy.actorReady(Double.NaN,20,300,300,false,true));
        assertFalse(ProjectedSourceColumnPolicy.actorReady(20,20,300,300,false,false));
    }
    @Test void floorTriggerPhaseIsAllowedButOrientationAndAllOtherPinsRemainExact(){
        String a="Block{minecraft:dropper}[facing=up,triggered=true]",b=a.replace("true","false");
        assertTrue(ProjectedSourceColumnPolicy.samePinned(a,b,true));assertFalse(ProjectedSourceColumnPolicy.samePinned(a,b,false));
        assertFalse(ProjectedSourceColumnPolicy.samePinned(a,b.replace("facing=up","facing=north"),true));
        assertFalse(ProjectedSourceColumnPolicy.samePinned("Block{minecraft:stone}","Block{minecraft:glass}",false));
    }
    @Test void exactShapeOnlyNoRotatedOversizedOrOverflowingBounds(){
        var real=new ProjectedSourceColumnPolicy.Bounds(761388,59,793986,761390,67,793986);assertTrue(real.valid());
        assertTrue(real.contains(761389,62,793986));assertFalse(real.contains(761389,68,793986));
        assertFalse(new ProjectedSourceColumnPolicy.Bounds(0,0,0,1,8,0).valid());
        assertFalse(new ProjectedSourceColumnPolicy.Bounds(0,0,0,2,9,0).valid());
        assertFalse(new ProjectedSourceColumnPolicy.Bounds(0,0,0,2,8,1).valid());
        assertFalse(new ProjectedSourceColumnPolicy.Bounds(0,Integer.MIN_VALUE,0,2,Integer.MIN_VALUE+8,0).valid());
        assertFalse(new ProjectedSourceColumnPolicy.Bounds(Integer.MAX_VALUE,0,0,Integer.MIN_VALUE+1,8,0).valid());
    }
    @Test void existingColumnChannelDrainAndFillModesCannotBeCombined(){
        assertTrue(ProjectedSourceColumnPolicy.exclusivePlace(true,false,false,false));
        assertFalse(ProjectedSourceColumnPolicy.exclusivePlace(false,false,false,false));
        for(int flags=1;flags<8;flags++)assertFalse(ProjectedSourceColumnPolicy.exclusivePlace(true,(flags&1)!=0,(flags&2)!=0,(flags&4)!=0));
    }
    @Test void partialManifestsAndOutOfRangeTargetsAreNotValidWork(){
        assertNotNull(reject(fixture().subList(0,26),0,true));assertNotNull(reject(null,0,true));
        assertNotNull(reject(fixture(),-1,true));assertNotNull(reject(fixture(),27,true));
    }
}
