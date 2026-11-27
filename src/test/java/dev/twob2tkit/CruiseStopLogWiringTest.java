package dev.twob2tkit;

import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class CruiseStopLogWiringTest {
    @Test void repeatedWaypointStopsAreDemotedToDebugButStillReleaseKeys() throws Exception {
        var node = new ClassNode();
        try (var in = getClass().getResourceAsStream("/dev/twob2tkit/KitController.class")) { assertNotNull(in); new ClassReader(in).accept(node, 0); }
        var stop = node.methods.stream().filter(m -> m.name.equals("stop") && m.desc.contains("Ljava/lang/String;")).findFirst().orElseThrow();
        var calls = new ArrayList<String>();
        for (var i : stop.instructions) if (i instanceof MethodInsnNode c) calls.add(c.name);
        assertTrue(calls.containsAll(List.of("releaseKeys", "allow", "info", "debug")));
        assertTrue(calls.lastIndexOf("releaseKeys") < calls.indexOf("allow"), "throttling a log line must never skip the key release");
    }
}
