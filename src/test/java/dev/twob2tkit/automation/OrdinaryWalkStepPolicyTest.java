package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class OrdinaryWalkStepPolicyTest {
    @Test void slabAndSingleBlockStepsAreAllowed(){assertTrue(OrdinaryWalkStepPolicy.boundedStep(201.5,202));assertTrue(OrdinaryWalkStepPolicy.boundedStep(64.1,65.1));}
    @Test void staleFarmRestoreCannotDisableFlightAfterDefensiveRise(){assertFalse(OrdinaryWalkStepPolicy.boundedStep(222.2,201.5));}
    @Test void evenUpwardLargeStepsNeedAnotherNavigationPrimitive(){assertFalse(OrdinaryWalkStepPolicy.boundedStep(64,70));}
    @Test void normalJumpFitsEnvelope(){assertTrue(OrdinaryWalkStepPolicy.withinEnvelope(64,63,65.26));}
    @Test void defensiveRiseDuringWalkRequiresFlightBraking(){assertFalse(OrdinaryWalkStepPolicy.withinEnvelope(202,201.5,222.2));}
    @Test void leavingFloorDuringWalkRequiresFlightBraking(){assertFalse(OrdinaryWalkStepPolicy.withinEnvelope(202,201.5,199.9));}
    @Test void negativeWorldHeightWorks(){assertTrue(OrdinaryWalkStepPolicy.boundedStep(-40.5,-40));assertTrue(OrdinaryWalkStepPolicy.withinEnvelope(-40.5,-40,-40.25));}
    @Test void nonFiniteInputIsNeverSafe(){for(double bad:new double[]{Double.NaN,Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY}){assertFalse(OrdinaryWalkStepPolicy.boundedStep(bad,64));assertFalse(OrdinaryWalkStepPolicy.boundedStep(64,bad));assertFalse(OrdinaryWalkStepPolicy.withinEnvelope(bad,64,64));assertFalse(OrdinaryWalkStepPolicy.withinEnvelope(64,bad,64));assertFalse(OrdinaryWalkStepPolicy.withinEnvelope(64,64,bad));}}
}
