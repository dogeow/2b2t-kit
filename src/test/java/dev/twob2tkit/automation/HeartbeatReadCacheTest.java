package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class HeartbeatReadCacheTest {
    private JsonObject beat(long time,boolean finished){
        var result=new JsonObject();result.addProperty("time",time);result.addProperty("finished",finished);return result;
    }
    @Test void repeatedTicksReadTheFileAtMostEveryHundredMillisAndDoNotRenewTheStoredTimestamp()throws Exception{
        var cache=new HeartbeatReadCache();var reads=new AtomicInteger();
        var first=cache.read("lease","world","world",1000,()->{reads.incrementAndGet();return beat(990,false);});
        for(long tick:new long[]{1020,1050,1099}){
            var seen=cache.read("lease","world","world",tick,()->{reads.incrementAndGet();return beat(tick,false);});
            assertSame(first,seen);assertEquals(990,seen.get("time").getAsLong());
        }
        assertEquals(1,reads.get());cache.read("lease","world","world",1100,()->{reads.incrementAndGet();return beat(1090,true);});
        assertEquals(2,reads.get());
    }
    @Test void leaseAndBothWorldIdentitiesForceAnImmediateFreshRead()throws Exception{
        var cache=new HeartbeatReadCache();var reads=new AtomicInteger();
        for(var scope:new String[][]{{"a","w","w"},{"b","w","w"},{"b","v","w"},{"b","v","v"}})
            cache.read(scope[0],scope[1],scope[2],1000,()->{reads.incrementAndGet();return beat(1000,false);});
        assertEquals(4,reads.get());
    }
    @Test void finishedEvidenceIsRetainedBetweenFilePollsAndNeverFabricated()throws Exception{
        var cache=new HeartbeatReadCache();cache.read("a","w","w",1000,()->beat(999,true));
        assertTrue(cache.read("a","w","w",1050,()->null).get("finished").getAsBoolean());
        assertNull(cache.read("a","w","w",1100,()->null));
    }
    @Test void failedNewScopeCannotReuseTheOldControllerAndCanRecoverImmediately()throws Exception{
        var cache=new HeartbeatReadCache();cache.read("a","w","w",1000,()->beat(1000,false));
        assertThrows(IOException.class,()->cache.read("b","w","w",1001,()->{throw new IOException("missing");}));
        assertNull(cache.read("b","w","w",1002,()->null));
    }
    @Test void clockReversalForcesNewObservation()throws Exception{
        var cache=new HeartbeatReadCache();cache.read("a","w","w",1000,()->beat(1000,false));
        assertEquals(900,cache.read("a","w","w",900,()->beat(900,false)).get("time").getAsLong());
    }
}
