package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionBatchWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(c,0);}return c.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode n)r.add(n.name);return r;}
    @Test void nativeCandidatesAreRejectedBeforeGuidesCanQueueActions()throws Exception{
        var m=method("mixin/PrinterCandidateMixin","kit$candidate");var c=calls(m);
        assertTrue(c.containsAll(List.of("owned","observeCandidate","emptyCandidateGuides","setReturnValue")));
        assertTrue(c.indexOf("owned")<c.indexOf("observeCandidate"));assertTrue(c.indexOf("observeCandidate")<c.indexOf("setReturnValue"));
        var annotation=m.visibleAnnotations.stream().filter(a->a.desc.endsWith("/Inject;")).findFirst().orElseThrow();
        int i=annotation.values.indexOf("cancellable");assertTrue(i>=0);assertEquals(Boolean.TRUE,annotation.values.get(i+1));
        assertTrue(calls(method("automation/ProfessionalPrinter","observeCandidate")).contains("projectionBatchAllows"));
    }
    @Test void queuedAndActualInteractionBothRecheckTheTarget()throws Exception{
        assertTrue(calls(method("automation/ProfessionalPrinter","nativeProposalQueued")).contains("projectionBatchAllows"));
        assertTrue(calls(method("automation/ProfessionalPrinter","prepareInteraction")).containsAll(List.of("projectionBatchCurrent","projectionBatchAllows")));
        assertTrue(calls(method("automation/ProfessionalPrinter","allowNativeProposal")).contains("projectionBatchCurrent"));
        assertFalse(calls(method("automation/ProfessionalPrinter","allowNativeProposal")).contains("validateProjectionBatch"));
    }
    @Test void onlyAvailabilityIsFilteredAndFullModelCountsRemainUnfiltered()throws Exception{
        assertTrue(calls(method("builder/ProjectionBuildJob","available")).contains("projectionBatchAllows"));
        for(String name:List.of("load","recount","serverBlock"))assertFalse(calls(method("builder/ProjectionBuildJob",name)).contains("projectionBatchAllows"));
        assertTrue(calls(method("builder/ProjectionBuildJob","tick")).contains("validateProjectionBatch"));
    }
    @Test void invalidationStopsAutomaticPrintingBeforeReset()throws Exception{
        var c=calls(method("automation/AutomationBridge","validateProjectionBatch"));assertTrue(c.indexOf("stop")<c.indexOf("reset"));
        for(String method:List.of("disconnected","afterDisconnectCleanup","cancel","cancelWork"))assertTrue(calls(method("automation/AutomationBridge",method)).contains("reset"));
    }
    @Test void updateChecksLeaseAndExpectedSelectionBeforeReplacingMask()throws Exception{
        var c=calls(method("automation/AutomationBridge","changeProjectionBatch"));
        assertTrue(c.containsAll(List.of("externalMaterialScope","batchGateAvailable","request","buildSelection","loadingReason","schematicWorld","set")));
        assertTrue(c.indexOf("externalMaterialScope")<c.indexOf("set"));assertTrue(c.indexOf("loadingReason")<c.indexOf("set"));
    }
    @Test void modelRequiresLoadedProjectionAndExportsExpectedNotActual()throws Exception{
        var c=calls(method("automation/ProjectionAudit","model"));assertTrue(c.containsAll(List.of("buildSelection","loadingReason","serverChunk","inVisibleLayer","isAir","contentHash")));
        assertFalse(c.contains("scan"));assertFalse(c.contains("projectionBatchAllows"));
    }
    @Test void feetLimitGuardsStationsProposalsAndFinalClicksButNotNormalNavigation()throws Exception{
        assertTrue(calls(method("builder/ProjectionBuildJob","clear")).contains("projectionBatchStationAllowed"));
        assertTrue(calls(method("builder/ProjectionBuildJob","tick")).contains("projectionBatchFeetAllowed"));
        for(String name:List.of("allowNativeProposal","nativeProposalQueued","prepareInteraction"))assertTrue(calls(method("automation/ProfessionalPrinter",name)).contains("projectionBatchFeetAllowed"));
        assertFalse(calls(method("automation/AutomationBridge","airNavigationClear")).contains("projectionBatchFeetAllowed"));
    }

}
