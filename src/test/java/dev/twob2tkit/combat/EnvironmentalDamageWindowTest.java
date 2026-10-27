package dev.twob2tkit.combat;

import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class EnvironmentalDamageWindowTest {
    private final Object world=new Object(),player=new Object(),connection=new Object();
    private final Vec3 point=new Vec3(761029.533,8.15,797858.503);
    private boolean observe(EnvironmentalDamageWindow window,long time,float health,boolean environment){
        return window.observe(world,player,connection,time,health,point,true,environment);
    }
    @Test void capturedFireSequenceExitsAboveNineteenInsteadOfWaitingForFourteen(){
        var window=new EnvironmentalDamageWindow();
        assertFalse(observe(window,0,20,false));
        assertFalse(observe(window,1000,19.398079f,true));
        assertTrue(observe(window,3000,19.3f,true));
        assertFalse(observe(window,4000,19f,true));
    }
    @Test void partialRegenerationDoesNotHideRepeatedFire(){
        var window=new EnvironmentalDamageWindow();
        assertFalse(observe(window,0,20,false));
        assertFalse(observe(window,1000,19.4f,true));
        assertFalse(observe(window,1500,19.6f,true));
        assertTrue(observe(window,2000,19f,true));
    }
    @Test void routineMobHitsAndOneIsolatedEnvironmentalHitDoNotRequestExit(){
        var mob=new EnvironmentalDamageWindow();
        assertFalse(observe(mob,0,20,false));assertFalse(observe(mob,1000,19,false));assertFalse(observe(mob,2000,18,false));
        var single=new EnvironmentalDamageWindow();
        assertFalse(observe(single,0,20,false));assertFalse(observe(single,1000,19,true));
        assertFalse(observe(single,5000,19,true));assertFalse(observe(single,6000,18.9f,true));
    }
    @Test void duplicatePacketsOrTicksAreNotDistinctInjuries(){
        var window=new EnvironmentalDamageWindow();observe(window,0,20,false);
        assertFalse(observe(window,1000,19.4f,true));
        for(int i=0;i<20;i++)assertFalse(observe(window,1000,19.4f,true));
        assertFalse(observe(window,1100,19.3f,true));
        assertFalse(observe(window,2000,19.3f,true));
    }
    @Test void actualEscapeOrManualTakeoverClearsTheOldBurnWindow(){
        for(boolean manual:new boolean[]{false,true}){
            var window=new EnvironmentalDamageWindow();observe(window,0,20,false);observe(window,1000,19.4f,true);
            assertFalse(window.observe(world,player,connection,1500,19.4f,manual?point:point.add(2,0,0),!manual,true));
            assertFalse(observe(window,2000,19.3f,true));
        }
    }
    @Test void changedWorldPlayerConnectionOrClockCannotReuseOldInjury(){
        for(int scope=0;scope<4;scope++){
            var window=new EnvironmentalDamageWindow();observe(window,0,20,false);observe(window,1000,19.4f,true);
            assertFalse(window.observe(scope==0?new Object():world,scope==1?new Object():player,
                scope==2?new Object():connection,scope==3?500:2000,19.3f,point,true,true));
        }
    }
    @Test void invalidSnapshotsDoNotBecomeDamageEvidence(){
        var window=new EnvironmentalDamageWindow();observe(window,0,20,false);observe(window,1000,19.4f,true);
        assertFalse(observe(window,2000,Float.NaN,true));
        assertFalse(observe(window,3000,19.3f,true));
        assertFalse(window.observe(world,player,connection,4000,19f,new Vec3(Double.NaN,0,0),true,true));
    }
}
