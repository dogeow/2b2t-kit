package dev.twob2tkit.skills;

import com.google.gson.*;
import java.nio.file.*;
import java.io.IOException;
import java.util.*;

/** Read-only display data, independent of the learning database and all game controls. */
public final class SkillCatalog {
    public static final int MAX_BYTES=16*1024*1024;
    public record Entry(String name,String title,int version,String status,String description,int successes,int failures,
                        String origin,List<String> parameters,List<String> steps,List<String> checks,String search) {
        public boolean verified(){return status.equals("verified");}
        public String statusLabel(){return verified()?"已验证":status.equals("candidate")?"候选 · 待验证":"状态待确认";}
        public String originLabel(){return origin.equals("observed")?"本机执行记录":"模板或导入候选";}
        public String rowTitle(){return title+" · "+statusLabel()+" · v"+version;}
    }
    public record View(List<Entry> entries,long updatedMs,String error) {
        public long verified(){return entries.stream().filter(Entry::verified).count();}
        public String summary(long now){
            if(!error.isEmpty())return error;
            return (now-updatedMs<15000?"记录器在线":"目录未更新 · 显示已保存技能")+" · 已验证 "+verified()+" · 候选 "+(entries.size()-verified());
        }
    }
    public static Path defaultPath(){
        return resolvePath(System.getProperty("twob2tkit.skills.catalog",""),System.getenv("HOME"),System.getenv("USERPROFILE"),System.getProperty("user.home"));
    }
    /** HMCL may override Java user.home with the game directory; Python's publisher uses OS HOME. */
    public static Path resolvePath(String override,String home,String userProfile,String javaHome){
        if(override!=null&&!override.isBlank())return Path.of(override);
        for(String candidate:new String[]{home,userProfile,javaHome}){
            if(candidate==null||candidate.isBlank())continue;
            try{var path=Path.of(candidate);if(path.isAbsolute())return path.resolve(".minecraft-kit/skills/catalog.json");}
            catch(InvalidPathException ignored){}
        }
        throw new IllegalArgumentException("Cannot locate skill catalog home directory");
    }
    public static View read(Path path){
        if(!Files.isRegularFile(path))return new View(List.of(),0,"尚未收到技能目录，请检查技能记录器");
        try{
            if(Files.size(path)>MAX_BYTES)throw new IllegalArgumentException("技能目录过大");
            return parse(Files.readString(path));
        }catch(IOException|RuntimeException e){return new View(List.of(),0,"技能目录读取失败，请稍后刷新");}
    }
    public static View parse(String text){
        var root=JsonParser.parseString(text).getAsJsonObject();
        if(root.get("schema").getAsInt()!=1)throw new IllegalArgumentException("Unsupported skill catalog schema");
        var entries=new ArrayList<Entry>();var names=new HashSet<String>();
        for(var raw:root.getAsJsonArray("skills")){
            var s=raw.getAsJsonObject();String name=str(s,"name");
            if(name.isBlank()||!names.add(name))throw new IllegalArgumentException("Duplicate or missing skill id");
            var parameters=new ArrayList<String>();var p=object(s,"parameters");
            for(var kv:p.entrySet()){
                var spec=kv.getValue().isJsonObject()?kv.getValue().getAsJsonObject():new JsonObject();
                parameters.add(parameterLabel(kv.getKey())+(spec.has("required")&&spec.get("required").getAsBoolean()?"（必填）":""));
            }
            var steps=new ArrayList<String>();
            if(s.has("steps"))for(var v:s.getAsJsonArray("steps"))steps.add(operationLabel(str(v.getAsJsonObject(),"op")));
            var checks=new ArrayList<String>();
            if(s.has("success"))for(var v:s.getAsJsonArray("success"))checks.add(checkLabel(v.getAsJsonObject()));
            String title=str(s,"title");if(title.isBlank())title=name;
            String status=str(s,"status"),description=str(s,"description");
            String search=title+" "+name+" "+description+" "+status+" "+String.join(" ",steps)+" "+s.get("tags");
            entries.add(new Entry(name,title,num(s,"version"),status,description,num(s,"successful_runs"),num(s,"failed_runs"),str(s,"origin"),List.copyOf(parameters),List.copyOf(steps),List.copyOf(checks),search));
        }
        entries.sort(Comparator.comparing(Entry::verified).reversed().thenComparing(Entry::title));
        return new View(List.copyOf(entries),root.get("updated_ms").getAsLong(),"");
    }
    private static JsonObject object(JsonObject s,String key){return s.has(key)&&s.get(key).isJsonObject()?s.getAsJsonObject(key):new JsonObject();}
    private static String str(JsonObject s,String key){return s.has(key)&&s.get(key).isJsonPrimitive()?s.get(key).getAsString():"";}
    private static int num(JsonObject s,String key){return s.has(key)?Math.max(0,s.get(key).getAsInt()):0;}
    public static String parameterLabel(String key){return switch(key){
        case "item"->"原木种类";case "target_count"->"目标物品数量";case "seconds"->"执行时限（秒）";
        case "target"->"目标坐标 X / Y / Z";case "arrival"->"到点误差（格）";
        case "conservative"->"保守放置";case "restore_flight"->"完成后恢复飞行";default->key;};}
    public static String operationLabel(String key){return switch(key){
        case "chop"->"采集原木";case "walk"->"步行到指定位置";case "navigate"->"飞行到指定位置";
        case "professional_print"->"打印附近投影方块";case "scan"->"读取附近方块";default->key;};}
    private static String value(JsonObject s,String key){
        if(!s.has(key))return "指定值";var v=s.get(key);
        if(v.isJsonObject()&&v.getAsJsonObject().has("param"))return parameterLabel(str(v.getAsJsonObject(),"param"));
        return v.isJsonPrimitive()?v.getAsString():"指定位置";
    }
    private static String checkLabel(JsonObject s){return switch(str(s,"type")){
        case "inventory_at_least"->"背包中的"+value(s,"item")+"达到"+value(s,"count");
        case "position_near"->"实际位置到达"+value(s,"target")+"，误差不超过"+value(s,"radius")+"格";
        case "server_placements_at_least"->"服务器确认至少 "+value(s,"count")+" 格放置成功";
        default->"需要额外验收";};}
    private SkillCatalog(){}
}
