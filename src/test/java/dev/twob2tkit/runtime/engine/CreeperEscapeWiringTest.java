package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class CreeperEscapeWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode c)r.add(c.name);return r;}
    @Test void priorOwnerIsStoppedBeforeEscapeTakesFlightAndMovement()throws Exception{
        var c=calls(method("runtime/engine/BorerRangedCombat","evadeCreeper"));
        assertTrue(c.indexOf("prepareForBorer")<c.indexOf("acquire"));assertTrue(c.indexOf("prepareForBorer")<c.indexOf("setDown"));
        assertFalse(c.contains("attack"));assertFalse(c.contains("prepareRelease"));
        assertTrue(calls(method("KitClient","prepareForBorer")).containsAll(List.of("buildJob","stop")));
    }
    @Test void escapeIsConsideredBeforeMeleeAndBowAndBeforeFoodFreeze()throws Exception{
        var c=calls(method("runtime/engine/BorerRangedCombat","tick"));assertTrue(c.indexOf("evadeCreeper")<c.indexOf("attack"));assertTrue(c.indexOf("evadeCreeper")<c.indexOf("selectBow"));
        var d=calls(method("runtime/engine/DefaultTunnelBorerEngine","tickStandaloneGuard"));assertTrue(d.indexOf("hasCreeperEmergency")<d.indexOf("pauseForEating"));
    }
    @Test void endingGuardReleasesEmergencyFlightLease()throws Exception{
        assertTrue(calls(method("runtime/engine/BorerRangedCombat","end")).contains("releaseEscape"));
        assertTrue(calls(method("runtime/engine/BorerRangedCombat","releaseEscape")).containsAll(List.of("pauseGuardMovement","closeKeepingFlight","close")));
    }
}
