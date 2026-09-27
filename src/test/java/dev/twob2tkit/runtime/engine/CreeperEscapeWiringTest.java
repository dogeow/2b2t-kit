package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class CreeperEscapeWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode c)r.add(c.name);return r;}
    @Test void defenseYieldsMovementWithoutPretendingTheUserChangedTasks()throws Exception{
        var c=calls(method("runtime/engine/BorerRangedCombat","evadeCreeper"));
        assertFalse(c.contains("prepareForBorer"));
        assertTrue(c.indexOf("pauseGuardMovement")<c.indexOf("acquire"));assertTrue(c.indexOf("pauseGuardMovement")<c.indexOf("setDown"));
        assertFalse(c.contains("attack"));assertFalse(c.contains("prepareRelease"));
        var host=calls(method("KitClient","tickNavigation"));
        assertTrue(host.indexOf("beforeGuard")<host.indexOf("pauseForDefense"));
        var pause=calls(method("builder/ProjectionBuildJob","pauseForDefense"));
        assertFalse(pause.contains("hover"));assertFalse(pause.contains("release"));assertFalse(pause.contains("stop"));
    }
    @Test void escapeIsConsideredBeforeMeleeAndBowAndBeforeFoodFreeze()throws Exception{
        var c=calls(method("runtime/engine/BorerRangedCombat","tick"));assertTrue(c.indexOf("evadeCreeper")<c.indexOf("attack"));assertTrue(c.indexOf("evadeCreeper")<c.indexOf("selectBow"));
        var d=calls(method("runtime/engine/DefaultTunnelBorerEngine","tickStandaloneGuard"));assertTrue(d.indexOf("hasCreeperEmergency")<d.indexOf("pauseForEating"));
    }
    @Test void endingGuardReleasesEmergencyFlightLease()throws Exception{
        assertTrue(calls(method("runtime/engine/BorerRangedCombat","end")).contains("releaseControls"));
        assertTrue(calls(method("runtime/engine/BorerRangedCombat","pause")).contains("releaseControls"));
        assertTrue(calls(method("runtime/engine/BorerRangedCombat","releaseControls")).contains("releaseEscape"));
        assertTrue(calls(method("runtime/engine/BorerRangedCombat","releaseEscape")).containsAll(List.of("pauseGuardMovement","closeKeepingFlight","close")));
    }
    @Test void areaYieldsItsFlightBeforeEmergencyEscapeAndDoesNotWaitForFood()throws Exception{
        var combat=calls(method("runtime/engine/BorerRangedCombat","tick"));
        assertTrue(combat.contains("flightDefenseScope"));
        assertTrue(combat.indexOf("yieldFlightForEscape")<combat.indexOf("evadeCreeper"));
        assertTrue(calls(method("runtime/engine/BorerAreaRunner","yieldFlightForEscape"))
            .containsAll(List.of("checkpoint","releaseMovement","closeKeepingFlight")));
        var engine=calls(method("runtime/engine/DefaultTunnelBorerEngine","tick"));
        assertTrue(engine.indexOf("hasCreeperEmergency")<engine.indexOf("pauseForMeteorFood"));
    }
    @Test void blockedAscentRetainsOrdinaryDefenseAndNeverPretendsCombatFinished()throws Exception{
        var fallback=method("runtime/engine/BorerRangedCombat","groundDefenseAfterRiseFailure");
        var linked=calls(fallback);
        assertTrue(linked.containsAll(List.of("releaseEscape","cancelDraw","rangedMode","raiseShield","riseFailureNeedsExit","requestEmergencyExit")));
        assertFalse(linked.contains("end"));assertFalse(linked.contains("clear"));
        var operations=new ArrayList<AbstractInsnNode>();
        for(var instruction:fallback.instructions)if(instruction.getOpcode()>=0)operations.add(instruction);
        assertEquals(Opcodes.ICONST_0,operations.get(operations.size()-2).getOpcode(),"Healthy fallback must fall through to melee/bow defense");
        assertEquals(Opcodes.IRETURN,operations.getLast().getOpcode());
        assertEquals(3,calls(method("runtime/engine/BorerRangedCombat","elevateBeforeCombat")).stream()
            .filter("groundDefenseAfterRiseFailure"::equals).count(),"Ceiling, unavailable flight, and failed flight must all retain defense");
    }
}
