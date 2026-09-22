package dev.twob2tkit.combat;

import com.google.gson.*;
import java.nio.file.*;
import java.io.IOException;

/** Durable automation interlock. A corrupt record also requires human review. */
public final class SafetyHoldStore {
    private final Path path;
    private JsonObject cached;
    public SafetyHoldStore(Path path){this.path=path;}
    public JsonObject read(){
        if(cached!=null)return cached.deepCopy();
        if(!Files.exists(path)){cached=new JsonObject();return cached.deepCopy();}
        try{cached=JsonParser.parseString(Files.readString(path)).getAsJsonObject();if(!cached.has("active")||!cached.get("active").isJsonPrimitive()||!cached.getAsJsonPrimitive("active").isBoolean())throw new IllegalStateException("Invalid safety lock");return cached.deepCopy();}
        catch(Exception e){var j=new JsonObject();j.addProperty("active",true);j.addProperty("reason","安全锁记录不可读，需要手动确认");cached=j;return j.deepCopy();}
    }
    public boolean active(){var j=read();return j.has("active")&&j.get("active").getAsBoolean();}
    public void write(JsonObject value)throws IOException{
        Files.createDirectories(path.getParent());Path tmp=path.resolveSibling(path.getFileName()+".tmp");
        Files.writeString(tmp,value.toString());
        try{Files.move(tmp,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}
        catch(AtomicMoveNotSupportedException e){Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING);}
        cached=value.deepCopy();
    }
    public void clearByUser()throws IOException{
        var j=read();j.addProperty("active",false);j.addProperty("cleared_by","game_ui");j.addProperty("cleared_at",System.currentTimeMillis());write(j);
    }
}
