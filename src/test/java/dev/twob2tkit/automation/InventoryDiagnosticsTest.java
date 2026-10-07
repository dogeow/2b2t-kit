package dev.twob2tkit.automation;

import com.google.gson.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InventoryDiagnosticsTest {
    private JsonObject stack(String item,int count,int damage){
        var s=new JsonObject();s.addProperty("item",item);s.addProperty("count",count);s.addProperty("max_stack",64);
        var data=new JsonObject();data.addProperty("id",item);data.addProperty("count",count);data.addProperty("damage",damage);s.add("stack_data",data);return s;
    }
    private JsonObject frame(int source,int carried){
        var frame=new JsonObject();frame.addProperty("id",0);frame.addProperty("type","InventoryMenu");
        frame.addProperty("state_id",1);frame.addProperty("quickcraft_status",0);frame.addProperty("observed_at",10);
        frame.add("cursor",stack(carried==0?"minecraft:air":"minecraft:dark_oak_log",carried,0));
        var slots=new JsonArray();for(int i=0;i<12;i++){
            var row=stack(i==11&&source>0?"minecraft:dark_oak_log":"minecraft:air",i==11?source:0,0);row.addProperty("slot",i);slots.add(row);
        }frame.add("slots",slots);var inventory=new JsonArray();inventory.add(stack(source>0?"minecraft:dark_oak_log":"minecraft:air",source,0));frame.add("inventory",inventory);return frame;
    }
    @Test void timerAndMatchingPredictionsCannotProveServerProcessing(){
        var before=frame(1,0);var after=frame(0,1);
        assertEquals("unknown",InventoryDiagnostics.classify(false,before,after,after,after));
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,after,null,after));
    }
    @Test void actualProcessedPickupRequiresCompleteMatchingFinalState(){
        var before=frame(1,0);var after=frame(0,1);
        assertEquals("confirmed",InventoryDiagnostics.classify(true,before,after,after,after));
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,after,after,before));
    }
    @Test void processedNoEffectIncludesPredictionCorrectedBackToTheOriginalInventory(){
        var before=frame(1,0);var prediction=frame(0,1);
        assertEquals("no_effect",InventoryDiagnostics.classify(true,before,prediction,before,before));
    }
    @Test void anActualDragResetIsNoEffectAndDoesNotManufactureASecondClick(){
        var before=frame(1,0);before.addProperty("quickcraft_status",1);var after=frame(1,0);
        assertEquals("no_effect",InventoryDiagnostics.classify(true,before,after,after,after));
        after.addProperty("quickcraft_status",1);
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,after,after,after));
    }
    @Test void stateIdsAndTimesMayAdvanceWithoutChangingItemSemantics(){
        var before=frame(1,0);var predicted=frame(0,1);var server=predicted.deepCopy();server.addProperty("state_id",5);server.addProperty("observed_at",100);
        assertEquals("confirmed",InventoryDiagnostics.classify(true,before,predicted,server,predicted));
    }
    @Test void itemComponentDisagreementIsUnknownEvenWhenItemAndCountMatch(){
        var before=frame(1,0);var predicted=frame(0,1);var server=predicted.deepCopy();
        server.getAsJsonObject("cursor").getAsJsonObject("stack_data").addProperty("damage",7);
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,predicted,server,server));
    }
    @Test void onlyVirtualRecipeResultMayDifferFromPrediction(){
        var before=frame(1,0);var predicted=frame(0,1);var finalState=predicted.deepCopy();
        var result=stack("minecraft:dark_oak_planks",4,0);result.addProperty("slot",0);finalState.getAsJsonArray("slots").set(0,result);
        assertEquals("confirmed",InventoryDiagnostics.classify(true,before,predicted,finalState,finalState));
        finalState.getAsJsonArray("slots").set(1,stack("minecraft:dark_oak_log",1,0));
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,predicted,finalState,finalState));
    }
    @Test void foreignInventoryChangesAndMenuChangesCannotBeConfirmed(){
        var before=frame(1,0);var predicted=frame(0,1);var server=predicted.deepCopy();
        server.getAsJsonArray("inventory").add(stack("minecraft:diamond",1,0));
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,predicted,server,server));
        server=predicted.deepCopy();server.addProperty("id",3);
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,predicted,server,server));
    }
    @Test void virtualResultExceptionStillRequiresTheTwoFinalSidesToAgree(){
        var before=frame(1,0);var predicted=frame(0,1);var server=predicted.deepCopy();
        server.getAsJsonArray("slots").set(0,stack("minecraft:dark_oak_planks",4,0));
        assertEquals("unknown",InventoryDiagnostics.classify(true,before,predicted,server,predicted));
    }
}
