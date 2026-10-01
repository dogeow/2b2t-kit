package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import static org.junit.jupiter.api.Assertions.*;

class StatusFileWriterTest {
    @TempDir Path directory;
    private JsonObject snapshot(int value){var out=new JsonObject();out.addProperty("value",value);return out;}
    private int value(Path file)throws IOException{return JsonParser.parseString(Files.readString(file)).getAsJsonObject().get("value").getAsInt();}
    private void entered(CountDownLatch latch)throws InterruptedException{assertTrue(latch.await(5,TimeUnit.SECONDS));}
    @Test void waitingSnapshotsCoalesceAndWrittenOldCandidateNeverRenamesOverNewest()throws Exception{
        Path file=directory.resolve("status.json");Files.writeString(file,"{\"value\":0}");
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var calls=new AtomicInteger();
        try(var writer=new StatusFileWriter((target,world,generation)->{
            if(calls.incrementAndGet()==1){entered.countDown();assertTrue(release.await(5,TimeUnit.SECONDS));}
        })){
            writer.submit(file,snapshot(1),"world",1);entered(entered);
            writer.submit(file,snapshot(2),"world",1);writer.submit(file,snapshot(3),"world",1);
            assertEquals(0,value(file));release.countDown();assertTrue(writer.awaitIdle(5000));
            assertEquals(3,value(file));assertEquals(1,writer.publishedCount());assertEquals(2,calls.get());
            try(var files=Files.list(directory)){assertEquals(List.of("status.json"),files.map(p->p.getFileName().toString()).toList());}
        }finally{release.countDown();}
    }
    @Test void changedWorldAndGenerationInvalidateAnAlreadyWrittenOldCandidate()throws Exception{
        for(long newGeneration:new long[]{20,21}){
            Path file=directory.resolve("status-"+newGeneration+".json");
            var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
            try(var writer=new StatusFileWriter((target,world,generation)->{
                if(world.equals("old-world")){entered.countDown();assertTrue(release.await(5,TimeUnit.SECONDS));}
            })){
                writer.submit(file,snapshot(1),"old-world",20);entered(entered);
                writer.submit(file,snapshot(2),"new-world",newGeneration);
                assertFalse(writer.submit(file,snapshot(99),"old-world",19));
                release.countDown();assertTrue(writer.awaitIdle(5000));
                assertEquals(2,value(file));assertEquals(1,writer.publishedCount());
            }finally{release.countDown();}
        }
    }
    @Test void onlyOneDaemonPublishesInOrderAndCallerTreeIsCopied()throws Exception{
        Path file=directory.resolve("status.json");var threads=new ArrayList<Thread>();var generations=new ArrayList<Long>();
        Thread caller=Thread.currentThread();var snapshot=snapshot(1);
        try(var writer=new StatusFileWriter((target,world,generation)->{threads.add(Thread.currentThread());generations.add(generation);})){
            writer.submit(file,snapshot,"world",1);snapshot.addProperty("value",99);
            assertTrue(writer.awaitIdle(5000));assertEquals(1,value(file));
            writer.submit(file,snapshot(2),"world",2);assertTrue(writer.awaitIdle(5000));assertEquals(2,value(file));
            assertEquals(List.of(1L,2L),generations);assertSame(threads.get(0),threads.get(1));
            assertNotSame(caller,threads.getFirst());assertTrue(threads.getFirst().isDaemon());assertEquals(0,writer.failureCount());
        }
    }
    @Test void realIoFailurePreservesTruthAndNextSnapshotStillPublishes()throws Exception{
        Path file=directory.resolve("status.json");Files.writeString(file,"{\"value\":10}");
        Path badParent=directory.resolve("not-a-directory");Files.writeString(badParent,"preserve me");
        try(var writer=new StatusFileWriter()){
            writer.submit(badParent.resolve("status.json"),snapshot(20),"world",1);
            assertTrue(writer.awaitIdle(5000));assertEquals(1,writer.failureCount());assertFalse(writer.lastFailureType().isBlank());
            assertEquals(10,value(file));assertEquals("preserve me",Files.readString(badParent));
            writer.submit(file,snapshot(30),"world",2);assertTrue(writer.awaitIdle(5000));
            assertEquals(30,value(file));assertEquals(1,writer.publishedCount());
        }
    }
    @Test void failureAtRenameBoundaryCleansTempAndWorkerRecovers()throws Exception{
        Path file=directory.resolve("status.json");Files.writeString(file,"{\"value\":10}");var calls=new AtomicInteger();
        try(var writer=new StatusFileWriter((target,world,generation)->{if(calls.incrementAndGet()==1)throw new IOException("injected failure");})){
            writer.submit(file,snapshot(20),"world",1);assertTrue(writer.awaitIdle(5000));
            assertEquals(10,value(file));assertEquals("IOException",writer.lastFailureType());
            try(var files=Files.list(directory)){assertEquals(1,files.count());}
            writer.submit(file,snapshot(30),"world",1);assertTrue(writer.awaitIdle(5000));assertEquals(30,value(file));
        }
    }
    @Test void closedWriterCannotPublishOrAcceptAnotherStatus()throws Exception{
        Path file=directory.resolve("status.json");Files.writeString(file,"{\"value\":10}");
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
        var writer=new StatusFileWriter((target,world,generation)->{entered.countDown();release.await();});
        writer.submit(file,snapshot(20),"world",1);entered(entered);writer.close();release.countDown();
        assertTrue(writer.awaitIdle(5000));assertEquals(10,value(file));assertFalse(writer.submit(file,snapshot(30),"world",2));
    }
}
