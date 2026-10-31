package dev.twob2tkit.automation;
import net.minecraft.world.InteractionResult;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class VanillaInteractionPolicyTest {
    @Test void onlyTheRealVanillaClientSuccessRequestsAClientSwing(){
        assertTrue(VanillaInteractionPolicy.clientSwingRequired(InteractionResult.SUCCESS));
        for(var result:new InteractionResult[]{InteractionResult.SUCCESS_SERVER,InteractionResult.CONSUME,InteractionResult.PASS,InteractionResult.FAIL,InteractionResult.TRY_WITH_EMPTY_HAND,null})assertFalse(VanillaInteractionPolicy.clientSwingRequired(result));
    }
    @Test void installedVanillaClientContainsTheSameSuccessSwingContract()throws Exception{
        var node=node("/net/minecraft/client/Minecraft.class");boolean source=false,swing=false,client=false;
        for(var method:node.methods)if(method.name.equals("startUseItem"))for(var i:method.instructions){
            if(i instanceof org.objectweb.asm.tree.MethodInsnNode c){source|=c.owner.endsWith("InteractionResult$Success")&&c.name.equals("swingSource");swing|=c.name.equals("swing");}
            if(i instanceof org.objectweb.asm.tree.FieldInsnNode f)client|=f.owner.endsWith("InteractionResult$SwingSource")&&f.name.equals("CLIENT");
        }
        assertTrue(source&&swing&&client);
    }
    @Test void nativeBridgeAddsOneSwingWithoutRepeatingEitherUseBranch()throws Exception{
        var node=node("/dev/twob2tkit/automation/AutomationBridge.class");boolean found=false,protocol=false;
        for(var method:node.methods){var calls=new java.util.ArrayList<org.objectweb.asm.tree.MethodInsnNode>();for(var i:method.instructions){if(i instanceof org.objectweb.asm.tree.MethodInsnNode c)calls.add(c);if(i instanceof org.objectweb.asm.tree.LdcInsnNode v)protocol|="vanilla_interaction_swing_protocol".equals(v.cst);}
            if(calls.stream().anyMatch(c->c.owner.endsWith("VanillaInteractionPolicy")&&c.name.equals("clientSwingRequired"))){found=true;assertEquals(1,calls.stream().filter(c->c.name.equals("swing")).count());assertEquals(1,calls.stream().filter(c->c.name.equals("useItemOn")).count());assertEquals(1,calls.stream().filter(c->c.name.equals("useItem")).count());}
        }assertTrue(found&&protocol);
    }
    private org.objectweb.asm.tree.ClassNode node(String resource)throws Exception{var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream(resource)){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}return node;}
}
