package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ProfessionalPrintOwnershipHandoffTest {
 @Test void currentMaterialRevisionIsSynchronizedBeforeTheActiveRequestIsCopied()throws Exception{
  var cls=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
   assertNotNull(in);new ClassReader(in).accept(cls,0);
  }
  var method=cls.methods.stream().filter(m->m.name.equals("startOwnedProfessionalPrinter")).findFirst().orElseThrow();
  var calls=new ArrayList<String>();
  for(var i:method.instructions)if(i instanceof MethodInsnNode c){
   assertFalse(c.owner.equals("dev/twob2tkit/KitClient")&&c.name.equals("stopWork"));calls.add(c.name);
  }
  assertTrue(calls.indexOf("currentMaterialRequest")>=0&&calls.indexOf("currentMaterialRequest")<calls.indexOf("stopWorkForScript"));
  assertTrue(calls.indexOf("stopWorkForScript")<calls.indexOf("start"));
  assertTrue(calls.indexOf("stopWorkForScript")<calls.indexOf("deepCopy"));
  assertTrue(cls.methods.stream().filter(m->m.name.equals("dispatch")).flatMap(m->java.util.Arrays.stream(m.instructions.toArray()))
   .anyMatch(i->i instanceof MethodInsnNode c&&c.name.equals("startOwnedProfessionalPrinter")));
 }
}
