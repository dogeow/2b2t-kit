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
    private static final WorkHudCache cache=new WorkHudCache();
    private static volatile WorkHudModel.Summary notice;
    private static volatile long noticeUntil;
    private static volatile String navigation="";
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
        current=cache.select(state,external,now);navigation=WorkHudModel.navigation(state);updatedAt=now;
        if(state.has("manual_movement")&&state.get("manual_movement").getAsBoolean())clearNotice();
    }
    public static WorkHudModel.Summary current(){
        long now=System.currentTimeMillis();
        if(now-updatedAt>2000)return null;
        return current!=null?current:now<noticeUntil?notice:null;
    }
    public static void showNotice(String title,String phase){notice=new WorkHudModel.Summary(WorkHudModel.clean(title),"",WorkHudModel.clean(phase),false);noticeUntil=System.currentTimeMillis()+2000;}
    public static void clearNotice(){notice=null;noticeUntil=0;}
    public static String navigation(){return System.currentTimeMillis()-updatedAt<=2000?navigation:"";}
    public static void clear(){current=null;external=null;navigation="";updatedAt=0;cache.clear();clearNotice();}
}
