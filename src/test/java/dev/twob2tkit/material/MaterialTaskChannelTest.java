package dev.twob2tkit.material;
import com.google.gson.*;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.*;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.function.Function;
import static org.junit.jupiter.api.Assertions.*;
class MaterialTaskChannelTest {
    @TempDir Path root;
    private void request(String id)throws Exception{Files.writeString(root.resolve(MaterialTaskChannel.REQUEST),"{\"id\":\""+id+"\",\"op\":\"material_task_start\"}");}
    private Function<JsonObject,JsonObject> handler(AtomicInteger calls){return request->{calls.incrementAndGet();var result=new JsonObject();result.addProperty("op",request.get("op").getAsString());result.addProperty("phase","done");var task=new JsonObject();task.addProperty("state","queued");task.addProperty("process_alive",true);result.add("material_task",task);return result;};}
    private JsonObject reply(String id)throws Exception{return JsonParser.parseString(Files.readString(root.resolve(MaterialTaskChannel.REPLY_PREFIX+id+".json"))).getAsJsonObject();}
    @Test void independentMailboxNeverChangesNativeRequestOrStatus()throws Exception{
        Path gameplay=root.resolve("request.json"),status=root.resolve("status.json");Files.writeString(gameplay,"native running request");Files.writeString(status,"native running status");
        var calls=new AtomicInteger();var channel=new MaterialTaskChannel();channel.tick(root,handler(calls));request("outer-1");channel.tick(root,handler(calls));
        assertEquals(1,calls.get());assertEquals("native running request",Files.readString(gameplay));assertEquals("native running status",Files.readString(status));
        var result=reply("outer-1");assertEquals(1,result.get("schema").getAsInt());assertEquals("outer-1",result.get("id").getAsString());assertEquals("queued",result.getAsJsonObject("material_task").get("state").getAsString());
    }
    @Test void startAcceptedReplyDoesNotPretendTaskCompleted()throws Exception{
        var calls=new AtomicInteger();var channel=new MaterialTaskChannel();channel.tick(root,handler(calls));request("start-1");channel.tick(root,handler(calls));
        assertEquals("done",reply("start-1").get("phase").getAsString());assertEquals("queued",reply("start-1").getAsJsonObject("material_task").get("state").getAsString());
    }
    @Test void duplicateAndOlderReplayCannotLaunchAgain()throws Exception{
        var calls=new AtomicInteger();var channel=new MaterialTaskChannel();channel.tick(root,handler(calls));
        request("one");channel.tick(root,handler(calls));channel.tick(root,handler(calls));request("two");channel.tick(root,handler(calls));request("one");channel.tick(root,handler(calls));assertEquals(2,calls.get());
    }
    @Test void leftoverRequestAfterRestartGetsExplicitErrorWithoutExecution()throws Exception{
        request("old-session");var calls=new AtomicInteger();var channel=new MaterialTaskChannel();channel.tick(root,handler(calls));
        assertEquals(0,calls.get());assertEquals("error",reply("old-session").get("phase").getAsString());assertEquals("material_task_start",reply("old-session").get("op").getAsString());
        request("fresh-session");channel.tick(root,handler(calls));assertEquals(1,calls.get());
    }
    @Test void interruptedHandlerIsNeverReplayedWithSameId()throws Exception{
        var calls=new AtomicInteger();var channel=new MaterialTaskChannel();channel.tick(root,handler(calls));request("uncertain");
        assertThrows(IllegalStateException.class,()->channel.tick(root,r->{calls.incrementAndGet();throw new IllegalStateException("after action");}));
        channel.tick(root,handler(calls));assertEquals(1,calls.get());assertFalse(Files.exists(root.resolve(MaterialTaskChannel.REPLY_PREFIX+"uncertain.json")));
    }
    @Test void malformedOrPathTraversalRequestsNeverCallHandler()throws Exception{
        var calls=new AtomicInteger();var channel=new MaterialTaskChannel();channel.tick(root,handler(calls));
        Files.writeString(root.resolve(MaterialTaskChannel.REQUEST),"broken");channel.tick(root,handler(calls));request("../escape");channel.tick(root,handler(calls));assertEquals(0,calls.get());
    }
}
