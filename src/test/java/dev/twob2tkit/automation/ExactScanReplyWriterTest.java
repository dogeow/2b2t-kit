package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;

class ExactScanReplyWriterTest {
    @TempDir Path root;
    private JsonObject reply(String id,int cells){
        var value=new JsonObject();value.addProperty("id",id);value.addProperty("world_session","world-a");
        var rows=new JsonArray();for(int i=0;i<cells;i++){
            var row=new JsonObject();row.addProperty("state","Block{minecraft:stone}");row.addProperty("sample",i);
            row.addProperty("block_light",i%16);row.addProperty("sky_light",i%16);row.addProperty("zombie_block_light_risk",false);
            rows.add(row);
        }
        value.add("blocks",rows);return value;
    }
    private void await(ExactScanReplyWriter.Job job,ExactScanReplyWriter.State expected)throws Exception{
        long deadline=System.nanoTime()+TimeUnit.SECONDS.toNanos(10);
        while(job.state!=expected&&System.nanoTime()<deadline)Thread.sleep(2);
        assertEquals(expected,job.state,job.failureType);
    }
    @Test void completedTreeTransfersWithoutCopyAndOnlySingleDaemonPerformsEncodingAndIO()throws Exception{
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);var thread=new AtomicReference<Thread>();
        try(var writer=new ExactScanReplyWriter(path->{thread.set(Thread.currentThread());entered.countDown();assertTrue(release.await(5,TimeUnit.SECONDS));})){
            var tree=reply("scan-a",5);var job=writer.submit(root.resolve("reply-a.json"),tree);
            assertSame(tree,job.snapshot);assertTrue(entered.await(5,TimeUnit.SECONDS));
            assertNotEquals(Thread.currentThread(),thread.get());assertTrue(thread.get().isDaemon());
            assertEquals(ExactScanReplyWriter.State.PENDING,job.state);assertFalse(Files.exists(job.target));
            assertThrows(IllegalStateException.class,()->writer.submit(root.resolve("reply-b.json"),reply("scan-b",1)));
            release.countDown();await(job,ExactScanReplyWriter.State.SAVED);
            assertEquals("scan-a",JsonParser.parseString(Files.readString(job.target)).getAsJsonObject().get("id").getAsString());
            writer.release(job);
        }
    }
    @Test void allFiftyThousandDetailedRowsReachTheExactReplyOnActualFilesystem()throws Exception{
        try(var writer=new ExactScanReplyWriter()){
            var job=writer.submit(root.resolve("reply-large.json"),reply("large-scan",50_000));await(job,ExactScanReplyWriter.State.SAVED);
            assertTrue(Files.size(job.target)>5_000_000);
            var actual=JsonParser.parseString(Files.readString(job.target)).getAsJsonObject();
            var cells=actual.getAsJsonArray("blocks");assertEquals(50_000,cells.size());
            assertEquals(0,cells.get(0).getAsJsonObject().get("sample").getAsInt());
            assertEquals(49_999,cells.get(49_999).getAsJsonObject().get("sample").getAsInt());writer.release(job);
        }
    }
    @Test void realIOFailureRetainsTheOriginalRecordAndRetryWritesItWithoutReplacement()throws Exception{
        var blocked=root.resolve("blocked");Files.writeString(blocked,"file");var tree=reply("scan-original",3);
        try(var writer=new ExactScanReplyWriter()){
            var job=writer.submit(blocked.resolve("reply.json"),tree);await(job,ExactScanReplyWriter.State.FAILED);
            assertSame(tree,job.snapshot);assertEquals(1,job.failures);assertFalse(job.failureType.isBlank());
            assertThrows(IllegalStateException.class,()->writer.release(job));
            assertThrows(IllegalStateException.class,()->writer.submit(root.resolve("different.json"),reply("different",1)));
            Files.delete(blocked);writer.retry(job);await(job,ExactScanReplyWriter.State.SAVED);
            assertEquals(tree,JsonParser.parseString(Files.readString(job.target)));writer.release(job);
        }
    }
    @Test void failureAfterTemporaryWriteCleansTheTemporaryFileAndKeepsTheExactRetry()throws Exception{
        var calls=new AtomicInteger();try(var writer=new ExactScanReplyWriter(path->{if(calls.getAndIncrement()==0)throw new IOException("injected");})){
            var job=writer.submit(root.resolve("reply.json"),reply("same-scan",2));await(job,ExactScanReplyWriter.State.FAILED);
            try(var files=Files.list(root)){assertTrue(files.noneMatch(path->path.getFileName().toString().endsWith(".tmp")));}
            writer.retry(job);await(job,ExactScanReplyWriter.State.SAVED);assertEquals(2,calls.get());writer.release(job);
        }
    }
    @Test void exactJobsAreNeverCoalescedAndShutdownDrainsTheAlreadyAcceptedJob()throws Exception{
        var entered=new CountDownLatch(1);var release=new CountDownLatch(1);
        var writer=new ExactScanReplyWriter(path->{entered.countDown();assertTrue(release.await(5,TimeUnit.SECONDS));});
        try{
            var first=writer.submit(root.resolve("first.json"),reply("first",1));assertTrue(entered.await(5,TimeUnit.SECONDS));
            writer.close();assertThrows(IllegalStateException.class,()->writer.submit(root.resolve("second.json"),reply("second",1)));
            release.countDown();await(first,ExactScanReplyWriter.State.SAVED);assertTrue(Files.isRegularFile(first.target));
        }finally{release.countDown();writer.close();}
        try(var next=new ExactScanReplyWriter()){
            var first=next.submit(root.resolve("one.json"),reply("one",1));await(first,ExactScanReplyWriter.State.SAVED);next.release(first);
            var second=next.submit(root.resolve("two.json"),reply("two",1));await(second,ExactScanReplyWriter.State.SAVED);next.release(second);
            assertTrue(Files.isRegularFile(first.target));assertTrue(Files.isRegularFile(second.target));
        }
    }
    @Test void writerHasNoWorldAccessAndSubmittedScanTreesAreNotCopiedAgain()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/ExactScanReplyWriter.class")){
            assertNotNull(in);new ClassReader(in).accept(node,0);
        }
        for(var method:node.methods)for(var instruction:method.instructions)if(instruction instanceof MethodInsnNode call){
            assertFalse(call.owner.startsWith("net/minecraft/"));assertNotEquals("deepCopy",call.name);
        }
    }
}
