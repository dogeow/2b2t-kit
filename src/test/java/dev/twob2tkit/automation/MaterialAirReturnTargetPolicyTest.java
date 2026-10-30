package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.ClassNode;
import org.objectweb.asm.tree.MethodInsnNode;

final class MaterialAirReturnTargetPolicyTest {
    @Test void elevatedFarmHasTheSameBoundedReturnAsNaturalWater() {
        assertTrue(MaterialAirReturnTargetPolicy.allowed(65.85,69.5,-64,320));
        assertTrue(MaterialAirReturnTargetPolicy.allowed(52,65.5,-64,320));
        assertTrue(MaterialAirReturnTargetPolicy.allowed(150,154,-64,320));
    }
    @Test void returnMustRiseWithinTheExistingSixtyFourBlockLimit() {
        assertFalse(MaterialAirReturnTargetPolicy.allowed(65.85,65.5,-64,320));
        assertFalse(MaterialAirReturnTargetPolicy.allowed(65.85,66.5,-64,320));
        assertTrue(MaterialAirReturnTargetPolicy.allowed(65,129,-64,320));
        assertFalse(MaterialAirReturnTargetPolicy.allowed(65,129.01,-64,320));
    }
    @Test void invalidCoordinatesAndWorldHeadroomCannotArmReturn() {
        for(double v:new double[]{Double.NaN,Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY}) {
            assertFalse(MaterialAirReturnTargetPolicy.allowed(v,69.5,-64,320));
            assertFalse(MaterialAirReturnTargetPolicy.allowed(65,v,-64,320));
        }
        assertFalse(MaterialAirReturnTargetPolicy.allowed(-65,-60,-64,320));
        assertFalse(MaterialAirReturnTargetPolicy.allowed(317,319,-64,320));
        assertFalse(MaterialAirReturnTargetPolicy.allowed(65,69,320,-64));
    }
    @Test void configurationStillRequiresTheVerifiedDryCollisionAndLavaFreeColumn() throws Exception {
        var node=new ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/MaterialAirRoute.class")) {
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var configure=node.methods.stream().filter(v->v.name.equals("configure")).findFirst().orElseThrow();
        var calls=java.util.stream.StreamSupport.stream(configure.instructions.spliterator(),false)
            .filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
        assertTrue(calls.contains("allowed"));assertTrue(calls.contains("clearColumn"));
        assertTrue(calls.contains("isUnderWater"));assertTrue(calls.contains("getHealth"));
        var column=node.methods.stream().filter(v->v.name.equals("clearColumn")).findFirst().orElseThrow();
        var checks=java.util.stream.StreamSupport.stream(column.instructions.spliterator(),false)
            .filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
        assertTrue(checks.contains("getFluidState"));assertTrue(checks.contains("noCollision"));assertTrue(checks.contains("lavaIn"));
    }
}
