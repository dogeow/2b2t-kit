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
        assertTrue(steep.vertical());assertTrue(steep.horizontal());assertTrue(steep.moving());
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
