package dev.twob2tkit.automation;

import net.minecraft.core.Direction;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.block.HopperBlock;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class PrinterHopperPredictionTest {
    @BeforeAll static void bootstrap(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    @Test void defaultPlacementCanRepresentAPoweredHopperInTheSchematic(){
        var predicted=Blocks.HOPPER.defaultBlockState().setValue(HopperBlock.FACING,Direction.WEST);
        assertTrue(predicted.getValue(HopperBlock.ENABLED));var goal=predicted.setValue(HopperBlock.ENABLED,false);
        assertTrue(PrinterHopperPrediction.matches(predicted,goal));assertTrue(predicted.getValue(HopperBlock.ENABLED));assertFalse(goal.getValue(HopperBlock.ENABLED));
    }
    @Test void wrongFacingAndWrongBlockAreNeverEquivalent(){
        var goal=Blocks.HOPPER.defaultBlockState().setValue(HopperBlock.FACING,Direction.WEST).setValue(HopperBlock.ENABLED,false);
        assertFalse(PrinterHopperPrediction.matches(goal.setValue(HopperBlock.FACING,Direction.EAST),goal));
        assertFalse(PrinterHopperPrediction.matches(Blocks.DROPPER.defaultBlockState(),goal));assertFalse(PrinterHopperPrediction.matches(goal,Blocks.CHEST.defaultBlockState()));
        assertFalse(PrinterHopperPrediction.matches(null,goal));assertFalse(PrinterHopperPrediction.matches(goal,null));
    }
    @Test void finalServerConfirmationStillRequiresTheSchematicPowerState(){
        var goal=Blocks.HOPPER.defaultBlockState().setValue(HopperBlock.FACING,Direction.WEST).setValue(HopperBlock.ENABLED,false);var predicted=goal.setValue(HopperBlock.ENABLED,true);
        assertTrue(PrinterHopperPrediction.matches(predicted,goal));assertFalse(PrinterStateConfirmation.matches(goal,predicted));assertEquals(goal,PrinterStateConfirmation.placementExpectation(goal,predicted));assertTrue(PrinterStateConfirmation.matches(goal,goal));
    }
    @Test void optionalModIntegrationIsRegisteredInThePackagedClientConfig()throws Exception{
        try(var input=getClass().getResourceAsStream("/twob2tkit.client.mixins.json")){
            assertNotNull(input);var config=com.google.gson.JsonParser.parseReader(new java.io.InputStreamReader(input,java.nio.charset.StandardCharsets.UTF_8)).getAsJsonObject();
            assertTrue(config.getAsJsonArray("client").asList().stream().anyMatch(v->v.getAsString().equals("PrinterGuideHopperStateMixin")));
        }
    }
    @Test void mixinOnlyChangesTheGuideComparisonAndNeverDispatchesAnInteraction()throws Exception{
        var node=new ClassNode();try(var input=getClass().getResourceAsStream("/dev/twob2tkit/mixin/PrinterGuideHopperStateMixin.class")){new ClassReader(input).accept(node,0);}
        var method=node.methods.stream().filter(m->m.name.equals("kit$hopperPrediction")).findFirst().orElseThrow();
        var calls=new java.util.ArrayList<String>();for(var instruction:method.instructions)if(instruction instanceof MethodInsnNode call)calls.add(call.name);
        assertEquals(java.util.List.of("matches","setReturnValue"),calls);
        assertTrue(method.visibleAnnotations.stream().anyMatch(a->a.desc.endsWith("/Inject;")&&a.values.toString().contains("statesEqual(")));
    }
}
