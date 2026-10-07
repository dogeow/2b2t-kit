package dev.twob2tkit.automation;

import com.google.gson.*;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class InventoryTraceTest {
    @Test void repeatedForeignClicksCannotGrowTheTraceWithoutBound(){
        var trace=new InventoryDiagnostics.Trace();
        for(int i=0;i<40;i++)trace.add("encoded",i,false,null,null,null,"","");
        assertEquals(16,trace.snapshot().size());assertEquals(24,trace.dropped());
        assertEquals(24,trace.snapshot().get(0).getAsJsonObject().get("native_sequence").getAsLong());
    }
    @Test void returnedEvidenceIsDetachedAndCallerFramesAreBounded(){
        var trace=new InventoryDiagnostics.Trace();var packet=new JsonObject();packet.addProperty("slot",11);
        var callers=new JsonArray();for(int i=0;i<20;i++)callers.add("example.Handler.method"+i);
        trace.add("encoded",1,true,packet,callers,null,"","");packet.addProperty("slot",99);
        var observed=trace.snapshot();var row=observed.get(0).getAsJsonObject();assertEquals(8,row.getAsJsonArray("caller").size());
        assertEquals(11,row.getAsJsonObject("packet").get("slot").getAsInt());
        row.addProperty("owner","changed");assertEquals("owned",trace.snapshot().get(0).getAsJsonObject().get("owner").getAsString());
    }
    @Test void packetOriginsAreBoundedAndUseActualPacketIdentity(){
        var trace=new InventoryDiagnostics.Trace();var first=new Object();var origin=new JsonArray();origin.add("example.Refill.handle");trace.origin(first,origin);
        for(int i=0;i<30;i++)trace.origin(new Object(),origin);
        var extra=new Object();trace.origin(extra,origin);assertTrue(trace.origin(extra).isEmpty());
        var observed=trace.origin(first);observed.add("mutation");assertEquals(1,trace.origin(first).size());
    }
    @Test void poisonEvidenceContainsOnlyControlledReasonAndExceptionType(){
        var trace=new InventoryDiagnostics.Trace();trace.add("poison",1,false,null,null,null,"foreign_encoded_click","IllegalStateException");
        var row=trace.snapshot().get(0).getAsJsonObject();assertEquals("foreign_encoded_click",row.get("reason").getAsString());
        assertEquals("IllegalStateException",row.get("failure_type").getAsString());assertFalse(row.has("message"));assertFalse(row.has("arguments"));
    }
}
