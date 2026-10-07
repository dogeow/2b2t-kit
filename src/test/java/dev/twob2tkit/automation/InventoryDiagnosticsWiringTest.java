package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class InventoryDiagnosticsWiringTest {
    private ClassNode type(String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/"+name+".class")){assertNotNull(in,name);new ClassReader(in).accept(node,0);}return node;
    }
    private MethodNode method(String type,String name)throws Exception{return type(type).methods.stream().filter(m->m.name.equals(name)).findFirst().orElseThrow();}
    private List<String> calls(MethodNode method){var calls=new ArrayList<String>();for(var i:method.instructions)if(i instanceof MethodInsnNode m)calls.add(m.owner+"."+m.name);return calls;}
    @Test void observationsUseActualMinecraft26_1_2InvocationDescriptors()throws Exception{
        var server=method("net/minecraft/server/network/ServerGamePacketListenerImpl","handleContainerClick");
        long clicked=0;for(var i:server.instructions)if(i instanceof MethodInsnNode m&&m.name.equals("clicked")){
            assertEquals("net/minecraft/world/inventory/AbstractContainerMenu",m.owner);
            assertEquals("(IILnet/minecraft/world/inventory/ContainerInput;Lnet/minecraft/world/entity/player/Player;)V",m.desc);clicked++;
        }assertEquals(1,clicked);
        var client=method("net/minecraft/client/multiplayer/MultiPlayerGameMode","handleContainerInput");
        assertTrue(calls(client).contains("net/minecraft/client/multiplayer/ClientPacketListener.send"));
        assertTrue(type("net/minecraft/network/PacketEncoder").methods.stream().anyMatch(m->m.name.equals("encode")&&m.desc.equals("(Lio/netty/channel/ChannelHandlerContext;Lnet/minecraft/network/protocol/Packet;Lio/netty/buffer/ByteBuf;)V")));
    }
    @Test void serverProcessingIsObservedAroundClickedRatherThanHandlerReturn()throws Exception{
        for(String name:List.of("kit$beforeClick","kit$afterClick")){
            var m=method("dev/twob2tkit/mixin/InventoryServerClickObservationMixin",name);
            assertFalse(calls(m).contains("org/spongepowered/asm/mixin/injection/callback/CallbackInfo.cancel"));
            assertTrue(calls(m).stream().anyMatch(c->c.startsWith("dev/twob2tkit/automation/InventoryDiagnostics.server")));
            var inject=m.visibleAnnotations.getFirst();int atIndex=inject.values.indexOf("at");
            @SuppressWarnings("unchecked") var at=(List<AnnotationNode>)inject.values.get(atIndex+1);
            assertEquals(1,at.size());String text=at.getFirst().values.toString();assertTrue(text.contains("INVOKE"));assertTrue(text.contains("clicked"));
        }
    }
    @Test void readOnlyProbeDispatchPrecedesActionGuardAndStartsNoController()throws Exception{
        var calls=calls(method("dev/twob2tkit/automation/AutomationBridge","dispatch"));
        assertTrue(calls.indexOf("dev/twob2tkit/automation/AutomationBridge.inventoryProbe")<calls.indexOf("dev/twob2tkit/automation/AutomationBridge.guard"));
        var probe=calls(method("dev/twob2tkit/automation/AutomationBridge","inventoryProbe"));
        assertTrue(probe.contains("dev/twob2tkit/automation/InventoryDiagnostics.probe"));
        assertFalse(probe.stream().anyMatch(c->c.contains("handleContainerInput")||c.contains("preemptIdle")||c.contains("SingleplayerTrialRuntime.require")));
    }
    @Test void ordinarySendArgumentIsReturnedAndEncodedObservationNeverSends()throws Exception{
        var observer=method("dev/twob2tkit/mixin/InventoryClientClickObservationMixin","kit$observeClick");
        assertFalse(calls(observer).stream().anyMatch(c->c.endsWith(".send")));assertEquals(org.objectweb.asm.Opcodes.ARETURN,observer.instructions.getLast().getPrevious().getOpcode());
        var encoded=calls(method("dev/twob2tkit/mixin/InventoryEncodedClickObservationMixin","kit$encodedClick"));
        assertTrue(encoded.contains("dev/twob2tkit/automation/InventoryDiagnostics.encoded"));assertFalse(encoded.stream().anyMatch(c->c.endsWith(".send")));
    }
}
