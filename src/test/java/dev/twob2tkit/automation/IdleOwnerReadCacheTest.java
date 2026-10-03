package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.LongPredicate;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class IdleOwnerReadCacheTest {
    @TempDir Path root;
    final String service="0123456789abcdefabcd";
    JsonObject lease(){
        var lease=new JsonObject();lease.addProperty("kind","materials");lease.addProperty("id","idle-lease");
        lease.addProperty("job_session","idle-task");lease.addProperty("world_session","world");lease.addProperty("revision",7);
        return lease;
    }
    JsonObject marker()throws IOException{
        var marker=new JsonObject();marker.addProperty("schema",1);marker.addProperty("idle_service_id",service);
        marker.addProperty("world_session","world");marker.addProperty("task_session","idle-task");
        marker.addProperty("lease_id","idle-lease");marker.addProperty("revision",7);marker.addProperty("pid",77);
        marker.addProperty("updated_at",10000);marker.addProperty("input_released",false);
        marker.addProperty("lock_path",lock().toString());return marker;
    }
    Path lock()throws IOException{return root.toRealPath().resolve("idle-services").resolve(service).resolve("worker.lock");}
    void publish(JsonObject marker)throws IOException{
        Files.createDirectories(lock().getParent());if(!Files.exists(lock()))Files.createFile(lock());
        Files.writeString(root.resolve("idle-service-owner.json"),marker.toString());
    }
    IdleOwnerReadCache cache(AtomicInteger reads,LongPredicate alive){
        return new IdleOwnerReadCache((path,lease,world,revision,now)->{
            reads.incrementAndGet();return IdleOwnerReadCache.readFile(path,lease,world,revision,now,alive);
        });
    }
    @Test void statusAndManualProbesSharePositiveAndNegativeObservationsWithinTwoTicks()throws IOException{
        var reads=new AtomicInteger();var processes=new AtomicInteger();publish(marker());
        var cache=cache(reads,pid->{processes.incrementAndGet();return pid==77;});var lease=lease();
        assertNotNull(cache.read(root,lease,"world",7,10,10000));
        for(int i=0;i<5;i++)assertNotNull(cache.read(root,lease,"world",7,10,10000));
        assertNotNull(cache.read(root,lease,"world",7,11,10050));
        assertEquals(1,reads.get());assertEquals(1,processes.get());
        Files.delete(root.resolve("idle-service-owner.json"));
        assertNull(cache.read(root,lease,"world",7,12,10060));
        for(int i=0;i<5;i++)assertNull(cache.readForAction(root,lease,"world",7,12,10060));
        assertEquals(2,reads.get());assertEquals(1,processes.get());
    }
    @Test void wallClockBoundAlsoRefreshesWhenClientTicksDoNotAdvance()throws IOException{
        var reads=new AtomicInteger();publish(marker());var cache=cache(reads,p->true);var lease=lease();
        assertNotNull(cache.read(root,lease,"world",7,10,10000));
        assertNotNull(cache.read(root,lease,"world",7,10,10099));assertEquals(1,reads.get());
        Files.delete(root.resolve("idle-service-owner.json"));
        assertNull(cache.read(root,lease,"world",7,10,10100));assertEquals(2,reads.get());
    }
    @Test void cachedMarkerCannotExtendTheOriginalTwoAndAHalfSecondDeadline()throws IOException{
        var reads=new AtomicInteger();publish(marker());var cache=cache(reads,p->true);var lease=lease();
        assertNotNull(cache.read(root,lease,"world",7,10,12500));
        assertNull(cache.read(root,lease,"world",7,10,12501));
        assertNull(cache.readForAction(root,lease,"world",7,10,12501));assertEquals(1,reads.get());
    }
    @Test void localLeaseRemovalAndEveryOwnerScopeChangeInvalidateImmediatelyInTheSameTick()throws IOException{
        var reads=new AtomicInteger();var marker=marker();publish(marker());var cache=cache(reads,p->true);var lease=lease();
        assertNotNull(cache.read(root,lease,"world",7,10,10000));
        lease.addProperty("id","new-lease");marker.addProperty("lease_id","new-lease");publish(marker);
        assertEquals("new-lease",cache.read(root,lease,"world",7,10,10000).lease());
        lease.addProperty("job_session","new-task");marker.addProperty("task_session","new-task");publish(marker);
        assertEquals("new-task",cache.read(root,lease,"world",7,10,10000).task());
        lease.addProperty("world_session","new-world");marker.addProperty("world_session","new-world");publish(marker);
        assertEquals("new-world",cache.read(root,lease,"new-world",7,10,10000).world());
        lease.addProperty("revision",8);marker.addProperty("revision",8);publish(marker);
        assertEquals(8,cache.read(root,lease,"new-world",8,10,10000).revision());assertEquals(5,reads.get());
        assertNull(cache.read(root,null,"new-world",8,10,10000));assertEquals(5,reads.get());
        assertNotNull(cache.read(root,lease,"new-world",8,10,10000));assertEquals(6,reads.get());
        cache.invalidate();assertNotNull(cache.read(root,lease,"new-world",8,10,10000));assertEquals(7,reads.get());
    }
    @Test void incompatibleNativeOwnershipDoesNotReadAnyFiles()throws IOException{
        var reads=new AtomicInteger();publish(marker());var cache=cache(reads,p->true);var lease=lease();
        assertNull(cache.read(root,null,"world",7,10,10000));
        assertNull(cache.read(root,lease,"foreign",7,10,10000));
        assertNull(cache.read(root,lease,"world",8,10,10000));
        lease.addProperty("kind","parking");assertNull(cache.read(root,lease,"world",7,10,10000));
        lease.addProperty("kind","materials");lease.addProperty("revision",7.5);
        assertNull(cache.read(root,lease,"world",7,10,10000));assertEquals(0,reads.get());
    }
    @Test void actionRefreshRejectsReleasedMarkerEvenWithinTheSameTick()throws IOException{
        var reads=new AtomicInteger();var marker=marker();publish(marker());var cache=cache(reads,p->true);var lease=lease();
        assertNotNull(cache.read(root,lease,"world",7,10,10000));
        marker.addProperty("input_released",true);publish(marker);
        assertNull(cache.readForAction(root,lease,"world",7,10,10000));
        assertNull(cache.read(root,lease,"world",7,10,10000));assertEquals(2,reads.get());
    }
    @Test void actionRefreshCannotInheritAnExternallyChangedIdleOwner()throws IOException{
        var reads=new AtomicInteger();var marker=marker();publish(marker());var cache=cache(reads,p->true);var lease=lease();
        var before=cache.read(root,lease,"world",7,10,10000);assertNotNull(before);
        var request=new JsonObject();request.addProperty("idle_service_id",service);
        request.addProperty("task_session","idle-task");request.addProperty("world_session","world");
        assertTrue(IdleActivityPolicy.requestOwned(before,request));
        String replacement="abcdef0123456789abcd";var replacementLock=root.toRealPath().resolve("idle-services").resolve(replacement).resolve("worker.lock");
        Files.createDirectories(replacementLock.getParent());Files.createFile(replacementLock);
        marker.addProperty("idle_service_id",replacement);marker.addProperty("lock_path",replacementLock.toString());publish(marker);
        var after=cache.readForAction(root,lease,"world",7,10,10000);
        assertNotNull(after);assertEquals(replacement,after.service());assertFalse(IdleActivityPolicy.requestOwned(after,request));
        assertEquals(2,reads.get());
    }
    @Test void everyPositiveActionRefreshRechecksWorkerProcessAndLock()throws IOException{
        var reads=new AtomicInteger();var alive=new AtomicBoolean(true);publish(marker());var cache=cache(reads,p->alive.get());var lease=lease();
        assertNotNull(cache.read(root,lease,"world",7,10,10000));alive.set(false);
        assertNull(cache.readForAction(root,lease,"world",7,10,10000));
        alive.set(true);cache.invalidate();assertNotNull(cache.read(root,lease,"world",7,10,10000));
        Files.delete(lock());assertNull(cache.readForAction(root,lease,"world",7,10,10000));assertEquals(4,reads.get());
    }
    @Test void ioAndParseFailuresDiscardOldOwnerAndCacheOnlyAConservativeNegative()throws IOException{
        var reads=new AtomicInteger();publish(marker());var failing=new AtomicBoolean(false);
        var cache=new IdleOwnerReadCache((path,lease,world,revision,now)->{
            reads.incrementAndGet();if(failing.get())throw new IOException("unavailable");
            return IdleOwnerReadCache.readFile(path,lease,world,revision,now,p->true);
        });var lease=lease();assertNotNull(cache.read(root,lease,"world",7,10,10000));
        failing.set(true);assertNull(cache.readForAction(root,lease,"world",7,10,10000));
        assertNull(cache.readForAction(root,lease,"world",7,11,10050));assertEquals(2,reads.get());
        failing.set(false);Files.writeString(root.resolve("idle-service-owner.json"),"{malformed");
        assertNull(cache.read(root,lease,"world",7,12,10100));
        publish(marker());assertNotNull(cache.read(root,lease,"world",7,14,10200));
        Files.writeString(root.resolve("idle-service-owner.json")," ".repeat(IdleOwnerReadCache.MAX_MARKER_BYTES+1));
        assertNull(cache.readForAction(root,lease,"world",7,14,10200));assertEquals(5,reads.get());
    }
    @Test void clockAndTickReversalRequireAnewObservation()throws IOException{
        var reads=new AtomicInteger();publish(marker());var cache=cache(reads,p->true);var lease=lease();
        assertNotNull(cache.read(root,lease,"world",7,10,10000));
        assertNotNull(cache.read(root,lease,"world",7,10,9999));
        assertNotNull(cache.read(root,lease,"world",7,9,9999));assertEquals(3,reads.get());
    }
}
