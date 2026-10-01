package dev.twob2tkit.combat;

import com.google.gson.*;
import java.nio.file.*;

/** Read-only script health hold. Only a newer native game-UI acknowledgement satisfies it. */
public final class MaterialHealthHoldPolicy {
    public static boolean active(Path path,JsonObject nativeRecord){
        // Python atomically replaces this file; do not cache an older task's record.
        try{return active(JsonParser.parseString(Files.readString(path)),nativeRecord);}
        catch(NoSuchFileException absent){return false;}
        catch(Exception unreadable){return true;}
    }
    public static boolean active(JsonElement record,JsonObject nativeRecord){
        if(record==null||!record.isJsonObject())return true;
        var hold=record.getAsJsonObject();
        Boolean active=booleanValue(hold.get("active"));Long time=timestamp(hold.get("time"));
        if(active==null||time==null)return true;
        if(!active)return false;
        if(nativeRecord==null||!Boolean.FALSE.equals(booleanValue(nativeRecord.get("active"))))return true;
        var by=nativeRecord.get("cleared_by");Long clearedAt=timestamp(nativeRecord.get("cleared_at"));
        return by==null||!by.isJsonPrimitive()||!by.getAsJsonPrimitive().isString()
            ||!"game_ui".equals(by.getAsString())||clearedAt==null||clearedAt<=time;
    }
    private static Boolean booleanValue(JsonElement value){
        return value!=null&&value.isJsonPrimitive()&&value.getAsJsonPrimitive().isBoolean()?value.getAsBoolean():null;
    }
    private static Long timestamp(JsonElement value){
        if(value==null||!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isNumber())return null;
        var text=value.getAsString();if(!text.matches("0|[1-9][0-9]*"))return null;
        try{return Long.parseLong(text);}catch(NumberFormatException invalid){return null;}
    }
    private MaterialHealthHoldPolicy(){}
}
