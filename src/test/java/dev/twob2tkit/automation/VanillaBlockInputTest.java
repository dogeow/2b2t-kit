package dev.twob2tkit.automation;
import com.google.gson.*;
import net.minecraft.core.Direction;
import net.minecraft.world.level.block.*;
import org.junit.jupiter.api.*;
import static org.junit.jupiter.api.Assertions.*;
class VanillaBlockInputTest {
    @BeforeAll static void boot(){net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();}
    @Test void explicitFlagCannotBeImpliedOrCoerced(){assertFalse(VanillaBlockInput.requested(new JsonObject()));assertTrue(VanillaBlockInput.requested(JsonParser.parseString("{\"vanilla_block_input\":true}").getAsJsonObject()));for(String v:new String[]{"1","\"true\"","null","[]"})assertThrows(IllegalArgumentException.class,()->VanillaBlockInput.requested(JsonParser.parseString("{\"vanilla_block_input\":"+v+"}").getAsJsonObject()));}
    @Test void correctSideAndOneOpenAreRequiredForTheExactGoal(){
        var actual=Blocks.SPRUCE_FENCE_GATE.defaultBlockState().setValue(FenceGateBlock.FACING,Direction.EAST).setValue(FenceGateBlock.OPEN,false);
        var goal=actual.setValue(FenceGateBlock.FACING,Direction.WEST).setValue(FenceGateBlock.OPEN,true);
        assertTrue(VanillaGateInputPolicy.reachesGoal(actual,goal,Direction.WEST));assertFalse(VanillaGateInputPolicy.reachesGoal(actual,goal,Direction.EAST));assertFalse(VanillaGateInputPolicy.reachesGoal(goal,goal,Direction.WEST));assertFalse(VanillaGateInputPolicy.reachesGoal(actual,goal.setValue(FenceGateBlock.POWERED,true),Direction.WEST));
        assertFalse(VanillaGateInputPolicy.reachesGoal(Blocks.CHEST.defaultBlockState(),Blocks.CHEST.defaultBlockState(),Direction.WEST));assertFalse(VanillaGateInputPolicy.reachesGoal(actual,Blocks.OAK_FENCE_GATE.defaultBlockState(),Direction.WEST));
    }
    @Test void everyStandardBusyConditionPreventsTheInput(){assertTrue(VanillaGateInputPolicy.ready(false,false,false,false));for(int mask=1;mask<16;mask++)assertFalse(VanillaGateInputPolicy.ready((mask&1)!=0,(mask&2)!=0,(mask&4)!=0,(mask&8)!=0));}
    @Test void realVanillaPickAndUseMethodsAreVoidEntrypoints()throws Exception{
        var c=net.minecraft.client.Minecraft.class;assertEquals(void.class,c.getDeclaredMethod("pick",float.class).getReturnType());assertEquals(void.class,c.getDeclaredMethod("startUseItem").getReturnType());assertEquals(int.class,c.getDeclaredField("rightClickDelay").getType());
    }
    @Test void controlledInputUsesVanillaReflectionWithNoDirectUseOrWorldMutationFallback()throws Exception{
        var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/VanillaBlockInput.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}
        int invokes=0;for(var m:node.methods)if(m.name.equals("perform"))for(var i:m.instructions)if(i instanceof org.objectweb.asm.tree.MethodInsnNode call){if(call.owner.equals("java/lang/reflect/Method")&&call.name.equals("invoke"))invokes++;assertFalse(java.util.Set.of("useItem","useItemOn","setBlock","teleportTo","send").contains(call.name));}assertEquals(2,invokes);
    }
    @Test void missingOwnerCannotInvokeAnyInputHandler(){var receipt=new JsonObject();assertThrows(IllegalStateException.class,()->VanillaBlockInput.perform(null,new JsonObject(),net.minecraft.core.BlockPos.ZERO,Direction.UP,false,receipt));assertFalse(receipt.get("vanilla_input_handler_invoked").getAsBoolean());assertFalse(receipt.get("vanilla_input_handler_returned").getAsBoolean());}
}
