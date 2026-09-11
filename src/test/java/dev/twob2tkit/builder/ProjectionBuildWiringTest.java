package dev.twob2tkit.builder;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionBuildWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(n,0);}return n.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode c)r.add(c.name);return r;}
    @Test void jobDelegatesPlacementAndPausesItDuringMovement()throws Exception{
        assertTrue(calls(method("builder/ProjectionBuildJob","beginPrinting")).containsAll(List.of("release","hover","start")));
        assertTrue(calls(method("builder/ProjectionBuildJob","move")).containsAll(List.of("pause","noCollision","speed")));
        for(String name:List.of("tick","move","beginPrinting"))assertFalse(calls(method("builder/ProjectionBuildJob",name)).contains("useItemOn"));
    }
    @Test void stoppedJobsRestoreFlightAndReleaseKeys()throws Exception{
        assertTrue(calls(method("builder/ProjectionBuildJob","stop")).containsAll(List.of("stop","release","closeKeepingFlight","close")));
        assertTrue(calls(method("builder/ProjectionBuildJob","pause")).containsAll(List.of("pause","release","hover")));
    }
    @Test void serverUpdatesReachProjectionVerificationAsWellAsConcrete()throws Exception{
        var single=method("mixin/ConcreteBlockUpdatesMixin","kit$concreteBlockUpdate");
        assertEquals(3,calls(single).stream().filter("serverBlock"::equals).count());
        assertTrue(calls(method("mixin/ConcreteBlockUpdatesMixin","kit$concreteSectionUpdate")).contains("buildJob"));
    }
    @Test void persistentPauseGateExistsBeforePrinterProposal()throws Exception{
        var tick=method("automation/ProfessionalPrinter","tick");var names=new ArrayList<String>();
        for(var i:tick.instructions)if(i instanceof FieldInsnNode f)names.add(f.name);
        assertTrue(names.contains("paused"));assertTrue(calls(tick).contains("guardBusy"));
        assertTrue(calls(method("builder/ProjectionBuildJob","tick")).contains("resume"));
    }
}
