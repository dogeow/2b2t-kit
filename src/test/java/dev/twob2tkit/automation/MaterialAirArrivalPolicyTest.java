package dev.twob2tkit.automation;

import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class MaterialAirArrivalPolicyTest {
    private static final Vec3 HOVER_GRAVITY=new Vec3(0,-.0784000015,0);
    @Test void observedFalseArrivalIsOutsideRequestedRadiusAndStillMoving(){
        Vec3 error=new Vec3(761009-761009.7773465675,72.1-72.3748725518226,797850.5000002448-797850.5783988966);
        assertFalse(MaterialAirArrivalPolicy.inside(error,.25));
        assertFalse(MaterialAirArrivalPolicy.stationary(new Vec3(3.9801130573,0,-.3000874328),new Vec3(.3179803081501339,0,-.02397466931788471)));
        assertFalse(MaterialAirArrivalPolicy.stationary(Vec3.ZERO,new Vec3(.1238266929244593,0,-.00933612534959082)));
    }
    @Test void realDisplacementAndVelocityMustBothBeQuiet(){
        assertTrue(MaterialAirArrivalPolicy.stationary(Vec3.ZERO,HOVER_GRAVITY));
        assertFalse(MaterialAirArrivalPolicy.stationary(new Vec3(0,-.0784,0),HOVER_GRAVITY));
        assertFalse(MaterialAirArrivalPolicy.stationary(new Vec3(.02,0,0),Vec3.ZERO));
        assertFalse(MaterialAirArrivalPolicy.stationary(Vec3.ZERO,new Vec3(0,.2,0)));
        assertFalse(MaterialAirArrivalPolicy.stationary(new Vec3(Double.NaN,0,0),Vec3.ZERO));
    }
    @Test void oneTransientFrameCannotFinishAndRestoredSettingsAreObservedAgain(){
        var settle=new MaterialAirArrivalPolicy.Settlement(.25);
        for(int i=0;i<7;i++)assertEquals(MaterialAirArrivalPolicy.Decision.WAIT,settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY));
        assertFalse(settle.done());
        assertEquals(MaterialAirArrivalPolicy.Decision.RESTORE,settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY));
        assertFalse(settle.done());
        for(int i=0;i<7;i++)assertEquals(MaterialAirArrivalPolicy.Decision.WAIT,settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY));
        assertEquals(MaterialAirArrivalPolicy.Decision.CONFIRMED,settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY));
        assertTrue(settle.done());
    }
    @Test void driftAfterRestoringFlightReacquiresPrecisionInsteadOfWideningArrival(){
        var settle=new MaterialAirArrivalPolicy.Settlement(.25);
        for(int i=0;i<8;i++)settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY);
        assertEquals(MaterialAirArrivalPolicy.Decision.REACQUIRE,settle.observe(new Vec3(.3,0,0),new Vec3(.3,0,0),new Vec3(.1,0,0)));
        assertFalse(settle.done());assertFalse(settle.restored());
        for(int i=0;i<8;i++)settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY);
        assertEquals(2,settle.restorations());
        for(int i=0;i<8;i++)settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY);
        assertTrue(settle.done());
    }
    @Test void repeatedRestorationDriftStopsInsteadOfLoopingForever(){
        var settle=new MaterialAirArrivalPolicy.Settlement(.25);
        for(int round=0;round<3;round++){
            for(int i=0;i<8;i++)settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY);
            if(round<2)assertEquals(MaterialAirArrivalPolicy.Decision.REACQUIRE,settle.observe(new Vec3(.4,0,0),Vec3.ZERO,Vec3.ZERO));
            else assertThrows(IllegalStateException.class,()->settle.observe(new Vec3(.4,0,0),Vec3.ZERO,Vec3.ZERO));
        }
        assertFalse(settle.done());
    }
    @Test void defenseOrMenuPauseDiscardsOldStableSamples(){
        var settle=new MaterialAirArrivalPolicy.Settlement(.25);
        for(int i=0;i<7;i++)settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY);
        settle.pause();assertEquals(0,settle.stableTicks());
        assertEquals(MaterialAirArrivalPolicy.Decision.WAIT,settle.observe(Vec3.ZERO,Vec3.ZERO,HOVER_GRAVITY));
        assertFalse(settle.done());
    }
    @Test void precisionBrakesBeforeTheWaypointAndUsesBoundedNormalFlightInputs(){
        assertTrue(MaterialAirArrivalPolicy.takeOver(new Vec3(2,0,0),Vec3.ZERO,true));
        assertTrue(MaterialAirArrivalPolicy.takeOver(new Vec3(8,0,0),new Vec3(1.3,0,0),true));
        assertTrue(MaterialAirArrivalPolicy.takeOver(new Vec3(30,0,0),Vec3.ZERO,false));
        assertFalse(MaterialAirArrivalPolicy.takeOver(new Vec3(30,0,0),Vec3.ZERO,true));
        assertTrue(MaterialAirArrivalPolicy.motion(new Vec3(0,-20,0)).vertical());
        assertFalse(MaterialAirArrivalPolicy.motion(new Vec3(0,-20,0)).horizontal());
        assertEquals(.08,MaterialAirArrivalPolicy.motion(new Vec3(0,-20,0)).speed());
        assertEquals(.01,MaterialAirArrivalPolicy.motion(new Vec3(.2,0,0)).speed(),1e-12);
        assertTrue(MaterialAirArrivalPolicy.motion(new Vec3(.2,0,0)).horizontal());
        assertFalse(MaterialAirArrivalPolicy.motion(new Vec3(.02,.02,.02)).moving());
        var steep=MaterialAirArrivalPolicy.motion(new Vec3(4,-8,3));
        assertFalse(steep.vertical());assertTrue(steep.horizontal());assertTrue(steep.moving());
        assertTrue(MaterialAirArrivalPolicy.motion(new Vec3(.06,-20,0)).vertical());
        assertFalse(MaterialAirArrivalPolicy.motion(new Vec3(.06,-20,0)).horizontal());
    }
    @Test void observedDescentStartAlignsSmallHorizontalErrorBeforeDescending(){
        Vec3 error=observedDescentStart();
        double horizontal=Math.hypot(error.x,error.z);
        assertEquals(.06808229801409094,horizontal,1e-12);
        assertEquals(-78.96897348378408,error.y,1e-12);
        var motion=MaterialAirArrivalPolicy.motion(error);
        assertTrue(motion.horizontal());assertFalse(motion.vertical());
        assertTrue(motion.speed()*10<horizontal,"Meteor's horizontal step must not cross the target");
    }
    @Test void observedOscillationBrakesHorizontalMotionBeforeFurtherDescent(){
        Vec3 error=observedDescentOscillation();
        double horizontal=Math.hypot(error.x,error.z);
        assertEquals(.7115364034543242,horizontal,1e-12);
        assertEquals(-7.768973483783075,error.y,1e-12);
        var motion=MaterialAirArrivalPolicy.motion(error);
        assertTrue(motion.horizontal());assertFalse(motion.vertical());
        assertTrue(motion.speed()*10<horizontal,"The observed overshoot must converge rather than reverse again");
    }
    @Test void precisionConvergesWithMeteorVelocityStepsAndStillRequiresSettlement(){
        for(Vec3 initial:List.of(observedDescentStart(),observedDescentOscillation(),
                new Vec3(4,-8,3),new Vec3(4,8,3),new Vec3(0,-20,0))){
            Vec3 error=initial;
            var settle=new MaterialAirArrivalPolicy.Settlement(.25);
            int quietTicks=0;
            for(int tick=0;tick<512&&!settle.done();tick++){
                var motion=MaterialAirArrivalPolicy.motion(error);
                assertFalse(motion.horizontal()&&motion.vertical(),"Precision must move on one axis at a time");
                // Current Meteor Velocity mode applies speed * 10 horizontally
                // and speed * 5 vertically when vertical-speed-match is false.
                Vec3 step=Vec3.ZERO;
                double horizontal=Math.hypot(error.x,error.z);
                if(motion.horizontal()){
                    assertTrue(motion.speed()*10<horizontal,"Horizontal correction must not overshoot");
                    step=new Vec3(error.x/horizontal*motion.speed()*10,0,error.z/horizontal*motion.speed()*10);
                }else if(motion.vertical()){
                    assertTrue(horizontal<=.06,"Vertical movement must retain the aligned column");
                    assertTrue(motion.speed()*5<Math.abs(error.y),"Vertical correction must not overshoot");
                    step=new Vec3(0,Math.copySign(motion.speed()*5,error.y),0);
                }else quietTicks++;
                Vec3 next=error.subtract(step);
                assertTrue(Math.hypot(next.x,next.z)<=horizontal+1e-12);
                assertTrue(Math.abs(next.y)<=Math.abs(error.y)+1e-12);
                error=next;
                settle.observe(error,step,motion.moving()?step:HOVER_GRAVITY);
                if(quietTicks<MaterialAirArrivalPolicy.STABLE_TICKS+MaterialAirArrivalPolicy.RESTORED_TICKS)
                    assertFalse(settle.done(),"Arrival still needs quiet observations before and after restoring Flight");
            }
            assertTrue(settle.done(),"Precision did not converge from "+initial);
            assertTrue(MaterialAirArrivalPolicy.inside(error,.25));
            assertEquals(1,settle.restorations());
        }
    }
    private static Vec3 observedDescentStart(){
        return new Vec3(761029.5-761029.4574863483,65.6-144.56897348378408,
            797869.5-797869.4468230433);
    }
    private static Vec3 observedDescentOscillation(){
        return new Vec3(761029.5-761029.9176651334,65.6-73.36897348378307,
            797869.5-797870.0760554572);
    }
    private ClassNode code(String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/"+name+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);}return node;
    }
    @Test void implementationBrakesThroughFlightAndKeysWithoutChangingPlayerPositionOrVelocity()throws Exception{
        var node=code("MaterialAirNavigation");var calls=new HashSet<String>();var keys=new HashSet<String>();
        for(var method:node.methods)for(var instruction:method.instructions){
            if(instruction instanceof MethodInsnNode call){
                calls.add(call.name);
                assertFalse(Set.of("setPos","teleportTo","setDeltaMovement","moveTo").contains(call.name));
            }
            if(instruction instanceof FieldInsnNode field&&method.name.equals("release"))keys.add(field.name);
        }
        assertTrue(calls.containsAll(Set.of("acquire","hover","speed","closeKeepingFlight","setDown","observe")));
        assertTrue(keys.containsAll(Set.of("keyUp","keyDown","keyLeft","keyRight","keyJump","keyShift","keySprint")));
    }
    @Test void bridgeUsesTheStableGateAndClosesItOnEveryFinishOrCancellation()throws Exception{
        var bridge=code("AutomationBridge");
        var tick=bridge.methods.stream().filter(m->m.name.equals("tick")).findFirst().orElseThrow();
        var calls=new HashSet<String>();for(var instruction:tick.instructions)
            if(instruction instanceof MethodInsnNode call&&call.owner.endsWith("MaterialAirNavigation"))calls.add(call.name);
        assertTrue(calls.containsAll(Set.of("observe","done","defensePause")));
        for(String name:List.of("finish","cancelWork")){
            var method=bridge.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
            assertTrue(java.util.stream.StreamSupport.stream(method.instructions.spliterator(),false)
                .anyMatch(i->i instanceof MethodInsnNode call&&call.name.equals("closeMaterialAirNavigation")));
        }
    }
}
