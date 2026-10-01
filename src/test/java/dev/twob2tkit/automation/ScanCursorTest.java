package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicLong;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ScanCursorTest {
    @Test void inclusiveOrderRemainsXThenZThenYWithoutDuplicatesAcrossTicks(){
        var scan=new ScanCursor(-2,4,7,-1,5,8);var seen=new ArrayList<ScanCursor.Cell>();
        while(!scan.done())scan.advance(true,new AtomicLong(0)::get,seen::add);
        assertEquals(List.of(new ScanCursor.Cell(-2,4,7),new ScanCursor.Cell(-2,5,7),
            new ScanCursor.Cell(-2,4,8),new ScanCursor.Cell(-2,5,8),
            new ScanCursor.Cell(-1,4,7),new ScanCursor.Cell(-1,5,7),
            new ScanCursor.Cell(-1,4,8),new ScanCursor.Cell(-1,5,8)),seen);
    }
    @Test void detailedAndPlainBatchesRespectTheirHardCaps(){
        for(boolean details:new boolean[]{false,true}){
            var scan=new ScanCursor(0,0,0,49,19,49);var seen=new ArrayList<ScanCursor.Cell>();
            int cap=details?512:2048;assertEquals(cap,scan.advance(details,()->0,seen::add));
            assertEquals(cap,scan.read());assertEquals(cap,seen.size());assertFalse(scan.done());
        }
    }
    @Test void fiftyThousandCellsRemainCompleteAndOrderedAfterAllBudgetSlices(){
        var scan=new ScanCursor(0,0,0,49,19,49);var seen=new java.util.HashSet<ScanCursor.Cell>();int batches=0;
        while(!scan.done()){
            int count=scan.advance(true,()->0,cell->assertTrue(seen.add(cell)));assertTrue(count<=512);batches++;
        }
        assertEquals(50_000,seen.size());assertEquals(98,batches);assertEquals(50_000,scan.read());
    }
    @Test void timeBudgetYieldsButStillAllowsOneCellOfProgress(){
        var scan=new ScanCursor(0,0,0,10,0,0);var clock=new AtomicLong();var seen=new ArrayList<ScanCursor.Cell>();
        assertEquals(1,scan.advance(false,()->clock.getAndAdd(3_000_000),seen::add));
        assertEquals(1,seen.size());assertEquals(1,scan.read());
    }
    @Test void smallScanCanCompleteWithinOneClientTick(){
        var scan=new ScanCursor(0,0,0,2,2,2);assertEquals(27,scan.advance(true,()->0,cell->{}));assertTrue(scan.done());
    }
    @Test void failingWorldReadRetainsEarlierRecordsAndDoesNotCreditTheFailedCell(){
        var scan=new ScanCursor(0,0,0,5,0,0);var seen=new ArrayList<ScanCursor.Cell>();
        assertThrows(IllegalStateException.class,()->scan.advance(false,()->0,cell->{
            if(cell.x()==3)throw new IllegalStateException("chunk unloaded");seen.add(cell);
        }));
        assertEquals(3,scan.read());assertEquals(3,seen.size());assertFalse(scan.done());
    }
    @Test void invalidAndOverflowingInclusiveVolumesAreRejected(){
        assertThrows(IllegalArgumentException.class,()->new ScanCursor(0,0,0,50,19,49));
        assertThrows(IllegalArgumentException.class,()->new ScanCursor(1,0,0,0,0,0));
        assertThrows(IllegalArgumentException.class,()->new ScanCursor(Integer.MIN_VALUE,0,0,Integer.MAX_VALUE,0,0));
    }
}
