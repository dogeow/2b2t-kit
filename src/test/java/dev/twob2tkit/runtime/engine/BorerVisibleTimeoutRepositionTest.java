package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class BorerVisibleTimeoutRepositionTest {
    @Test void visibleLiveTimeoutCanPlanButCannotAttackUntilVerifiedReposition() {
        var s=new BorerCombatSession<String>();var id=UUID.randomUUID();
        s.beginTick(0);s.observe(id,"live spider",true,false,true,4.59f);
        s.beginTick(600);s.observe(id,"same live spider",true,false,true,4.59f);
        assertFalse(s.canAttack(id));assertTrue(s.needsReposition(id));assertTrue(s.pending());
        assertTrue(s.repositioned(id));assertTrue(s.canAttack(id));assertTrue(s.pending());
        s.beginTick(1200);s.observe(id,"same live spider",true,false,true,4.59f);
        assertTrue(s.needsReposition(id));assertTrue(s.repositioned(id));
        s.beginTick(1800);s.observe(id,"same live spider",true,false,true,4.59f);
        assertFalse(s.needsReposition(id));assertFalse(s.canAttack(id));assertTrue(s.pending());
    }
    @Test void MissingPausedOrDeadObservationDoesNotAuthorizeTimeoutPlanning() {
        var s=new BorerCombatSession<String>();var id=UUID.randomUUID();
        s.beginTick(0);s.observe(id,"spider",true,false,true,4.59f);
        s.beginTick(600);assertFalse(s.needsReposition(id));
        s.observe(id,"visible spider",true,false,true,4.59f);s.pause(600);assertFalse(s.needsReposition(id));
        s.beginTick(601);s.observe(id,"observed death",true,true,false,0);assertFalse(s.pending());assertFalse(s.needsReposition(id));
    }
    @Test void currentlyObservedOutOfRangeTargetCanPlanButCannotAttackOrResetBudgetYet() {
        var s=new BorerCombatSession<String>();var id=UUID.randomUUID();
        s.beginTick(0);s.observe(id,"engaged spider",true,false,true,4.59f);
        s.beginTick(20);s.observe(id,"same live spider outside range before timeout",false,false,false,4.59f);
        assertTrue(s.needsReposition(id));assertFalse(s.canAttack(id));assertFalse(s.repositioned(id));
        s.beginTick(600);s.observe(id,"same spider outside ten blocks",false,false,false,4.59f);
        assertTrue(s.needsReposition(id));assertFalse(s.canAttack(id));assertFalse(s.repositioned(id));
        s.beginTick(601);s.observe(id,"same spider visible within attack range",false,false,true,4.59f);
        assertTrue(s.repositioned(id));assertTrue(s.canAttack(id));assertTrue(s.pending());
    }
    @Test void firingGoalLeavesMarginForArrivalToleranceAndOneBlockWitness() {
        assertFalse(BorerCombatPeek.firingPositionFarEnough(1));
        assertFalse(BorerCombatPeek.firingPositionFarEnough(1.4*1.4));
        assertTrue(BorerCombatPeek.firingPositionFarEnough(1.5*1.5));
        assertFalse(BorerCombatPeek.firingPositionFarEnough(Double.NaN));
    }
}
