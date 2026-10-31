package dev.twob2tkit.automation;
import net.minecraft.core.BlockPos;
import net.minecraft.world.InteractionResult;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class BlockInteractionObservationTest {
    private BlockInteractionObservation.Input input(BlockPos p,boolean secondary,boolean forced){return new BlockInteractionObservation.Input("request-1","world-1",p,"before","minecraft:netherite_sword",2,"WEST","UP","useItemOn",90,45,secondary,false,forced,true);}
    @Test void consumedCallPreservesIdentityAndExplicitlyDoesNotClaimServerAcceptance(){
        var r=BlockInteractionObservation.snapshot(input(new BlockPos(4,62,7),false,false),InteractionResult.SUCCESS,"after");
        assertEquals("request-1",r.get("request_id").getAsString());assertEquals("world-1",r.get("world_session").getAsString());
        assertEquals(62,r.getAsJsonArray("pos").get(1).getAsInt());assertTrue(r.get("consumed_action").getAsBoolean());
        assertEquals("before",r.get("state_before").getAsString());assertEquals("after",r.get("state_after_local_call").getAsString());
        assertTrue(r.get("observation_scope").getAsString().contains("not_server_confirmation"));assertFalse(r.has("server_confirmed"));
    }
    @Test void passAndForcedSecondaryUseAreDistinctFromThePhysicalSneakKey(){
        var r=BlockInteractionObservation.snapshot(input(BlockPos.ZERO,true,true),InteractionResult.PASS,"before");
        assertFalse(r.get("consumed_action").getAsBoolean());assertTrue(r.get("secondary_use_active").getAsBoolean());
        assertTrue(r.get("forced_placement_sneak").getAsBoolean());assertFalse(r.get("sneak_key").getAsBoolean());
    }
    @Test void mutableTargetAndMissingResultCannotFabricateLaterEvidence(){
        var p=new BlockPos.MutableBlockPos(1,2,3);var in=input(p,false,false);p.set(9,9,9);
        var r=BlockInteractionObservation.snapshot(in,null,"unavailable");assertEquals(1,r.getAsJsonArray("pos").get(0).getAsInt());
        assertFalse(r.get("result_returned").getAsBoolean());assertTrue(r.get("consumed_action").isJsonNull());
    }
    @Test void nativeBridgeActuallyRecordsTheOneInteractionAndPublishesScopedEvidence()throws Exception{
        var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}
        boolean protocol=false,published=false,wired=false;var keys=new java.util.HashSet<String>();
        for(var method:node.methods){
            var calls=new java.util.ArrayList<org.objectweb.asm.tree.MethodInsnNode>();
            for(var instruction:method.instructions){
                if(instruction instanceof org.objectweb.asm.tree.MethodInsnNode call)calls.add(call);
                if(instruction instanceof org.objectweb.asm.tree.LdcInsnNode value){if(value.cst instanceof String key)keys.add(key);protocol|="block_interaction_observation_protocol".equals(value.cst);published|="last_block_interaction".equals(value.cst);}
            }
            boolean records=calls.stream().anyMatch(c->c.owner.endsWith("BlockInteractionObservation")&&c.name.equals("snapshot"));
            if(records){wired=true;assertEquals(1,calls.stream().filter(c->c.name.equals("useItemOn")).count());assertEquals(1,calls.stream().filter(c->c.name.equals("useItem")).count());}
        }
        assertTrue(protocol&&published&&wired);assertTrue(keys.containsAll(java.util.Set.of("player_secondary_use_active","forced_placement_sneak","player_can_build")));
    }
}
