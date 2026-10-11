package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ScanPredictionReportTest {
    @Test void pendingAirCellIsRetainedSeparatelyWithoutOldActionCredit(){
        var report=new ScanPredictionReport();report.observe(7,18,9,true);report.observe(8,18,9,false);
        var result=report.receipt(true,72,72,true,4,4);
        assertTrue(result.get("complete").getAsBoolean());assertEquals(1,result.get("pending_count").getAsInt());
        assertEquals(18,result.getAsJsonArray("pending_positions").get(0).getAsJsonArray().get(1).getAsInt());
        assertEquals(0,result.get("old_action_confirmation_credit").getAsInt());
        assertFalse(result.has("server_confirmed"));
    }
    @Test void partialForeignOrInterruptedReadNeverProvesEmptyPredictions(){
        var report=new ScanPredictionReport();
        assertFalse(report.receipt(false,72,72,true,4,4).get("complete").getAsBoolean());
        assertFalse(report.receipt(true,71,72,true,4,4).get("complete").getAsBoolean());
        assertFalse(report.receipt(true,72,72,false,4,4).get("complete").getAsBoolean());
        assertFalse(report.receipt(true,72,72,true,4,5).get("complete").getAsBoolean());
    }
    @Test void publishedReceiptDoesNotChangeWhenFurtherCellsAreRead(){
        var report=new ScanPredictionReport();var first=report.receipt(true,1,1,true,4,4);
        report.observe(1,2,3,true);assertEquals(0,first.getAsJsonArray("pending_positions").size());
        assertEquals(1,report.receipt(true,1,1,true,4,4).getAsJsonArray("pending_positions").size());
    }
}
