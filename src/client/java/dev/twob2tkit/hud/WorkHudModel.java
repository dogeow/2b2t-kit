package dev.twob2tkit.hud;

import com.google.gson.JsonObject;

/** Pure summary selection. Counts retain their task meaning; unlimited jobs have no invented total. */
public final class WorkHudModel {
    private WorkHudModel() {}
    public record Summary(String title, String progress, String phase, boolean attention) {
        public String line() { return title + (progress.isBlank()?"":" · "+progress) + (phase.isBlank()?"":" · "+phase); }
    }
    public static Summary select(JsonObject state, JsonObject external, long now) {
        if (!flag(state,"connected") || flag(state,"manual_movement")) return null;
        Summary result = external(state,external,now);
        JsonObject material = object(state,"material_job");
        if(result == null && flag(material,"active") && !text(material,"world_session").isBlank()
                && text(material,"world_session").equals(text(state,"world_session")))
            result=summary(text(material,"title").isBlank()?"材料任务":clean(text(material,"title")),number(material,"done"),number(material,"total"),text(material,"phase"));
        if (result == null) {
            JsonObject j = object(state,"build_job");
            if(flag(j,"active")) result=summary("投影建造",number(j,"matched"),number(j,"total"),text(j,"phase"));
            j=object(state,"concrete");
            if(result==null && flag(j,"active"))result=summary("混凝土制作",number(j,"completed"),number(j,"limit"),text(j,"status"));
            j=object(state,"gravel");
            if(result==null && flag(j,"active"))result=summary("采集沙砾",number(j,"collected"),number(j,"limit"),text(j,"status"));
            if(result==null && flag(state,"chopping"))result=new Summary("自动砍树","已完成 "+number(state,"chopper_verified_trees")+" 棵",clean(text(state,"chopper_status")),false);
            if(result==null && flag(state,"planter_active"))result=new Summary("种田","已种 "+number(state,"planter_count")+" · 已收 "+number(state,"harvest_count"),clean(text(state,"planter_status")),false);
            if(result==null && flag(state,"feeder_active"))result=new Summary("喂养","已喂 "+number(state,"feeder_count")+" 次",clean(text(state,"feeder_status")),false);
            if(result==null && flag(state,"fisher_active"))result=new Summary("钓鱼","",clean(text(state,"fisher_status")),false);
            if(result==null && flag(state,"borer_active"))result=new Summary("自动挖矿","",clean(text(state,"borer_status")),false);
            if(result==null && flag(state,"guide_active"))result=new Summary("目的地指引","",clean(text(state,"guide_status")),false);
            if(result==null && flag(state,"printing"))result=new Summary("自动建造","",clean(text(state,"printer_status")),false);
        }
        String override=flag(state,"health_recovery_hold")?"恢复生命":flag(state,"guard_busy")?"防护中":flag(object(state,"guard_food"),"active")?"进食中":"";
        if(!override.isBlank())return result==null?new Summary("自动保护","",override,true):new Summary(result.title,result.progress,override,true);
        return result;
    }
    private static Summary external(JsonObject s,JsonObject j,long now) {
        if(j==null||!flag(j,"active")||text(j,"world_session").isBlank()||!text(j,"world_session").equals(text(s,"world_session")))return null;
        JsonObject lease=object(s,"supervision_lease");
        if(text(j,"task_session").isBlank()||!text(j,"task_session").equals(text(lease,"job_session"))||number(j,"control_revision")!=number(s,"control_revision"))return null;
        long age=now-number(j,"updated_at");
        if(age<0||age>5000||text(j,"title").isBlank()||number(j,"done")<0||number(j,"total")<0)return null;
        return summary(clean(text(j,"title")),number(j,"done"),number(j,"total"),text(j,"phase"));
    }
    private static Summary summary(String title,long done,long total,String phase) {
        // Progress is never clamped to a plausible-looking value.
        return new Summary(title,total>0?done+"/"+total:"已完成 "+done,clean(phase).replaceFirst(" · 已(?:挖|收集).*$",""),false);
    }
    public static String clean(String value) {
        String s=value.replaceAll("§.","").replaceAll("[\\p{Cntrl}]"," ").replaceAll("\\s+"," ").strip();
        return s.codePointCount(0,s.length())>60?s.substring(0,s.offsetByCodePoints(0,59))+"…":s;
    }
    private static JsonObject object(JsonObject j,String key){try{return j.getAsJsonObject(key);}catch(Exception e){return null;}}
    private static String text(JsonObject j,String key){try{return j.get(key).getAsString();}catch(Exception e){return "";}}
    private static long number(JsonObject j,String key){try{return j.get(key).getAsLong();}catch(Exception e){return 0;}}
    private static boolean flag(JsonObject j,String key){try{return j.get(key).getAsBoolean();}catch(Exception e){return false;}}
}
