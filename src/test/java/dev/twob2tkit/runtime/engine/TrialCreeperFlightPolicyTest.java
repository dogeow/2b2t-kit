package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import java.util.UUID;
import static org.junit.jupiter.api.Assertions.*;

class TrialCreeperFlightPolicyTest {
    private final UUID id=UUID.randomUUID();
    private TrialCreeperFlightPolicy.Step step(TrialCreeperFlightPolicy p,int tick,double health,double distance,
                                               double y,boolean aligned,boolean swelling,boolean reach,
                                               boolean cooled,boolean column){
        return p.step(id,tick,0,0,health,distance,y,66,aligned,swelling,reach,cooled,column);
    }
    @Test void forestStartMustFindHighApproachAndNeverDescendsBeforeBeingAboveTheCreeper(){
        var p=new TrialCreeperFlightPolicy();
        assertEquals(TrialCreeperFlightPolicy.Decision.HIGH_APPROACH,step(p,0,20,8,63,false,false,false,true,false).decision());
        assertEquals(TrialCreeperFlightPolicy.Decision.HIGH_APPROACH,step(p,50,20,9,74,false,false,false,true,true).decision());
        assertEquals(TrialCreeperFlightPolicy.Decision.DESCEND,step(p,100,20,8,74,true,false,false,true,true).decision());
    }
    @Test void strikeRiseQuietThenDescendRequiresActualDistanceNotMerelyThreeFeetClearance(){
        var p=new TrialCreeperFlightPolicy();step(p,0,20,8,74,true,false,false,true,true);
        assertEquals(TrialCreeperFlightPolicy.Decision.ATTACK,step(p,50,20,3.1,69.1,true,false,true,true,true).decision());
        p.attacked();
        assertEquals(TrialCreeperFlightPolicy.Decision.HIGH_APPROACH,step(p,51,20,3.1,69.1,true,false,true,true,true).decision());
        assertEquals(TrialCreeperFlightPolicy.Decision.HIGH_APPROACH,step(p,90,16,7.4,73.4,true,false,false,true,true).decision());
        assertEquals(TrialCreeperFlightPolicy.Decision.HIGH_APPROACH,step(p,94,16,7.8,73.8,true,true,false,true,true).decision());
        assertEquals(TrialCreeperFlightPolicy.Decision.DESCEND,step(p,100,16,7.8,73.8,true,false,false,true,true).decision());
    }
    @Test void aChangingColumnAndTargetPositionForbidBlindDescent(){
        var p=new TrialCreeperFlightPolicy();step(p,0,20,8,74,true,false,false,true,true);
        assertEquals(TrialCreeperFlightPolicy.Decision.HIGH_APPROACH,step(p,1,20,8,74,false,false,false,true,true).decision());
        assertEquals("strike_or_return_column_blocked",step(p,2,20,8,74,true,false,false,true,false).reason());
        assertEquals(TrialCreeperFlightPolicy.Decision.UNAVAILABLE,step(p,3,20,8,74,true,false,false,true,true).decision());
    }
    @Test void attackIntentIsNotProgressButObservedHealthLossRenewsTheShortWindow(){
        var p=new TrialCreeperFlightPolicy();step(p,0,20,8,74,true,false,false,true,true);p.attacked();
        assertEquals("no_confirmed_damage",step(p,240,20,8,74,true,false,false,true,true).reason());
        var q=new TrialCreeperFlightPolicy();step(q,0,20,8,74,true,false,false,true,true);
        assertNotEquals(TrialCreeperFlightPolicy.Decision.UNAVAILABLE,step(q,239,16,8,74,true,false,false,true,true).decision());
        assertNotEquals(TrialCreeperFlightPolicy.Decision.UNAVAILABLE,step(q,400,16,8,74,true,false,false,true,true).decision());
    }
    @Test void menuPausePreservesTheTargetWithoutSpendingItsMovementBudget(){
        var p=new TrialCreeperFlightPolicy();step(p,0,20,8,74,true,false,false,true,true);p.pause(100);
        assertNotEquals(TrialCreeperFlightPolicy.Decision.UNAVAILABLE,step(p,2000,20,8,74,true,false,false,true,true).decision());
        assertEquals("no_confirmed_damage",step(p,2140,20,8,74,true,false,false,true,true).reason());
    }
    @Test void damageCannotRenewTheTotalDurationOrExcessiveTravel(){
        var p=new TrialCreeperFlightPolicy();step(p,0,20,8,74,true,false,false,true,true);
        for(int tick=100;tick<=800;tick+=100)step(p,tick,20-tick/100.0,8,74,true,false,false,true,true);
        assertEquals("time_limit",step(p,801,10,8,74,true,false,false,true,true).reason());
        var q=new TrialCreeperFlightPolicy();step(q,0,20,8,74,true,false,false,true,true);
        assertEquals("travel_limit",q.step(id,1,13,0,20,8,74,66,true,false,false,true,true).reason());
    }
}
