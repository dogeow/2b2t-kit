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
    @Test void stationTargetsRequireLiveSupportWithoutBypassingTheBatchMask()throws Exception{
        var calls=calls(method("builder/ProjectionBuildJob","available"));
        assertTrue(calls.containsAll(List.of("projectionBatchAllows","liveTargetReady")));
        assertTrue(calls.indexOf("projectionBatchAllows")<calls.indexOf("liveTargetReady"));
    }
    @Test void stoppedJobsRestoreFlightAndReleaseKeys()throws Exception{
        assertTrue(calls(method("builder/ProjectionBuildJob","stop")).contains("finishJob"));
        assertTrue(calls(method("builder/ProjectionBuildJob","finishJob")).containsAll(List.of("stop","release","closeKeepingFlight","close")));
        assertTrue(calls(method("builder/ProjectionBuildJob","pause")).containsAll(List.of("pause","release","hover")));
    }
    @Test void serverUpdatesReachProjectionVerificationAsWellAsConcrete()throws Exception{
        var single=method("mixin/ConcreteBlockUpdatesMixin","kit$concreteBlockUpdate");
        var recipients=new HashSet<String>();
        for(var instruction:single.instructions)
            if(instruction instanceof MethodInsnNode call&&call.name.equals("serverBlock"))recipients.add(call.owner);
        assertEquals(5,recipients.size());
        assertTrue(recipients.containsAll(Set.of("dev/twob2tkit/automation/SingleBlockMiningConfirmation",
            "dev/twob2tkit/automation/ProfessionalPrinter","dev/twob2tkit/automation/AutomationBridge",
            "dev/twob2tkit/builder/ProjectionBuildJob")));

        var section=method("mixin/ConcreteBlockUpdatesMixin","kit$concreteSectionUpdate");
        assertTrue(calls(section).contains("buildJob"));
        boolean terrainSectionHook=false;
        for(var instruction:section.instructions)
            if(instruction instanceof InvokeDynamicInsnNode dynamic)
                for(var argument:dynamic.bsmArgs)
                    if(argument instanceof Handle handle
                            && handle.getOwner().equals("dev/twob2tkit/automation/AutomationBridge")
                            && handle.getName().equals("serverBlock"))terrainSectionHook=true;
        assertTrue(terrainSectionHook);
    }
    @Test void persistentPauseGateExistsBeforePrinterProposal()throws Exception{
        var tick=method("automation/ProfessionalPrinter","tick");var names=new ArrayList<String>();
        for(var i:tick.instructions)if(i instanceof FieldInsnNode f)names.add(f.name);
        assertTrue(names.contains("paused"));assertTrue(calls(tick).contains("guardBusy"));
        assertTrue(calls(method("builder/ProjectionBuildJob","tick")).contains("resume"));
    }
    @Test void reloadOnlyWaitsForAnOwnedPrinterAndDiscardsOldSearch()throws Exception{
        var names=calls(method("builder/ProjectionBuildJob","prepareRuntimeReload"));
        assertTrue(names.containsAll(List.of("owned","readyForTravel","stop","release","hover","discardSearch")));
        assertTrue(names.indexOf("owned")<names.indexOf("readyForTravel"));
        assertTrue(calls(method("builder/ProjectionBuildJob","runtimeReloaded")).contains("buildNavigation"));
    }
}
