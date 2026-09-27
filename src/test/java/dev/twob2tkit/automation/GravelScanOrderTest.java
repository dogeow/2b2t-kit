package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.HashSet;
import static org.junit.jupiter.api.Assertions.*;

class GravelScanOrderTest {
    @Test void scansFromCenterWithoutDuplicatesOrGaps() {
        int radius=7,lastRing=-1;
        var positions=new HashSet<String>();
        for(int i=0;i<GravelScanOrder.size(radius);i++){
            var p=GravelScanOrder.at(i);
            assertEquals(Math.max(Math.abs(p.x()),Math.abs(p.z())),p.ring());
            assertTrue(p.ring()>=lastRing);
            assertTrue(p.ring()<=radius);
            assertTrue(positions.add(p.x()+","+p.z()));
            lastRing=p.ring();
        }
        assertEquals(225,positions.size());
        assertEquals("0,0",GravelScanOrder.at(0).x()+","+GravelScanOrder.at(0).z());
        assertEquals(1,GravelScanOrder.at(8).ring());
        assertEquals(2,GravelScanOrder.at(9).ring());
        assertThrows(IllegalArgumentException.class,()->GravelScanOrder.at(-1));
    }
}
