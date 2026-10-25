package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.HashSet;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class LoadedSpawnerSurveyTest {
    private static JsonObject frame(String world,int generation){
        var f=new JsonObject();f.addProperty("world_session",world);f.addProperty("runtime_generation",generation);
        f.addProperty("runtime_version","test");f.addProperty("connected",true);return f;
    }
    @Test void coversEachBoundedChunkExactlyOnceIncludingNegativeCoordinates(){
        var visited=new HashSet<String>();
        for(int i=0;i<LoadedSpawnerSurvey.CHUNKS;i++){
            int x=LoadedSpawnerSurvey.chunkX(-20,i),z=LoadedSpawnerSurvey.chunkZ(30,i);
            assertTrue(x>=-32&&x<=-8);assertTrue(z>=18&&z<=42);assertTrue(visited.add(x+":"+z));
        }
        assertEquals(625,visited.size());
    }
    @Test void staleAsyncWorldAndRuntimeCannotPublish(){
        assertTrue(LoadedSpawnerSurvey.sameGeneration(frame("w",1),frame("w",1)));
        assertFalse(LoadedSpawnerSurvey.sameGeneration(frame("other",1),frame("w",1)));
        assertFalse(LoadedSpawnerSurvey.sameGeneration(frame("w",2),frame("w",1)));
        assertFalse(LoadedSpawnerSurvey.sameGeneration(new JsonObject(),frame("w",1)));
        var s=frame("w",1);s.addProperty("connected",false);
        assertFalse(LoadedSpawnerSurvey.sameGeneration(s,frame("w",1)));
    }
    @Test void statusMustBeFreshFromThisConnectionAndDimension(){
        assertTrue(LoadedSpawnerSurvey.current(true,1100,500,1000,"s","s","d","d"));
        assertFalse(LoadedSpawnerSurvey.current(true,1100,1001,1000,"s","s","d","d"));
        assertFalse(LoadedSpawnerSurvey.current(true,2101,500,1000,"s","s","d","d"));
        assertFalse(LoadedSpawnerSurvey.current(true,900,500,1000,"s","s","d","d"));
        assertFalse(LoadedSpawnerSurvey.current(false,1100,500,1000,"s","s","d","d"));
        assertFalse(LoadedSpawnerSurvey.current(true,1100,500,1000,"other","s","d","d"));
        assertFalse(LoadedSpawnerSurvey.current(true,1100,500,1000,"s","s","other","d"));
    }
    @Test void enumeratesBlockEntitiesWithoutInputsOrWorldMutation()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/LoadedSpawnerSurvey.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var names=new HashSet<String>();
        for(var method:node.methods)for(var i:method.instructions)if(i instanceof MethodInsnNode call){
            names.add(call.name);
            assertFalse(Set.of("send","attack","interact","useItemOn","setDown","setPos","teleportTo","setBlock",
                    "setHealth","addFreshEntity","startRiding").contains(call.name),call.name);
        }
        assertTrue(names.containsAll(Set.of("getChunk","getBlockEntities","isServerChunk","getBlockEntity")));
    }
}
