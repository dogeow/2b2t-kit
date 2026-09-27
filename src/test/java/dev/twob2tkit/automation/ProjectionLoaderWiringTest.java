package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionLoaderWiringTest {
    private MethodNode method(String cls,String name)throws Exception{var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/"+cls+".class")){assertNotNull(in);new ClassReader(in).accept(node,0);}return node.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(String cls,String name)throws Exception{var out=new ArrayList<String>();for(var i:method(cls,name).instructions)if(i instanceof MethodInsnNode m)out.add(m.name);return out;}
    private Set<String> strings(String cls,String name)throws Exception{var out=new HashSet<String>();for(var i:method(cls,name).instructions)if(i instanceof LdcInsnNode m&&m.cst instanceof String s)out.add(s);return out;}
    @Test void fileAndPreparedBoundsAreValidatedBeforeExistingProjectionActivation()throws Exception{
        var c=calls("ProjectionLoader","load");assertTrue(c.indexOf("parse")<c.indexOf("prepare"));assertTrue(c.indexOf("decodedSize")<c.indexOf("prepare"));
        assertTrue(c.indexOf("prepare")<c.indexOf("apply"));assertTrue(c.indexOf("write")<c.indexOf("apply"));
        assertTrue(c.containsAll(List.of("rollback","lockedBuildSelection","loadingReason")));
    }
    @Test void bridgeRequiresIdleWorkerPrinterHealthLockAndFreshWorldScope()throws Exception{
        var c=calls("AutomationBridge","projectionLoadScope");assertTrue(c.containsAll(List.of("envelope","anyAfkAuto","snapshot","owned","getHealth","getFoodLevel","isInWater","isOnFire","manualMovementDown","held","scope")));
        assertTrue(strings("AutomationBridge","dispatch").containsAll(Set.of("projection_load","projection_load_rollback")));
        assertTrue(strings("AutomationBridge","snapshot").contains("projection_load_protocol"));
    }
    @Test void publicAdapterOnlyChangesPlacementConfigurationNotBlocksOrSchematicsOnDisk()throws Exception{
        for(String name:List.of("prepare","add","remove","enable","select","save","removeOwnSchematic")){
            var c=calls("ProjectionLoader$Access",name);assertFalse(c.contains("setBlock"));assertFalse(c.contains("useItemOn"));assertFalse(c.contains("startDestroyBlock"));assertFalse(c.contains("writeToFile"));
            var s=strings("ProjectionLoader$Access",name);assertFalse(s.contains("placeToWorld"));assertFalse(s.contains("removeAllPlacementsOfSchematic"));
        }
        assertTrue(strings("ProjectionLoader$Access","prepare").containsAll(Set.of("createFromFile","createFor","setRotation","setMirror","toggleLocked")));
        assertTrue(strings("ProjectionLoader$Access","requireAllLayers").contains("ALL"));
    }
}
