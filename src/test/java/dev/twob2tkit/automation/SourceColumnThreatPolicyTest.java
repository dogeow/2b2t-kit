package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class SourceColumnThreatPolicyTest {
    private SourceColumnThreatPolicy.Workspace work(boolean enclosed){return new SourceColumnThreatPolicy.Workspace(true,true,true,enclosed,true,true);}
    private SourceColumnThreatPolicy.Threat below(boolean ranged,double clearance){return new SourceColumnThreatPolicy.Threat(true,true,ranged,false,true,clearance);}
    @Test void recordedInvisibleSlimeAndSkeletonBelowAnIntactFloorDoNotBlockEnclosedWork(){
        assertTrue(SourceColumnThreatPolicy.permit(work(true),List.of(below(false,3.77),below(true,7.82))));
    }
    @Test void everyPhysicalAndQuietWorkspaceProofRemainsRequired(){
        for(int failure=0;failure<5;failure++){
            var w=new SourceColumnThreatPolicy.Workspace(failure!=0,failure!=1,failure!=2,true,failure!=3,failure!=4);
            assertFalse(SourceColumnThreatPolicy.permit(w,List.of(below(true,7.82))));
        }
    }
    @Test void exposedUpperWorkNeedsExistingHighClearanceMargins(){
        assertTrue(SourceColumnThreatPolicy.permit(work(false),List.of(below(true,12),below(false,6))));
        assertFalse(SourceColumnThreatPolicy.permit(work(false),List.of(below(true,11.99))));
        assertFalse(SourceColumnThreatPolicy.permit(work(false),List.of(below(false,5.99))));
    }
    @Test void creepersUnsupportedMobsVisibilityAndFloorLevelThreatsStillBlock(){
        for(var t:List.of(new SourceColumnThreatPolicy.Threat(true,false,false,false,true,12),
                new SourceColumnThreatPolicy.Threat(true,true,false,true,true,12),
                new SourceColumnThreatPolicy.Threat(false,true,true,false,true,12)))
            assertFalse(SourceColumnThreatPolicy.permit(work(true),List.of(t)));
    }
    @Test void recordedSameLevelZombieOutsideIntactGlassDoesNotBlockAFullyEnclosedActor(){
        var zombie=new SourceColumnThreatPolicy.Threat(true,true,false,false,false,.90);
        assertTrue(SourceColumnThreatPolicy.permit(work(true),List.of(zombie)));
        assertFalse(SourceColumnThreatPolicy.permit(work(false),List.of(zombie)));
        assertFalse(SourceColumnThreatPolicy.permit(work(true),List.of(new SourceColumnThreatPolicy.Threat(true,true,false,false,false,-.01))));
        assertFalse(SourceColumnThreatPolicy.permit(work(true),List.of(new SourceColumnThreatPolicy.Threat(true,true,false,true,false,.90))));
    }
    @Test void anySingleUnprovedThreatBlocksTheEntireSet(){
        assertFalse(SourceColumnThreatPolicy.permit(work(true),List.of(below(false,6),new SourceColumnThreatPolicy.Threat(true,false,false,false,true,8))));
    }
    @Test void recordedDiagonalCreeperOutside16ActualBlocksIsNotANearThreatToASealedActor(){
        assertTrue(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,false,true,22.4*22.4));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,false,true,16*16));
    }
    @Test void nearVisibleSwellingPoweredAboveOrUnobservedCreepersRemainBlocked(){
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,false,true,15.99*15.99));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(false,true,true,false,false,true,500));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,false,true,false,false,true,500));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,false,false,false,true,500));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,true,true,false,true,500));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,true,true,500));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,false,false,500));
        assertFalse(SourceColumnThreatPolicy.remoteCreeper(true,true,true,false,false,true,Double.NaN));
    }
    @Test void missingOrNonFiniteObservationsAreNeverSeparationProof(){
        assertFalse(SourceColumnThreatPolicy.permit(null,List.of()));assertFalse(SourceColumnThreatPolicy.permit(work(true),null));
        assertFalse(SourceColumnThreatPolicy.permit(work(true),Arrays.asList((SourceColumnThreatPolicy.Threat)null)));
        assertFalse(SourceColumnThreatPolicy.permit(work(true),List.of(below(true,Double.NaN))));
        assertFalse(SourceColumnThreatPolicy.permit(work(true),List.of(below(false,-.1))));
    }
}
