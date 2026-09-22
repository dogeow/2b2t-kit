package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BuildSupervisionPolicyTest {
    @Test void supplyRecoveryNeverOverridesManualStopOrChangedJob(){
        assertTrue(BuildSupervisionPolicy.maySupply(true,false,"missing_materials",true));
        for(String outcome:new String[]{"manual_stop","placement_changed","world_changed","complete"})assertFalse(BuildSupervisionPolicy.maySupply(true,false,outcome,true));
        assertFalse(BuildSupervisionPolicy.maySupply(false,false,"missing_materials",true));
        assertFalse(BuildSupervisionPolicy.maySupply(true,true,"missing_materials",true));
    }
    @Test void autoBlockedRoutesCanAcquireSupplyButCannotRestartWithoutAnInventoryGain(){
        assertTrue(BuildSupervisionPolicy.maySupply(true,false,"blocked",true));
        assertFalse(BuildSupervisionPolicy.mayResumeSupply("blocked",false));
        assertTrue(BuildSupervisionPolicy.mayResumeSupply("blocked",true));
        assertFalse(BuildSupervisionPolicy.mayResumeSupply("manual_stop",true));
    }
    @Test void aStoppedOrDifferentJobCannotBeRestartedByModelOutput(){
        for(String action:new String[]{"replan","rescan","pause_and_report","start"}) {
            assertFalse(BuildSupervisionPolicy.mayApply(action,true,false,false,true,true,1000));
            assertFalse(BuildSupervisionPolicy.mayApply(action,false,true,false,true,true,1000));
        }
    }
    @Test void pendingServerPlacementsMustSettleBeforeTravelOrRecount(){
        assertFalse(BuildSupervisionPolicy.mayApply("replan",true,true,false,false,true,1000));
        assertFalse(BuildSupervisionPolicy.mayApply("rescan",true,true,true,true,true,1000));
        assertTrue(BuildSupervisionPolicy.mayApply("pause_and_report",true,true,false,false,true,1000));
    }
    @Test void boundedSafeCorrectionsRequireCooldown(){
        assertTrue(BuildSupervisionPolicy.mayApply("replan",true,true,false,true,true,100));
        assertFalse(BuildSupervisionPolicy.mayApply("replan",true,true,false,true,true,99));
        assertFalse(BuildSupervisionPolicy.mayApply("replan",true,true,false,true,false,1000));
        assertFalse(BuildSupervisionPolicy.mayApply("delete_blocks",true,true,false,true,true,1000));
    }
}
