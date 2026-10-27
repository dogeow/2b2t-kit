package dev.twob2tkit.runtime.engine;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.HashSet;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;
class LoadedHostileSurveyTest {
    private static JsonObject frame(String world,int generation){
        var f=new JsonObject();f.addProperty("world_session",world);f.addProperty("runtime_generation",generation);
        f.addProperty("runtime_version","1.8.20");f.addProperty("connected",true);return f;
    }
    @Test void asyncOldWorldOrGenerationCannotPublish(){
        assertTrue(LoadedHostileSurvey.sameGeneration(frame("w",2),frame("w",2)));
        assertFalse(LoadedHostileSurvey.sameGeneration(frame("w",3),frame("w",2)));
        assertFalse(LoadedHostileSurvey.sameGeneration(frame("other",2),frame("w",2)));
        var disconnected=frame("w",2);disconnected.addProperty("connected",false);
        assertFalse(LoadedHostileSurvey.sameGeneration(disconnected,frame("w",2)));
        assertFalse(LoadedHostileSurvey.sameGeneration(new JsonObject(),frame("w",2)));
    }
    @Test void observesServerEntityIdentityAndEquipmentWithoutSendingOrMutatingGameState()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/LoadedHostileSurvey.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var names=new HashSet<String>();
        for(var method:node.methods)for(var i:method.instructions)if(i instanceof MethodInsnNode call){
            names.add(call.name);
            assertFalse(Set.of("send","attack","interact","interactAt","useItem","useItemOn","setDown","setPos","teleportTo",
                    "setHealth","addFreshEntity","setItemSlot","startRiding","stopRiding").contains(call.name),call.name);
        }
        assertTrue(names.containsAll(Set.of("entitiesForRendering","getEntity","isServerChunk","getMainHandItem","getOffhandItem","getItemBySlot")));
    }
    @Test void normalWorldObservationRunsHostileSurvey()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        assertTrue(node.methods.stream().filter(m->m.name.equals("observeWorld"))
                .anyMatch(m->{for(var i:m.instructions)if(i instanceof MethodInsnNode c&&c.owner.endsWith("/LoadedHostileSurvey")&&c.name.equals("tick"))return true;return false;}));
    }
}
