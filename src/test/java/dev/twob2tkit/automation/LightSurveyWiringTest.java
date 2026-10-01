package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class LightSurveyWiringTest {
    private MethodNode method(String name)throws Exception{
        var c=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(c,0);
        }
        return c.methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof MethodInsnNode n)r.add(n.name);return r;}
    private List<String> strings(MethodNode m){var r=new ArrayList<String>();for(var i:m.instructions)if(i instanceof LdcInsnNode n&&n.cst instanceof String s)r.add(s);return r;}
    @Test void scanUsesRealLightLayersAndVanillaZombieSpawnPlacement(){
        assertDoesNotThrow(()->{
            var m=method("scanCell");var names=calls(m);
            assertTrue(names.containsAll(List.of("getBrightness","isSpawnPositionOk","getDimensions","makeBoundingBox","noBlockCollision","monsterSpawnBlockLightLimit","sample")));
            assertTrue(strings(m).containsAll(List.of("block_light","sky_light","spawn_block_light","spawn_sky_light","zombie_spawn_floor","zombie_block_light_risk")));
            assertTrue(names.indexOf("isServerChunk")<names.indexOf("getBrightness"));
        });
    }
    @Test void theRealBlockAndSkyEnumsAreBothRead()throws Exception{
        boolean block=false,sky=false;
        for(var i:method("scanCell").instructions)if(i instanceof FieldInsnNode f&&f.owner.equals("net/minecraft/world/level/LightLayer")){
            block|=f.name.equals("BLOCK");sky|=f.name.equals("SKY");
        }
        assertTrue(block);assertTrue(sky);
    }
    @Test void scanEntitiesAreCurrentLoadedRecordsBoundedByTheRequestedBox()throws Exception{
        var m=method("scanEntities");var names=calls(m);
        assertTrue(names.containsAll(List.of("getEntities","getBoundingBox","intersects","getId","getUUID","hasLineOfSight","isBaby")));
        for(String unsupported:List.of("getAge","isInLove","getAgeCooldown","send","requestChunk"))assertFalse(names.contains(unsupported));
        assertTrue(strings(m).containsAll(List.of("id","uuid","type","pos","visible","is_baby")));
        assertFalse(names.contains("distanceToSqr")); // A high player does not impose the snapshot's16-block radius.
    }
    @Test void scanReplyAddsEntityScopeAndLeavesNormalSnapshotRadiusAlone()throws Exception{
        var finish=method("finishScan");assertTrue(calls(finish).contains("scanEntities"));
        assertTrue(strings(finish).containsAll(List.of("scan_entities","scan_entity_scope","light_survey_scope")));
        assertTrue(calls(method("snapshot")).contains("distanceToSqr"));
        assertFalse(calls(method("snapshot")).contains("scanEntities"));
    }
    @Test void lightingSurveyMakesNoWorldOrInventoryMutation()throws Exception{
        for(String name:List.of("scanCell","scanEntities"))for(String mutation:List.of("setBlock","useItemOn","attack","setItem","send","handleContainerInput"))
            assertFalse(calls(method(name)).contains(mutation));
    }
}
