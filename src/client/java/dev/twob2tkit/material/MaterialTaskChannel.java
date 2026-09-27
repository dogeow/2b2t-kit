package dev.twob2tkit.material;

import com.google.gson.*;
import java.io.IOException;
import java.nio.file.*;
import java.util.function.Function;

/** At-most-once outer-worker mailbox, separate from the gameplay/native-operation mailbox. */
public final class MaterialTaskChannel {
    public static final String REQUEST="material-task-request.json",REPLY_PREFIX="material-task-reply-";
    private static final Gson JSON=new Gson();
    private boolean initialized;
    private String lastId="";
    public void tick(Path root,Function<JsonObject,JsonObject> handler)throws IOException{
        Path file=root.resolve(REQUEST);
        if(!initialized){
            initialized=true;
            // A request left by an earlier game process is never replayed after startup.
            if(Files.isRegularFile(file)&&Files.size(file)<=16384){
                try{
                    JsonObject request=JsonParser.parseString(Files.readString(file)).getAsJsonObject();
                    lastId=MaterialTaskProtocol.identifier(request);
                    Path reply=root.resolve(REPLY_PREFIX+lastId+".json");
                    if(!Files.exists(reply)){
                        var stale=new JsonObject();stale.addProperty("phase","error");stale.addProperty("op",request.has("op")&&request.get("op").isJsonPrimitive()&&request.getAsJsonPrimitive("op").isString()?request.get("op").getAsString():"");
                        stale.addProperty("detail","Request predates this client session; not replayed. Inspect current status before a new explicit request.");
                        stale.addProperty("observed_at",System.currentTimeMillis());writeReply(reply,lastId,stale);
                    }
                }
                catch(RuntimeException ignored){}
            }
            return;
        }
        if(!Files.isRegularFile(file)||Files.size(file)>16384)return;
        JsonObject request;
        try{request=JsonParser.parseString(Files.readString(file)).getAsJsonObject();}
        catch(RuntimeException malformed){return;}
        String id;
        try{id=MaterialTaskProtocol.identifier(request);}catch(IllegalArgumentException invalid){return;}
        if(id.equals(lastId))return;
        lastId=id;
        Path destination=root.resolve(REPLY_PREFIX+id+".json");
        if(Files.exists(destination))return; // Old ID replay cannot cancel or launch another task.
        JsonObject reply=handler.apply(request);
        writeReply(destination,id,reply);
    }
    private static void writeReply(Path destination,String id,JsonObject reply)throws IOException{
        reply.addProperty("schema",MaterialTaskProtocol.VERSION);reply.addProperty("id",id);
        Path tmp=destination.resolveSibling(destination.getFileName()+".tmp");
        Files.writeString(tmp,JSON.toJson(reply));
        try{Files.move(tmp,destination,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}
        catch(AtomicMoveNotSupportedException unsupported){Files.move(tmp,destination,StandardCopyOption.REPLACE_EXISTING);}
    }
}
