package dev.twob2tkit.automation;

import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.FieldInsnNode;
import org.objectweb.asm.tree.MethodInsnNode;
import org.objectweb.asm.tree.MethodNode;
import static org.junit.jupiter.api.Assertions.*;

class CruiseArrivalWiringTest {
    private static MethodNode method(String resource, String name) throws Exception {
        try (InputStream in = CruiseArrivalWiringTest.class.getClassLoader().getResourceAsStream(resource)) {
            assertNotNull(in);
            ClassNode node = new ClassNode();
            new ClassReader(in).accept(node, 0);
            return node.methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
        }
    }

    @Test void materialNavigationPassesRadiusWithoutWritingUserPreference() throws Exception {
        MethodNode dispatch = method("dev/twob2tkit/automation/AutomationBridge.class", "dispatch");
        boolean exactWithRadius = false;
        for (var instruction : dispatch.instructions) {
            if (instruction instanceof FieldInsnNode field && field.getOpcode() == Opcodes.PUTFIELD
                    && field.owner.equals("dev/twob2tkit/KitConfig") && field.name.equals("arrivalRadius"))
                fail("A temporary route must not alter the persisted user radius");
            if (instruction instanceof MethodInsnNode call && call.name.equals("startExact")
                    && call.desc.endsWith("DDDD)V")) exactWithRadius = true;
        }
        assertTrue(exactWithRadius);
    }

    @Test void completedArrivalIsConsideredBeforeCanopyDetours() throws Exception {
        MethodNode tick = method("dev/twob2tkit/KitController.class", "tick");
        List<String> calls = new ArrayList<>();
        for (var instruction : tick.instructions)
            if (instruction instanceof MethodInsnNode call) calls.add(call.name);
        assertTrue(calls.indexOf("reached") >= 0);
        assertTrue(calls.indexOf("reached") < calls.indexOf("tickCanopyEscape"));
        assertTrue(calls.indexOf("arrive") < calls.indexOf("tickCanopyEscape"));
    }
    @Test void startupRepairsAStaleSubBlockManualRadius() throws Exception {
        MethodNode load = method("dev/twob2tkit/KitConfig.class", "load");
        boolean normalize = false, save = false;
        for (var instruction : load.instructions) if (instruction instanceof MethodInsnNode call) {
            if (call.owner.equals("dev/twob2tkit/cruise/CruiseArrivalPolicy") && call.name.equals("manualRadius")) normalize = true;
            if (call.owner.equals("dev/twob2tkit/KitConfig") && call.name.equals("save")) save = true;
        }
        assertTrue(normalize); assertTrue(save);
    }

    @Test void mapActionUsesLivePlayerHeight() throws Exception {
        MethodNode action = method("dev/twob2tkit/map/XaeroCruiseOption.class", "onAction");
        List<String> calls = new ArrayList<>();
        for (var instruction : action.instructions) {
            if (instruction instanceof FieldInsnNode field && field.name.equals("cruiseY"))
                fail("Map action must not use an earlier stored altitude");
            if (instruction instanceof MethodInsnNode call) calls.add(call.name);
        }
        assertTrue(calls.indexOf("getY") >= 0);
        assertTrue(calls.indexOf("getY") < calls.indexOf("startMapCruise"));
    }

}
