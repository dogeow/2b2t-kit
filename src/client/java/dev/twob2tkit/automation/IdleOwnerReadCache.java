package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.function.LongPredicate;

/** Bounded owner observations for status; action authority always refreshes positive evidence. */
final class IdleOwnerReadCache {
    static final long INTERVAL_MILLIS=100;
    static final int INTERVAL_TICKS=2;
    static final int MAX_MARKER_BYTES=8192;
    interface Reader {
        Observation read(Path root,JsonObject lease,String world,long revision,long now)throws IOException;
    }
    record Observation(JsonObject marker,Path root,IdleActivityPolicy.Owner owner) {
        Observation { marker=marker.deepCopy(); }
    }
    private record Scope(Path root,String lease,String task,String world,long revision) {}
    private final Reader reader;
    private Scope scope;
    private Observation observed;
    private boolean read;
    private int readTick;
    private long readAt;

    IdleOwnerReadCache(){this((root,lease,world,revision,now)->readFile(root,lease,world,revision,now,
        pid->ProcessHandle.of(pid).map(ProcessHandle::isAlive).orElse(false)));}
    IdleOwnerReadCache(Reader reader){this.reader=reader;}

    IdleActivityPolicy.Owner read(Path root,JsonObject lease,String world,long revision,int tick,long now){
        return read(root,lease,world,revision,tick,now,false);
    }
    /** Negative observations may delay an action; a cached positive can never grant one. */
    IdleActivityPolicy.Owner readForAction(Path root,JsonObject lease,String world,long revision,int tick,long now){
        return read(root,lease,world,revision,tick,now,true);
    }
    void invalidate(){scope=null;observed=null;read=false;}

    private IdleActivityPolicy.Owner read(Path root,JsonObject lease,String world,long revision,int tick,long now,boolean action){
        Scope current=scope(root,lease,world,revision);
        if(current==null){invalidate();return null;}
        boolean refresh=!read||!current.equals(scope)||now<readAt||tick<readTick
            ||now-readAt>=INTERVAL_MILLIS||(long)tick-readTick>=INTERVAL_TICKS;
        if(refresh||action&&owner(lease,world,revision,now)!=null){
            // Clear first: IO or process failures must not restore the previous owner's authority.
            scope=current;observed=null;read=true;readAt=now;readTick=tick;
            try{observed=reader.read(current.root(),lease,world,revision,now);}
            catch(IOException|RuntimeException failure){observed=null;}
        }
        return owner(lease,world,revision,now);
    }
    private IdleActivityPolicy.Owner owner(JsonObject lease,String world,long revision,long now){
        if(observed==null||observed.owner()==null)return null;
        // Timestamp and exact native ownership remain live checks, independent of the cache TTL.
        return IdleActivityPolicy.owner(observed.marker(),lease,world,revision,now,observed.root(),
            pid->pid==observed.owner().pid());
    }
    private static Scope scope(Path root,JsonObject lease,String world,long revision){
        try{
            if(root==null||lease==null||world==null||world.isBlank()||revision<0
                    ||!"materials".equals(IdleActivityPolicy.string(lease,"kind"))
                    ||!world.equals(IdleActivityPolicy.string(lease,"world_session"))
                    ||!lease.has("revision")||!lease.get("revision").isJsonPrimitive()
                    ||!lease.getAsJsonPrimitive("revision").isNumber()
                    ||lease.get("revision").getAsBigDecimal().longValueExact()!=revision)return null;
            String id=IdleActivityPolicy.string(lease,"id"),task=IdleActivityPolicy.string(lease,"job_session");
            if(id.isBlank()||task.isBlank())return null;
            return new Scope(root.toAbsolutePath().normalize(),id,task,world,revision);
        }catch(RuntimeException malformed){return null;}
    }
    static Observation readFile(Path root,JsonObject lease,String world,long revision,long now,LongPredicate alive)throws IOException{
        Path base=root.toRealPath(),path=base.resolve("idle-service-owner.json");
        if(!Files.isRegularFile(path))return null;
        byte[] bytes;
        try(var stream=Files.newInputStream(path)){bytes=stream.readNBytes(MAX_MARKER_BYTES+1);}
        if(bytes.length>MAX_MARKER_BYTES)return null;
        var marker=JsonParser.parseString(new String(bytes,StandardCharsets.UTF_8)).getAsJsonObject();
        var owner=IdleActivityPolicy.owner(marker,lease,world,revision,now,base,alive);
        if(owner==null||!Files.isRegularFile(base.resolve("idle-services").resolve(owner.service()).resolve("worker.lock")))return null;
        return new Observation(marker,base,owner);
    }
}
