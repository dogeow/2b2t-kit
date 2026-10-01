package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.UUID;

/** Durable claim written before the sole attack packet; an existing key is never replayed. */
final class HorseNudgeStore {
    private HorseNudgeStore() {}

    static String canonicalKey(String server,String dimension,String placementKey,String horseUuid,
                               int x,int y,int z){
        String scope=String.join("\0",server,dimension,placementKey,horseUuid,x+","+y+","+z);
        try{
            byte[] digest=MessageDigest.getInstance("SHA-256").digest(scope.getBytes(StandardCharsets.UTF_8));
            StringBuilder hex=new StringBuilder(32);for(int i=0;i<16;i++)hex.append(String.format("%02x",digest[i]));
            return "horse-nudge-"+hex;
        }catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
    }

    static Path path(Path automationRoot,String key){
        if(key==null||!key.matches("[A-Za-z0-9_-]{8,80}"))
            throw new IllegalArgumentException("Invalid horse nudge spent key");
        return automationRoot.resolve("horse-nudge-spent-v1").resolve(key+".json");
    }

    static Path claim(Path automationRoot,String key,JsonObject receipt)throws IOException{
        Path destination=path(automationRoot,key);Files.createDirectories(destination.getParent());
        // CREATE_NEW is the exclusive claim. Even a crash before the JSON write
        // leaves a spent inode, which is safer than replaying an uncertain hit.
        Files.createFile(destination);forceDirectory(destination.getParent());
        writeExistingForced(destination,receipt);forceDirectory(destination.getParent());
        return destination;
    }

    static void update(Path destination,JsonObject receipt)throws IOException{
        if(destination==null||!Files.isRegularFile(destination))
            throw new IllegalStateException("Horse nudge spent claim is missing");
        Path temporary=destination.resolveSibling("."+destination.getFileName()+"-update-"+UUID.randomUUID());
        try{
            writeForced(temporary,receipt);
            try{Files.move(temporary,destination,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}
            catch(AtomicMoveNotSupportedException unsupported){Files.move(temporary,destination,StandardCopyOption.REPLACE_EXISTING);}
            forceDirectory(destination.getParent());
        }finally{Files.deleteIfExists(temporary);}
    }

    private static void writeForced(Path path,JsonObject receipt)throws IOException{
        byte[] bytes=receipt.toString().getBytes(StandardCharsets.UTF_8);
        try(FileChannel channel=FileChannel.open(path,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){
            ByteBuffer buffer=ByteBuffer.wrap(bytes);while(buffer.hasRemaining())channel.write(buffer);channel.force(true);
        }
    }
    private static void writeExistingForced(Path path,JsonObject receipt)throws IOException{
        byte[] bytes=receipt.toString().getBytes(StandardCharsets.UTF_8);
        try(FileChannel channel=FileChannel.open(path,StandardOpenOption.WRITE,StandardOpenOption.TRUNCATE_EXISTING)){
            ByteBuffer buffer=ByteBuffer.wrap(bytes);while(buffer.hasRemaining())channel.write(buffer);channel.force(true);
        }
    }
    private static void forceDirectory(Path directory)throws IOException{
        try(FileChannel channel=FileChannel.open(directory,StandardOpenOption.READ)){channel.force(true);}
    }
}
