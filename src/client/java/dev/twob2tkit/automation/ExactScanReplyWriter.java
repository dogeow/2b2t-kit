package dev.twob2tkit.automation;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Objects;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

/** One immutable completed scan, retained until its exact atomic reply has been written. */
final class ExactScanReplyWriter implements AutoCloseable {
    private static final Gson JSON=new GsonBuilder().disableHtmlEscaping().create();
    enum State { PENDING,SAVED,FAILED }
    @FunctionalInterface interface BeforeCommit { void run(Path target)throws IOException,InterruptedException; }
    static final class Job {
        final Path target;
        final JsonObject snapshot;
        volatile State state=State.PENDING;
        volatile String failureType="";
        volatile long failures;
        private String encoded;
        Job(Path target,JsonObject snapshot){this.target=target;this.snapshot=snapshot;}
    }
    private final BeforeCommit beforeCommit;
    private final ExecutorService worker=Executors.newSingleThreadExecutor(task->{
        var thread=new Thread(task,"twob2tkit-exact-scan-writer");thread.setDaemon(true);return thread;
    });
    private Job current;
    private boolean closed;
    ExactScanReplyWriter(){this(target->{});}
    ExactScanReplyWriter(BeforeCommit beforeCommit){this.beforeCommit=Objects.requireNonNull(beforeCommit);}

    /** Ownership transfer: caller must never mutate this finished tree after submitting it. */
    synchronized Job submit(Path target,JsonObject immutableSnapshot){
        if(closed)throw new IllegalStateException("Exact scan writer is closed");
        if(current!=null)throw new IllegalStateException("Another exact scan reply is retained");
        current=new Job(Objects.requireNonNull(target).toAbsolutePath().normalize(),Objects.requireNonNull(immutableSnapshot));
        schedule(current);return current;
    }
    synchronized void retry(Job job){
        if(closed||job!=current||job.state!=State.FAILED)throw new IllegalStateException("Exact scan reply is not retryable");
        job.state=State.PENDING;schedule(job);
    }
    synchronized void release(Job job){
        if(job!=current||job.state!=State.SAVED)throw new IllegalStateException("Exact scan reply has not been saved");
        current=null;
    }
    private void schedule(Job job){worker.execute(()->write(job));}
    private void write(Job job){
        Path temporary=null;
        try{
            if(job.encoded==null)job.encoded=JSON.toJson(job.snapshot);
            var parent=job.target.getParent();Files.createDirectories(parent);
            temporary=Files.createTempFile(parent,"."+job.target.getFileName()+"-",".tmp");
            Files.writeString(temporary,job.encoded);beforeCommit.run(job.target);
            Files.move(temporary,job.target,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
            job.state=State.SAVED;
        }catch(IOException|RuntimeException failure){
            job.failureType=failure.getClass().getSimpleName();job.failures++;job.state=State.FAILED;
        }catch(InterruptedException interrupted){
            Thread.currentThread().interrupt();job.failureType="InterruptedException";job.failures++;job.state=State.FAILED;
        }finally{
            if(temporary!=null)try{Files.deleteIfExists(temporary);}catch(IOException ignored){}
        }
    }
    /** Accepted work drains; shutdown never replaces or drops a queued exact reply. */
    @Override public synchronized void close(){closed=true;worker.shutdown();}
}
