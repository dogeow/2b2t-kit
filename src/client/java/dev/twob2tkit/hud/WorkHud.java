package dev.twob2tkit.hud;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;

/** Consumes the bridge's existing snapshot; no world scan or file IO in the render callback. */
public final class WorkHud {
    private static volatile WorkHudModel.Summary current;
    private static volatile long updatedAt;
    private static long lastRead;
    private static JsonObject external;
    private WorkHud() {}
    public static void update(JsonObject state,Path root) {
        long now=System.currentTimeMillis();
        if(now-lastRead>=250){
            lastRead=now;
            try {
                Path p=root.resolve("job-progress.json");
                external=Files.size(p)<=8192?JsonParser.parseString(Files.readString(p)).getAsJsonObject():null;
            }catch(Exception ignored){external=null;}
        }
        state.add("material_job", dev.twob2tkit.material.MaterialJobs.hud());
        current=WorkHudModel.select(state,external,now);updatedAt=now;
    }
    public static WorkHudModel.Summary current(){return System.currentTimeMillis()-updatedAt<=2000?current:null;}
    public static void clear(){current=null;external=null;updatedAt=0;}
}
