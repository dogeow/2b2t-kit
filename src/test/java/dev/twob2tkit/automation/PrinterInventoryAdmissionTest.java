package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class PrinterInventoryAdmissionTest {
    private JsonObject request(){var q=new JsonObject();q.addProperty("printer_idle_required",true);return q;}
    private JsonObject printer(boolean enabled,boolean owned){var p=new JsonObject();p.addProperty("enabled",enabled);p.addProperty("owned",owned);return p;}
    @Test void enabledUserModeOrAnotherOwnerCannotBeStoppedByAdmission(){
        var p=printer(true,false);var before=p.deepCopy();assertThrows(IllegalStateException.class,()->PrinterInventoryAdmission.requireIdle(request(),true,p));assertEquals(before,p);
        assertThrows(IllegalStateException.class,()->PrinterInventoryAdmission.requireIdle(request(),true,printer(false,true)));
    }
    @Test void idlePrinterAndAbsentOptionalModAreAllowed(){
        assertDoesNotThrow(()->PrinterInventoryAdmission.requireIdle(request(),true,printer(false,false)));
        assertDoesNotThrow(()->PrinterInventoryAdmission.requireIdle(request(),false,new JsonObject()));
    }
    @Test void unknownModeAndMalformedBooleanAreNotAssumedIdle(){
        assertThrows(IllegalStateException.class,()->PrinterInventoryAdmission.requireIdle(request(),true,new JsonObject()));var q=request();q.addProperty("printer_idle_required","true");assertThrows(IllegalArgumentException.class,()->PrinterInventoryAdmission.requireIdle(q,false,new JsonObject()));
    }
    @Test void oldEnvelopeHasNoNewImplicitRequirement(){
        assertDoesNotThrow(()->PrinterInventoryAdmission.requireIdle(new JsonObject(),true,printer(true,true)));
    }
    @Test void statusAdvertisesTheNewIdleAdmissionProtocol()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){new ClassReader(in).accept(node,0);}
        var snapshot=node.methods.stream().filter(m->m.name.equals("snapshot")&&m.desc.equals("(Lnet/minecraft/client/Minecraft;)Lcom/google/gson/JsonObject;")).findFirst().orElseThrow();
        boolean found=false;for(var i:snapshot.instructions)if(i instanceof LdcInsnNode c&&c.cst.equals("printer_idle_admission_protocol"))found=true;assertTrue(found);
    }
    @Test void nativeGuardPrecedesInventoryCompatibilityAndPrinterStop()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){new ClassReader(in).accept(node,0);}
        int found=0;for(var m:node.methods)for(var i:m.instructions)if(i instanceof MethodInsnNode c&&c.owner.endsWith("/PrinterInventoryAdmission")&&c.name.equals("requireIdle")){
            var next=i.getNext();while(!(next instanceof MethodInsnNode))next=next.getNext();assertEquals("requireReady",((MethodInsnNode)next).name);next=next.getNext();while(!(next instanceof MethodInsnNode))next=next.getNext();assertEquals("stop",((MethodInsnNode)next).name);found++;
        }assertEquals(1,found);
    }
}
