package dev.twob2tkit.runtime.engine;

import java.io.InputStream;
import java.util.HashSet;
import java.util.Set;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import static org.junit.jupiter.api.Assertions.*;

class MagmaFlightEscapeWiringTest {
    private static MethodNode method(String resource, String name) throws Exception {
        try (InputStream in = MagmaFlightEscapeWiringTest.class.getClassLoader().getResourceAsStream(resource)) {
            assertNotNull(in);
            ClassNode node = new ClassNode(); new ClassReader(in).accept(node, 0);
            return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
        }
    }
    @Test void magmaFallbackUsesTheGuardedLiftRatherThanRawFlightToggle() throws Exception {
        MethodNode method=method("dev/twob2tkit/runtime/engine/BorerLiquids.class","handleMagmaBurn");
        Set<String> calls=new HashSet<>();
        for (var i:method.instructions) if(i instanceof MethodInsnNode call) calls.add(call.name);
        assertTrue(calls.contains("tryStart"));
        assertFalse(calls.contains("enableMeteorFlight"));
    }
    @Test void liftChecksHeadroomFluidAndWritesBothVerticalInputs() throws Exception {
        MethodNode method=method("dev/twob2tkit/runtime/engine/MagmaFlightEscape.class","tryStart");
        Set<String> calls=new HashSet<>(),fields=new HashSet<>();
        for (var i:method.instructions) {
            if(i instanceof MethodInsnNode call)calls.add(call.name);
            if(i instanceof FieldInsnNode field)fields.add(field.name);
        }
        assertTrue(calls.containsAll(Set.of("hasChunkAt","getFluidState","noCollision","enableMeteorFlight","input","setDown")));
        assertTrue(fields.containsAll(Set.of("keyJump","keyShift")));
    }
}
