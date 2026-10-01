package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.io.IOException;
import java.nio.ByteBuffer;
import java.nio.channels.FileChannel;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.UUID;

/** Cell-scoped claim survives stop, reconnect and process crash. Only an exactly confirmed terminal receipt reopens it. */
final class BucketUseStore {
    private BucketUseStore() {}
    static Path path(Path root,String server,String dimension,int x,int y,int z) {
        String stableServer=server.trim().toLowerCase(java.util.Locale.ROOT).replaceFirst(":25565$","");
        String scope=String.join("\0",stableServer,dimension,x+","+y+","+z);
        try {
            byte[] hash=MessageDigest.getInstance("SHA-256").digest(scope.getBytes(StandardCharsets.UTF_8));
            StringBuilder key=new StringBuilder();for(int i=0;i<16;i++)key.append(String.format("%02x",hash[i]));
            return root.resolve("bucket-use-claims-v1").resolve(key+".json");
        }catch(NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
    }
    static void requireAvailable(Path path)throws IOException {
        if(!Files.exists(path))return;
        if(!Files.isRegularFile(path)||Files.size(path)>16384)throw new IllegalStateException("Bucket cell claim is unreadable; no replay allowed");
        try {
            JsonObject old=JsonParser.parseString(Files.readString(path)).getAsJsonObject();
            var confirmed=old.get("confirmed");
            if(confirmed==null||!confirmed.isJsonPrimitive()||!confirmed.getAsJsonPrimitive().isBoolean()
                    ||!confirmed.getAsBoolean())throw new IllegalStateException("Bucket cell has an unresolved durable use claim; no replay allowed");
        }catch(com.google.gson.JsonParseException|IllegalArgumentException malformed){
            throw new IllegalStateException("Bucket cell claim is malformed; no replay allowed",malformed);
        }
    }
    static void claim(Path path,JsonObject receipt)throws IOException {
        Files.createDirectories(path.getParent());requireAvailable(path);
        if(Files.exists(path))update(path,receipt);
        else {
            // An empty inode after a failed write still blocks another use.
            Files.createFile(path);forceDirectory(path.getParent());
            try(FileChannel out=FileChannel.open(path,StandardOpenOption.WRITE)){write(out,receipt);}
            forceDirectory(path.getParent());
        }
    }
    static void update(Path path,JsonObject receipt)throws IOException {
        if(!Files.isRegularFile(path))throw new IllegalStateException("Bucket durable claim disappeared; no replay allowed");
        Path temp=path.resolveSibling("."+path.getFileName()+"-"+UUID.randomUUID());
        try {
            try(FileChannel out=FileChannel.open(temp,StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE)){write(out,receipt);}
            try{Files.move(temp,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}
            catch(AtomicMoveNotSupportedException unsupported){Files.move(temp,path,StandardCopyOption.REPLACE_EXISTING);}
            forceDirectory(path.getParent());
        }finally{Files.deleteIfExists(temp);}
    }
    private static void write(FileChannel out,JsonObject receipt)throws IOException {
        ByteBuffer bytes=ByteBuffer.wrap(receipt.toString().getBytes(StandardCharsets.UTF_8));
        while(bytes.hasRemaining())out.write(bytes);out.force(true);
    }
    private static void forceDirectory(Path path)throws IOException {
        try(FileChannel out=FileChannel.open(path,StandardOpenOption.READ)){out.force(true);}
    }
}
