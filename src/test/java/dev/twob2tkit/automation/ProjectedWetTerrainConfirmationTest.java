package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;
import static org.junit.jupiter.api.Assertions.*;

class ProjectedWetTerrainConfirmationTest {
    @Test void flowedWaterIsRemovalOnlyForExplicitWaterAwareModes(){
        assertFalse(SingleBlockRemovalPolicy.removed(false,true,false,false));
        assertTrue(SingleBlockRemovalPolicy.removed(false,true,false,false,true));
        assertFalse(SingleBlockRemovalPolicy.removed(false,false,false,false,true));
        assertTrue(SingleBlockRemovalPolicy.removed(true,false,false,false,true));
    }
    @Test void floodedTargetStillNeedsBothServerPacketAndSequenceWithPredictionSettled(){
        var p=new SingleBlockServerConfirmation<String,String>();
        p.begin("world","one","target",s->SingleBlockRemovalPolicy.removed(s.equals("air"),s.equals("water"),false,false,true));
        p.sent("world","one","target",16);p.clientState("world","one","target","water");
        assertTrue(p.hold("world","one","target"),"Stop additional mining after local replacement by water");
        p.serverAck("world","one","target",16);
        assertFalse(p.confirmed("world","one","target","water",false));
        p.serverBlock("world","one","target","water");
        assertFalse(p.confirmed("world","one","target","water",true));
        assertTrue(p.confirmed("world","one","target","water",false));
        p.close("one",true);assertDoesNotThrow(()->p.requireAvailable("world","target"));
    }
    @Test void laterOptInDoesNotRewriteOrClearAnOldUncertainClaim(){
        var p=new SingleBlockServerConfirmation<String,String>();
        p.begin("world","old","target",s->SingleBlockRemovalPolicy.removed(s.equals("air"),s.equals("water"),false,false));
        p.sent("world","old","target",16);p.serverBlock("world","old","target","water");p.serverAck("world","old","target",16);
        assertFalse(p.confirmed("world","old","target","water",false));p.close("old",false);
        assertThrows(IllegalStateException.class,()->p.begin("world","new","target",s->SingleBlockRemovalPolicy.removed(false,s.equals("water"),false,false,true)));
    }
    @Test void compiledBridgePassesTheProjectedModeToTheConfirmationPredicate()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        boolean wired=false;
        for(var method:node.methods)for(var instruction:method.instructions)
            if(instruction instanceof MethodInsnNode call&&call.owner.equals("dev/twob2tkit/automation/SingleBlockMiningConfirmation")&&call.name.equals("begin")&&call.desc.endsWith("ZZZ)V"))wired=true;
        assertTrue(wired,"Guard admission alone must not leave the removal predicate in dry-only mode");
    }
}
