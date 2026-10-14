package dev.twob2tkit.hud;

import com.google.gson.JsonObject;
import java.util.Locale;

/** Pure summary selection. Counts retain their task meaning; unlimited jobs have no invented total. */
public final class WorkHudModel {
    private static final CruiseEtaEstimate navigationEta = new CruiseEtaEstimate();
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
        return protect(state,result);
    }
    static Summary protect(JsonObject state,Summary result) {
        String override=flag(state,"health_recovery_hold")?"恢复生命":flag(state,"guard_busy")?"防护中":flag(object(state,"guard_food"),"eating")?"进食中":flag(state,"inventory_interface_paused")?"查看背包，施工暂停":"";
        if(!override.isBlank())return result==null?new Summary("自动保护","",override,true):new Summary(result.title,result.progress,override,true);
        return result;
    }
    static Summary external(JsonObject s,JsonObject j,long now) {
        if(j==null||!flag(j,"active")||text(j,"world_session").isBlank()||!text(j,"world_session").equals(text(s,"world_session")))return null;
        JsonObject lease=object(s,"supervision_lease");
        if(text(j,"task_session").isBlank()||!text(j,"task_session").equals(text(lease,"job_session"))||number(j,"control_revision")!=number(s,"control_revision"))return null;
        long age=now-number(j,"updated_at");
        if(age<0||age>5000||text(j,"title").isBlank()||number(j,"done")<0||number(j,"total")<0)return null;
        return summary(clean(text(j,"title")),number(j,"done"),number(j,"total"),text(j,"phase"));
    }
    public static String navigation(JsonObject state) {
        if(!flag(state,"connected")||flag(state,"manual_movement")||flag(state,"inventory_interface_paused")||!flag(state,"navigating"))return clearNavigation();
        JsonObject route=object(state,"material_air_navigation");
        String phase=text(route,"phase");
        // Terminal air-only snapshots remain available as receipts. They must
        // never cover the distance/ETA of a later ordinary cruise.
        if(!text(route,"outcome").isBlank()
                || !text(route,"world_session").isBlank()&&!text(route,"world_session").equals(text(state,"world_session"))
                || !java.util.Set.of("cruising","precise_braking","checking_restored_flight").contains(phase))return clearNavigation();
        try {
            double horizontal=route.get("horizontal_error").getAsDouble(),vertical=route.get("vertical_error").getAsDouble();
            if(!Double.isFinite(horizontal)||!Double.isFinite(vertical)||horizontal<0)return clearNavigation();
            double remaining=Math.hypot(horizontal,vertical);
            String identity=text(state,"world_session")+":"+text(state,"last_request");
            double eta=text(state,"last_request").isBlank()?-1:navigationEta.observe(identity,remaining,number(state,"time"));
            String action=phase.equals("checking_restored_flight")?"停靠确认":phase.equals("precise_braking")?"精确停靠":Math.abs(vertical)>1?"调整高度":"前进";
            String duration=eta<0?"计算中":durationLabel((long)Math.ceil(eta));
            return String.format(Locale.ROOT,"巡航 · 剩余 %.1f 格 · 预计 %s · %s",remaining,duration,action);
        }catch(Exception ignored){return clearNavigation();}
    }
    private static String clearNavigation(){navigationEta.clear();return "";}
    public static String durationLabel(long seconds){
        seconds=Math.max(1,seconds);
        if(seconds<60)return seconds+"秒";
        if(seconds<3600)return seconds/60+"分"+seconds%60+"秒";
        return seconds/3600+"小时"+(seconds%3600)/60+"分";
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
