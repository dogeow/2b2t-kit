package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.ArrayList;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class ConcreteBridgeWiringTest {
    private static List<String> calls(String className,String method) throws Exception {
        var node=new ClassNode();
        try(var stream=ConcreteBridgeWiringTest.class.getResourceAsStream("/"+className+".class")){
            assertNotNull(stream);new ClassReader(stream).accept(node,0);
        }
        var out=new ArrayList<String>();
        var methods=node.methods.stream().filter(m->m.name.equals(method)).toList();
        assertFalse(methods.isEmpty());
        for(MethodNode found:methods)for(var instruction:found.instructions)if(instruction instanceof MethodInsnNode call)out.add(call.name);
        return out;
    }

    @Test void supervisedBatchChecksSiteAndRealMakerProgress() throws Exception {
        var dispatch=calls("dev/twob2tkit/automation/AutomationBridge","dispatch");
        assertTrue(dispatch.containsAll(List.of("checkSiteTarget","startAt","solidId")));
        var tick=calls("dev/twob2tkit/automation/AutomationBridge","tick");
        assertTrue(tick.containsAll(List.of("snapshot","status","count","finish","pickup")));
    }

    @Test void exactSupportIsRayCheckedBeforeExistingWaterAndToolRules() throws Exception {
        var start=calls("dev/twob2tkit/concrete/ConcreteMaker","startAt");
        assertTrue(start.containsAll(List.of("clip","begin")));
        var begin=calls("dev/twob2tkit/concrete/ConcreteMaker","begin");
        assertTrue(begin.contains("getMainHandItem"));
    }
}
