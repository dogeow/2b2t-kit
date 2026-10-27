package dev.twob2tkit.automation;

import com.google.gson.*;
import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class VillagerTradingTest {
    @Test void duplicateResetNeedsBothExplicitIntentAndAnotherVerifiedLockedSource(){
        assertTrue(VillagerTrading.protectUsefulBook(true,false,true));
        assertTrue(VillagerTrading.protectUsefulBook(true,true,false));
        assertFalse(VillagerTrading.protectUsefulBook(true,true,true));
        assertFalse(VillagerTrading.protectUsefulBook(false,false,false));
    }
    @Test void resetNeverDiscardsARequestedBookOrTouchesTradedStaleOrBookHoldingLecterns(){
        assertDoesNotThrow(()->VillagerTrading.requireResetPolicy(true,true,true,true,1,0,false,false,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(true,true,true,true,1,0,false,true,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(true,true,true,true,1,1,false,false,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(true,true,true,true,1,0,true,false,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(true,true,false,true,1,0,false,false,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(true,true,true,true,1,0,false,false,false,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(false,true,true,true,1,0,false,false,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(true,true,true,false,1,0,false,false,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireResetPolicy(true,true,true,true,1,0,false,false,true,false));
    }
    private void select(boolean owned,boolean manual,boolean healthy,boolean empty,int actual,int expected,
                        String observed,String chosen,int index,int count,boolean exhausted){
        VillagerTrading.requireSelection(owned,manual,healthy,empty,actual,expected,observed,chosen,index,count,exhausted);
    }
    @Test void staleOwnerMenuOfferAndStockCannotSendASelection(){
        assertDoesNotThrow(()->select(true,false,true,true,7,7,"abc","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(false,false,true,true,7,7,"abc","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,true,true,true,7,7,"abc","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,false,true,7,7,"abc","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,false,7,7,"abc","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,true,8,7,"abc","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,true,0,0,"abc","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,true,7,7,"changed","abc",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,true,7,7,"","",0,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,true,7,7,"abc","abc",-1,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,true,7,7,"abc","abc",2,2,false));
        assertThrows(IllegalStateException.class,()->select(true,false,true,true,7,7,"abc","abc",0,2,true));
    }
    @Test void lockPurchaseIsExactlyOneLeftPickupAndChecksFullResultAndPayments(){
        assertDoesNotThrow(()->VillagerTrading.requireOneOutput("pickup",0,true,true,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireOneOutput("quick_move",0,true,true,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireOneOutput("pickup",1,true,true,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireOneOutput("pickup",0,false,true,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireOneOutput("pickup",0,true,false,true,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireOneOutput("pickup",0,true,true,false,true));
        assertThrows(IllegalStateException.class,()->VillagerTrading.requireOneOutput("pickup",0,true,true,true,false));
    }
    @Test void fingerprintRetainsEnchantmentsPriceStockAndOrderedOfferIdentity(){
        var a=JsonParser.parseString("[{\"result\":{\"enchantment\":\"mending\",\"level\":1},\"cost\":12,\"uses\":0}]");
        var reordered=JsonParser.parseString("[{\"uses\":0,\"cost\":12,\"result\":{\"level\":1,\"enchantment\":\"mending\"}}]");
        assertEquals(VillagerTrading.fingerprint(a),VillagerTrading.fingerprint(reordered));
        for(String changed:List.of("enchantment","price","stock","order")){
            var b=a.deepCopy().getAsJsonArray();var row=b.get(0).getAsJsonObject();
            switch(changed){
                case "enchantment"->row.getAsJsonObject("result").addProperty("enchantment","binding_curse");
                case "price"->row.addProperty("cost",13);
                case "stock"->row.addProperty("uses",1);
                case "order"->b.add(row.deepCopy());
            }
            assertNotEquals(VillagerTrading.fingerprint(a),VillagerTrading.fingerprint(b));
        }
    }
    @Test void merchantOpeningWaitsForANewStableMenuAndNeverAdoptsAReplacement(){
        var p=new ProcessingMenuOpening();p.begin("trade","MerchantMenu",0);
        assertFalse(p.observe("trade","InventoryMenu",0,1,true));
        assertTrue(p.observe("trade","MerchantMenu",7,10,true));
        assertFalse(p.ready("trade",11));assertTrue(p.ready("trade",12));
        assertFalse(p.observe("trade","MerchantMenu",8,13,true));assertTrue(p.cancelled("trade"));
    }
    @Test void selectionUsesVanillaPacketAndNeverAssignsInventoryOffersOrExperience()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/VillagerTrading.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var select=node.methods.stream().filter(m->m.name.equals("select")).findFirst().orElseThrow();
        var calls=new ArrayList<String>();for(var i:select.instructions)if(i instanceof MethodInsnNode call)calls.add(call.owner+"."+call.name);
        assertTrue(calls.stream().anyMatch(s->s.contains("ServerboundSelectTradePacket.<init>")));
        assertTrue(calls.stream().anyMatch(s->s.endsWith(".send")));
        assertTrue(calls.stream().anyMatch(s->s.endsWith(".requireSelection")));
        assertTrue(calls.stream().anyMatch(s->s.endsWith(".setSelectionHint")),"Vanilla client prediction must select the same server offer");
        for(var method:node.methods)for(var i:method.instructions)if(i instanceof MethodInsnNode call)
            assertFalse(Set.of("setItem","setOffers","setXp","setVillagerXp","setVillagerData","increaseUses","setPos","teleportTo").contains(call.name));
    }
    @Test void surveyReadsOnlyLoadedCurrentEntitiesAndNeverLoadsChunks()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/VillagerTrading.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        var survey=node.methods.stream().filter(m->m.name.equals("loaded")).findFirst().orElseThrow();
        var names=new HashSet<String>();for(var i:survey.instructions)if(i instanceof MethodInsnNode call)names.add(call.name);
        assertTrue(names.containsAll(Set.of("entitiesForRendering","getEntity","isRemoved","isAlive")));
        assertFalse(names.contains("getChunk"));assertFalse(names.contains("setVillagerData"));
    }
}
