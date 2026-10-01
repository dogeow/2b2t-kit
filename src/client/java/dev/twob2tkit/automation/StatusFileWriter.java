package dev.twob2tkit.automation;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Objects;

/** Single daemon/latest-only status writer; exact action receipts keep their separate path. */
public final class StatusFileWriter implements AutoCloseable {
    private static final Gson JSON=new GsonBuilder().disableHtmlEscaping().create();
    @FunctionalInterface interface BeforePublish {
        void run(Path target,String world,long generation)throws IOException,InterruptedException;
    }
    private record Candidate(Path target,JsonObject snapshot,String world,long generation,long sequence) {}
    private final Object lock=new Object();
    private final BeforePublish beforePublish;
    private final Thread worker;
    private Candidate pending,current;
    private long sequence,publishedCount,failureCount;
    private boolean busy,closed;
    private String lastFailureType="";
    public StatusFileWriter(){this((target,world,generation)->{});}
    StatusFileWriter(BeforePublish beforePublish){
        this.beforePublish=Objects.requireNonNull(beforePublish);
        worker=new Thread(this::run,"twob2tkit-status-writer");
        worker.setDaemon(true);worker.start();
    }
    /** Copies the tick-owned tree without serializing it or doing file IO on the caller. */
    public boolean submit(Path target,JsonObject snapshot,String world,long generation){
        Objects.requireNonNull(target);Objects.requireNonNull(snapshot);Objects.requireNonNull(world);
        JsonObject copy=snapshot.deepCopy();
        synchronized(lock){
            if(closed||current!=null&&generation<current.generation())return false;
            current=new Candidate(target.toAbsolutePath().normalize(),copy,world,generation,++sequence);
            pending=current;lock.notifyAll();return true;
        }
    }
    private void run(){
        while(true){
            Candidate candidate;
            synchronized(lock){
                while(pending==null&&!closed)try{lock.wait();}
                catch(InterruptedException interrupted){if(closed)return;}
                if(closed)return;
                candidate=pending;pending=null;busy=true;
            }
            try{publish(candidate);}
            catch(IOException|RuntimeException failure){
                synchronized(lock){failureCount++;lastFailureType=failure.getClass().getSimpleName();}
            }catch(InterruptedException interrupted){
                synchronized(lock){if(!closed){failureCount++;lastFailureType="InterruptedException";}}
            }finally{synchronized(lock){busy=false;lock.notifyAll();}}
        }
    }
    private boolean current(Candidate candidate){
        return !closed&&current!=null&&current.sequence()==candidate.sequence()
            &&current.generation()==candidate.generation()&&current.world().equals(candidate.world());
    }
    private void publish(Candidate candidate)throws IOException,InterruptedException{
        Path target=candidate.target(),directory=target.getParent();
        synchronized(lock){if(!current(candidate))return;}
        String encoded=JSON.toJson(candidate.snapshot());
        Files.createDirectories(directory);
        Path temporary=Files.createTempFile(directory,"."+target.getFileName()+"-",".tmp");
        try{
            Files.writeString(temporary,encoded,StandardCharsets.UTF_8);
            beforePublish.run(target,candidate.world(),candidate.generation());
            synchronized(lock){
                // Enqueue and the short final rename use the same lock. A
                // superseded candidate can never publish after a newer submit.
                if(!current(candidate))return;
                Files.move(temporary,target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
                publishedCount++;
            }
        }finally{Files.deleteIfExists(temporary);}
    }
    /** Bounded diagnostics/tests only; production ticks call submit. */
    public boolean awaitIdle(long timeoutMillis)throws InterruptedException{
        long remaining=Math.max(0,timeoutMillis)*1_000_000L,deadline=System.nanoTime()+remaining;
        synchronized(lock){
            while(busy||pending!=null){
                if(remaining<=0)return false;
                lock.wait(remaining/1_000_000L,(int)(remaining%1_000_000L));
                remaining=deadline-System.nanoTime();
            }
            return true;
        }
    }
    public long publishedCount(){synchronized(lock){return publishedCount;}}
    public long failureCount(){synchronized(lock){return failureCount;}}
    public String lastFailureType(){synchronized(lock){return lastFailureType;}}
    @Override public void close(){
        synchronized(lock){closed=true;pending=null;lock.notifyAll();}
        worker.interrupt();
    }
}
