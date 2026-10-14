package dev.twob2tkit.hud;

import com.google.gson.JsonObject;

/** Keeps a recently verified task visible while its own navigation advances the revision. */
public final class WorkHudCache {
    private WorkHudModel.Summary task;
    private String world="",owner="",leaseId="";
    private long verifiedAt,revision;

    public WorkHudModel.Summary select(JsonObject state,JsonObject external,long now) {
        if(!flag(state,"connected")||flag(state,"manual_movement")) { clear();return null; }
        JsonObject lease=object(state,"supervision_lease");
        var fresh=WorkHudModel.external(state,external,now);
        if(fresh!=null) {
            task=fresh;world=text(state,"world_session");owner=text(lease,"job_session");
            leaseId=text(lease,"id");revision=number(state,"control_revision");verifiedAt=now;
            return WorkHudModel.protect(state,fresh);
        }
        boolean closed=external!=null&&!flag(external,"active")
            &&world.equals(text(external,"world_session"))&&owner.equals(text(external,"task_session"));
        if(task!=null&&!closed&&now>=verifiedAt&&now-verifiedAt<=5000
                &&!leaseId.isBlank()&&leaseId.equals(text(lease,"id"))
                &&world.equals(text(state,"world_session"))&&world.equals(text(lease,"world_session"))
                &&owner.equals(text(lease,"job_session"))&&text(lease,"kind").equals("materials")
                &&number(state,"control_revision")>=revision) {
            return WorkHudModel.protect(state,task);
        }
        clear();return WorkHudModel.select(state,external,now);
    }
    public void clear(){task=null;world="";owner="";leaseId="";verifiedAt=0;revision=0;}
    private static JsonObject object(JsonObject j,String key){try{return j.getAsJsonObject(key);}catch(Exception e){return null;}}
    private static String text(JsonObject j,String key){try{return j.get(key).getAsString();}catch(Exception e){return "";}}
    private static long number(JsonObject j,String key){try{return j.get(key).getAsLong();}catch(Exception e){return 0;}}
    private static boolean flag(JsonObject j,String key){try{return j.get(key).getAsBoolean();}catch(Exception e){return false;}}
}
