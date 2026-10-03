package dev.twob2tkit.storage;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class NearbyInventoryWiringTest {
    private ClassNode node(String name)throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/"+name+".class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);}return node;
    }
    private List<MethodInsnNode> calls(String name)throws Exception{
        var result=new ArrayList<MethodInsnNode>();for(var method:node(name).methods)for(var i:method.instructions)
            if(i instanceof MethodInsnNode call)result.add(call);return result;
    }
    @Test void warehouseFooterOpensTheSubpageAndItUsesComparisonColumnsAndLiveBackpackReads()throws Exception{
        assertTrue(calls("KitRecordPages").stream().anyMatch(c->c.owner.endsWith("NearbyInventoryScreen")&&c.name.equals("open")));
        assertTrue(calls("storage/NearbyInventoryScreen").stream().anyMatch(c->c.name.equals("comparisonColumns")));
        assertTrue(calls("storage/NearbyInventoryScreen").stream().anyMatch(c->c.name.equals("refreshWhen")));
        var names=calls("storage/NearbyInventoryScreen$View").stream().map(c->c.name).toList();
        assertTrue(names.containsAll(List.of("getInventory","getItem","getContainerSize","summarize")));
    }
    @Test void nearbyInventoryEntryBelongsToStorageNotSavedPlaces()throws Exception{
        var pages=node("KitRecordPages");
        var storage=pages.methods.stream().filter(m->m.name.equals("storage")).findFirst().orElseThrow();
        var places=pages.methods.stream().filter(m->m.name.equals("places")).findFirst().orElseThrow();
        boolean label=false,callback=false;
        for(var instruction:storage.instructions){
            if(instruction instanceof LdcInsnNode ldc&&"附近物资".equals(ldc.cst))label=true;
            if(instruction instanceof InvokeDynamicInsnNode dynamic)
                for(var arg:dynamic.bsmArgs)if(arg instanceof Handle handle){
                    var target=pages.methods.stream().filter(m->m.name.equals(handle.getName())).findFirst();
                    if(target.isPresent())for(var call:target.get().instructions)
                        if(call instanceof MethodInsnNode invoke&&invoke.owner.endsWith("NearbyInventoryScreen")&&invoke.name.equals("open"))callback=true;
                }
        }
        assertTrue(label);assertTrue(callback);
        for(var instruction:places.instructions)
            if(instruction instanceof LdcInsnNode ldc)assertNotEquals("附近物资",ldc.cst);
    }
    @Test void accountingAndSourceDetailsNeverOpenWorldContainersOrStartSupplyAutomation()throws Exception{
        for(String name:List.of("storage/NearbyInventory","storage/NearbyInventoryScreen","storage/NearbyInventoryScreen$View"))
            for(var call:calls(name)){
                assertFalse(Set.of("useItemOn","handleContainerInput","recordSnapshot","usable").contains(call.name),name+" "+call.name);
                assertFalse(call.owner.endsWith("BuildSupplyTask"));
            }
        assertTrue(calls("storage/StorageLifecycle").stream().anyMatch(c->c.name.equals("getUUID")));
    }
    @Test void fixedColumnsAreRenderedAsSeparateValuesAlongsideVisibleMetadata()throws Exception{
        var row=node("KitCollectionScreen$Items$Entry");var fields=new HashSet<String>();
        for(var method:row.methods)if(method.name.equals("extractContent"))for(var i:method.instructions)
            if(i instanceof FieldInsnNode field)fields.add(field.name);
        assertTrue(fields.containsAll(List.of("actualColumn","cachedColumn")));
        assertTrue(calls("KitCollectionScreen$Items$Entry").stream().anyMatch(c->c.name.equals("summaryText")));
    }
}
