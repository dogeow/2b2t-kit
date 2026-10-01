package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionScaffoldPolicyTest {
    private final ProjectionScaffoldPolicy.Row row=new ProjectionScaffoldPolicy.Row(100,227,64,500,"minecraft:cobblestone");
    private ProjectionScaffoldPolicy.Point point(int x,int y,int z){return new ProjectionScaffoldPolicy.Point(x,y,z);}
    @Test void exactFirstAndLastOf128RowAreAccepted() {
        assertTrue(ProjectionScaffoldPolicy.rowValid(row,128,true));
        assertTrue(ProjectionScaffoldPolicy.contains(row,100,64,500));
        assertTrue(ProjectionScaffoldPolicy.contains(row,227,64,500));
        assertFalse(ProjectionScaffoldPolicy.contains(row,99,64,500));
        assertFalse(ProjectionScaffoldPolicy.contains(row,228,64,500));
    }
    @Test void rowNeverAllowsAdjacentLayerOrParallelRow() {
        assertFalse(ProjectionScaffoldPolicy.contains(row,100,63,500));
        assertFalse(ProjectionScaffoldPolicy.contains(row,100,65,500));
        assertFalse(ProjectionScaffoldPolicy.contains(row,100,64,499));
        assertFalse(ProjectionScaffoldPolicy.contains(row,100,64,501));
    }
    @Test void envelopeRejectsMissingDuplicateOrOversizedTargetsAndNonCubes() {
        assertFalse(ProjectionScaffoldPolicy.rowValid(row,127,true));
        assertFalse(ProjectionScaffoldPolicy.rowValid(row,129,true));
        assertFalse(ProjectionScaffoldPolicy.rowValid(row,128,false));
        assertFalse(ProjectionScaffoldPolicy.rowValid(new ProjectionScaffoldPolicy.Row(0,128,64,0,"minecraft:cobblestone"),129,true));
        assertFalse(ProjectionScaffoldPolicy.rowValid(new ProjectionScaffoldPolicy.Row(0,0,320,0,"minecraft:cobblestone"),1,true));
    }
    @Test void actualMeteorPredictionUsesDeltaAndClampsToBelowPlayerBlockLayer() {
        assertEquals(point(100,64,500),ProjectionScaffoldPolicy.predictedFootTarget(100.5,65.9,500.5,.1,-.0784,0));
        assertEquals(point(101,64,500),ProjectionScaffoldPolicy.predictedFootTarget(100.95,65.2,500.5,.1,0,0));
        assertEquals(point(100,65,500),ProjectionScaffoldPolicy.predictedFootTarget(100.5,66.2,500.5,0,0,0));
    }
    @Test void physicalShiftCanPredict63ButCannotAuthorizePlacement() {
        assertEquals(point(100,63,500),ProjectionScaffoldPolicy.predictedFootTarget(100.5,65.2,500.5,0,0,0,true,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,65.2,500.5,0,0,0,true));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,65.2,500.5,0,0,0,false,true));
    }
    @Test void feetAndPredictionMustBothRemainOver64WithBodyInsideTheRow() {
        assertTrue(ProjectionScaffoldPolicy.motionAllowed(row,100.5,65.9,500.5,.1,-.0784,0,false));
        assertTrue(ProjectionScaffoldPolicy.motionAllowed(row,227.5,65.2,500.5,0,0,0,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,64.9,500.5,0,0,0,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,66.0,500.5,0,0,0,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,65.01,500.5,0,-.0784,0,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.3,65.2,500.5,0,0,0,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,227.6,65.2,500.5,.2,0,0,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,65.2,500.7,0,0,0,false));
    }
    @Test void speedAndNonfinitePredictionsFailClosed() {
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,65.2,500.5,.23,0,0,false));
        assertFalse(ProjectionScaffoldPolicy.motionAllowed(row,100.5,65.2,500.5,0,.13,0,false));
        assertNull(ProjectionScaffoldPolicy.predictedFootTarget(Double.NaN,65.2,500.5,0,0,0));
        assertNull(ProjectionScaffoldPolicy.predictedFootTarget(Double.MAX_VALUE,65.2,500.5,0,0,0));
    }
    @Test void gateUsesActualScaffoldTargetAndAllWorldPlacementPreconditions() {
        var p=point(100,64,500);
        assertTrue(ProjectionScaffoldPolicy.candidateAllowed(row,p,p,true,true,false,true,true,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,point(100,65,500),p,true,true,false,true,true,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,p,point(101,64,500),true,true,false,true,true,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,p,p,false,true,false,true,true,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,p,p,true,false,false,true,true,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,p,p,true,true,true,true,true,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,p,p,true,true,false,false,true,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,p,p,true,true,false,true,false,"minecraft:cobblestone"));
        assertFalse(ProjectionScaffoldPolicy.candidateAllowed(row,p,p,true,true,false,true,true,"minecraft:dirt"));
    }
    @Test void worldRevisionAndLockedProjectionAreExact() {
        assertTrue(ProjectionScaffoldPolicy.scopeAllowed("world","world",7,7,"locked","locked"));
        assertFalse(ProjectionScaffoldPolicy.scopeAllowed("world","next",7,7,"locked","locked"));
        assertFalse(ProjectionScaffoldPolicy.scopeAllowed("world","world",7,8,"locked","locked"));
        assertFalse(ProjectionScaffoldPolicy.scopeAllowed("world","world",7,7,"locked","other"));
        assertFalse(ProjectionScaffoldPolicy.scopeAllowed("","",7,7,"locked","locked"));
    }
    @Test void healthGuardBusyManualInputOrInjuryStopsAdmission() {
        assertTrue(ProjectionScaffoldPolicy.safe(true,20,20,false,true,true,false,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(false,20,20,false,true,true,false,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,18.99,20,false,true,true,false,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,20,7,false,true,true,false,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,20,20,true,true,true,false,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,20,20,false,false,true,false,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,20,20,false,true,false,false,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,20,20,false,true,true,true,false,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,20,20,false,true,true,false,true,false));
        assertFalse(ProjectionScaffoldPolicy.safe(true,19.9,20,false,true,true,false,false,true));
    }
    @Test void oneServerAckAndOneSettledInventoryDeltaAreRequired() {
        assertTrue(ProjectionScaffoldPolicy.confirmed(true,true,128,127,10,18));
        assertFalse(ProjectionScaffoldPolicy.confirmed(false,true,128,127,10,18));
        assertFalse(ProjectionScaffoldPolicy.confirmed(true,false,128,127,10,18));
        assertFalse(ProjectionScaffoldPolicy.confirmed(true,true,128,128,10,18));
        assertFalse(ProjectionScaffoldPolicy.confirmed(true,true,128,126,10,18));
        assertFalse(ProjectionScaffoldPolicy.confirmed(true,true,128,127,10,17));
        assertFalse(ProjectionScaffoldPolicy.confirmed(true,true,128,127,20,18));
    }
    @Test void trackerNeverDoubleCountsOrAcceptsAnotherCellAck() {
        var tracker=new ProjectionScaffoldPolicy.AckTracker();var p=point(100,64,500);
        assertTrue(tracker.begin(p,128,10));
        assertFalse(tracker.begin(point(101,64,500),128,11));
        assertFalse(tracker.acknowledge(point(101,64,500),11));
        assertFalse(tracker.acknowledge(p,9));
        assertTrue(tracker.acknowledge(p,11));
        assertFalse(tracker.acknowledge(p,20));
        assertFalse(tracker.take(p,true,127,18));
        assertTrue(tracker.take(p,true,127,19));
        assertFalse(tracker.pending());
        assertFalse(tracker.take(p,true,127,20));
        assertTrue(tracker.begin(point(101,64,500),127,20));
    }
    @Test void twoPendingWindowUsesExactCumulativeInventoryWithoutSplittingCredit() {
        assertTrue(ProjectionScaffoldPolicy.cumulativeInventoryMatches(128,126,2));
        assertTrue(ProjectionScaffoldPolicy.cumulativeInventoryMatches(128,128,0));
        assertFalse(ProjectionScaffoldPolicy.cumulativeInventoryMatches(128,127,2));
        assertFalse(ProjectionScaffoldPolicy.cumulativeInventoryMatches(128,125,2));
        assertFalse(ProjectionScaffoldPolicy.cumulativeInventoryMatches(128,129,0));
        assertFalse(ProjectionScaffoldPolicy.cumulativeInventoryMatches(-1,0,0));
        assertTrue(ProjectionScaffoldPolicy.windowAvailable(0));
        assertTrue(ProjectionScaffoldPolicy.windowAvailable(1));
        assertFalse(ProjectionScaffoldPolicy.windowAvailable(2));
        assertFalse(ProjectionScaffoldPolicy.windowAvailable(-1));
    }
}
