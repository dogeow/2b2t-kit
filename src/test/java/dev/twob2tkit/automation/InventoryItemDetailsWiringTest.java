package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class InventoryItemDetailsWiringTest {
    @Test void nestedContainerToolsUseTheSameDurabilityAndEnchantmentDetails()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);}
        var details=node.methods.stream().filter(m->m.name.equals("addItemDetails")).findFirst().orElseThrow();
        var keys=new HashSet<String>();var calls=new HashSet<String>();
        for(var instruction:details.instructions){
            if(instruction instanceof LdcInsnNode constant&&constant.cst instanceof String text)keys.add(text);
            if(instruction instanceof MethodInsnNode call)calls.add(call.name);
        }
        assertTrue(keys.containsAll(Set.of("max_stack","durability","max_durability","enchantments","stored_enchantments")));
        assertTrue(calls.containsAll(Set.of("isDamageableItem","getMaxStackSize","getMaxDamage","getDamageValue")));
        var callers=new HashSet<String>();
        for(var method:node.methods)for(var instruction:method.instructions)
            if(instruction instanceof MethodInsnNode call&&call.name.equals("addItemDetails"))callers.add(method.name);
        assertTrue(callers.contains("stack"));
        assertTrue(callers.stream().anyMatch(name->name.startsWith("lambda$stack$")),
            "Shulker preview children must include the same tool fields as directly carried stacks");
    }
}
