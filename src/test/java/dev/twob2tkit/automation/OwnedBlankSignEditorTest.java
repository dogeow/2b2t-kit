package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class OwnedBlankSignEditorTest {
    private boolean allowed(boolean[] gates,String[] lines,long remaining){return OwnedBlankSignEditor.policy(gates[0],gates[1],gates[2],gates[3],gates[4],gates[5],gates[6],gates[7],gates[8],lines,remaining);}
    private boolean[] good(){return new boolean[]{true,true,true,true,true,true,true,true,true};}
    @Test void exactOwnedNewBlankEditorMayCloseWithinBoundedLifetime(){assertTrue(allowed(good(),new String[]{"","","",""},30_000));assertTrue(allowed(good(),new String[]{"","","",""},1));}
    @Test void everyOwnershipWorldBatchInputPlacementAndInventoryGateIsRequired(){for(int j=0;j<9;j++){var gates=good();gates[j]=false;assertFalse(allowed(gates,new String[]{"","","",""},100),"gate"+j);}}
    @Test void anyDraftIncludingSpacesNullAndMalformedLinesIsPreserved(){for(String value:new String[]{"draft"," ","\t",null})for(int j=0;j<4;j++){var lines=new String[]{"","","",""};lines[j]=value;assertFalse(allowed(good(),lines,100));}assertFalse(allowed(good(),null,100));assertFalse(allowed(good(),new String[]{"","",""},100));}
    @Test void expiredOrInvalidLifetimeNeverCloses(){for(long n:new long[]{0,-1,30_001,Long.MAX_VALUE})assertFalse(allowed(good(),new String[]{"","","",""},n));}
    @Test void currentMinecraftFieldsAndNormalCloseCallbackExist()throws Exception{var type=Class.forName("net.minecraft.client.gui.screens.inventory.AbstractSignEditScreen",false,getClass().getClassLoader());assertEquals(String[].class,type.getDeclaredField("messages").getType());assertEquals("net.minecraft.world.level.block.entity.SignBlockEntity",type.getDeclaredField("sign").getType().getName());assertNotNull(type.getMethod("onClose"));}
    @Test void hostHooksRecoveryBeforeInterfacePauseAndOnlyArmsOnOwnedPrinterStart()throws Exception{
        var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("AutomationBridge.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}boolean before=false,arm=false,clear=false;
        for(var m:node.methods){int hook=-1,pause=-1,k=0;for(var ins:m.instructions){if(ins instanceof org.objectweb.asm.tree.MethodInsnNode call){if(m.name.equals("beforeInput")&&call.owner.endsWith("OwnedBlankSignEditor")&&call.name.equals("closeIfOwned"))hook=k;if(m.name.equals("beforeInput")&&call.name.equals("interfacePaused"))pause=k;arm|=m.name.equals("startOwnedProfessionalPrinter")&&call.owner.endsWith("OwnedBlankSignEditor")&&call.name.equals("arm");clear|=m.name.equals("disconnected")&&call.owner.endsWith("OwnedBlankSignEditor")&&call.name.equals("clear");}k++;}if(m.name.equals("beforeInput"))before=hook>=0&&pause>hook;}assertTrue(before&&arm&&clear);
    }
}
