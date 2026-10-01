package dev.twob2tkit.material;

import dev.twob2tkit.UiFeature;
import java.util.*;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class CaretakerWiringTest {
    private MethodNode method(String cls,String name)throws Exception{
        var type=new ClassNode();try(var input=getClass().getResourceAsStream("/dev/twob2tkit/"+cls+".class")){assertNotNull(input);new ClassReader(input).accept(type,0);}
        return type.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method){var result=new ArrayList<String>();for(var n:method.instructions)if(n instanceof MethodInsnNode m)result.add(m.owner+"."+m.name);return result;}
    @Test void productionFeatureHasNormalFormAndOpeningNeverStartsAutomation()throws Exception{
        assertEquals(UiFeature.Category.PRODUCTION,UiFeature.CARETAKER.category);
        assertTrue(UiFeature.visible(UiFeature.Category.PRODUCTION,"",null).contains(UiFeature.CARETAKER));
        assertFalse(UiFeature.visible(UiFeature.Category.HOME,"",null).contains(UiFeature.CARETAKER));
        var c=calls(method("material/CaretakerPages","open"));assertTrue(c.contains("dev/twob2tkit/KitFormScreen.id"));
        assertFalse(c.contains("dev/twob2tkit/material/CaretakerJobs.start"));
    }
    @Test void launchClosesUiAndWaitsForNewStateBeforeAnyProcessOrLeaseAction()throws Exception{
        var c=calls(method("material/CaretakerJobs","prepare"));
        assertTrue(c.containsAll(List.of("dev/twob2tkit/automation/AutomationBridge.materialJobContext","dev/twob2tkit/material/CaretakerProtocol.requireUnlocked","dev/twob2tkit/material/CaretakerProtocol.requireReady","net/minecraft/client/Minecraft.setScreen")));
        assertFalse(c.contains("dev/twob2tkit/material/MaterialWorkerProcess.start"));
        c=calls(method("material/CaretakerJobs","tick"));assertTrue(c.indexOf("dev/twob2tkit/material/CaretakerProtocol.requireReady")<c.indexOf("dev/twob2tkit/material/MaterialWorkerProcess.start"));
        assertFalse(c.stream().anyMatch(name->name.contains("Runtime.exec")||name.endsWith(".armPveGuard")||name.endsWith(".emergencyStop")));
    }
    @Test void pauseAndStopRequireConfirmedLiveWorkerAndDoNotChangeTheSavedJournalState()throws Exception{
        var c=calls(method("material/CaretakerJobs","control"));
        assertTrue(c.indexOf("dev/twob2tkit/material/CaretakerJobs.running")<c.indexOf("dev/twob2tkit/material/CaretakerProtocol.control"));
        assertFalse(c.stream().anyMatch(name->name.endsWith(".start")||name.endsWith(".stopImmediately")));
    }
    @Test void exactHandleEmergencyAndWorldLifecycleRemainHookedAndMaterialStartIsMutuallyExclusive()throws Exception{
        assertTrue(calls(method("KitClient","stopAll")).contains("dev/twob2tkit/material/CaretakerJobs.stopImmediately"));
        assertTrue(calls(method("KitClient","onEndTick")).contains("dev/twob2tkit/material/CaretakerJobs.tick"));
        assertTrue(calls(method("material/MaterialJobs","start")).contains("dev/twob2tkit/material/CaretakerJobs.occupied"));
        assertTrue(calls(method("material/CaretakerJobs","prepare")).contains("dev/twob2tkit/material/MaterialJobs.running"));
        var c=calls(method("material/CaretakerJobs","stopImmediately"));assertTrue(c.contains("dev/twob2tkit/material/MaterialWorkerProcess.stop"));assertFalse(c.stream().anyMatch(name->name.endsWith(".allProcesses")));
    }
}
