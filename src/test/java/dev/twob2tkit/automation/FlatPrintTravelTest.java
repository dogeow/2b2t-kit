package dev.twob2tkit.automation;

import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class FlatPrintTravelTest {
    @Test void walkingCanContinueDuringAnAcknowledgementIfTheClickStaysReachable(){
        var eye=new Vec3(0,2.14,0);var hit=new Vec3(2,0,0);
        assertTrue(FlatPrintTravel.keepsReach(eye,new Vec3(.24,0,0),hit));
        assertTrue(FlatPrintTravel.keepsReach(eye,new Vec3(-.24,0,0),hit));
    }
    @Test void movingAwayFromThePendingClickStopsBeforeLeavingReach(){
        var eye=new Vec3(0,2.14,0);var hit=new Vec3(3.35,0,0);
        assertTrue(FlatPrintTravel.keepsReach(eye,new Vec3(.24,0,0),hit));
        assertFalse(FlatPrintTravel.keepsReach(eye,new Vec3(-.24,0,0),hit));
    }
    @Test void onlyFlatTravelMayRunThePrinter(){
        assertTrue(FlatPrintTravel.horizontal(new Vec3(.24,0,0)));
        assertTrue(FlatPrintTravel.horizontal(new Vec3(0,.02,.1)));
        assertFalse(FlatPrintTravel.horizontal(new Vec3(.24,.1,0)));
        assertFalse(FlatPrintTravel.horizontal(new Vec3(0,1,0)));
        assertFalse(FlatPrintTravel.horizontal(Vec3.ZERO));
        assertFalse(FlatPrintTravel.horizontal(new Vec3(Double.NaN,0,0)));
    }
    @Test void absentPendingClickDoesNotRequireStoppingButInvalidMotionDoes(){
        assertTrue(FlatPrintTravel.keepsReach(new Vec3(0,2,0),new Vec3(.24,0,0),null));
        assertFalse(FlatPrintTravel.keepsReach(Vec3.ZERO,new Vec3(1,0,0),null));
        assertFalse(FlatPrintTravel.keepsReach(Vec3.ZERO,new Vec3(Double.NaN,0,0),null));
        assertFalse(FlatPrintTravel.keepsReach(Vec3.ZERO,Vec3.ZERO,new Vec3(Double.POSITIVE_INFINITY,0,0)));
    }
}
