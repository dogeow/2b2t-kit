package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.HashSet;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class LoadedVehicleSurveyTest {
    @Test void staleDisconnectedReplacedOrFutureWorldEvidenceIsRejected(){
        assertTrue(LoadedVehicleSurvey.current(true,2000,1000,1800,"s","s","d","d"));
        assertFalse(LoadedVehicleSurvey.current(false,2000,1000,1800,"s","s","d","d"));
        assertFalse(LoadedVehicleSurvey.current(true,3000,1000,1800,"s","s","d","d"));
        assertFalse(LoadedVehicleSurvey.current(true,2000,1900,1800,"s","s","d","d"));
        assertFalse(LoadedVehicleSurvey.current(true,2000,1000,2100,"s","s","d","d"));
        assertFalse(LoadedVehicleSurvey.current(true,2000,1000,1800,"s","other","d","d"));
        assertFalse(LoadedVehicleSurvey.current(true,2000,1000,1800,"s","s","d","other"));
    }
    @Test void observerReadsPassengerAndLeashIdentityWithoutSendingOrMutatingGameState()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/LoadedVehicleSurvey.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var names=new HashSet<String>();
        for(var method:node.methods)for(var i:method.instructions)if(i instanceof MethodInsnNode call){
            names.add(call.name);
            assertFalse(Set.of("send","attack","interact","interactAt","useItem","useItemOn","setDown","setPos","teleportTo",
                "setLeashedTo","dropLeash","removeLeash","startRiding","stopRiding","setLeashData").contains(call.name),call.name);
        }
        assertTrue(names.containsAll(Set.of("getPassengers","getLeashHolder","isLeashed","getEntity","isServerChunk")));
    }
}
