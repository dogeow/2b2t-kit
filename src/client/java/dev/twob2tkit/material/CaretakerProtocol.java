package dev.twob2tkit.material;

import com.google.gson.*;
import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.util.*;

/** The existing caretaker profile/journal/control contract; never generates a shell command. */
public final class CaretakerProtocol {
    private CaretakerProtocol() {}
    public record Installation(Path game,Path python,Path script,Path profilePath,JsonObject profile,Path directory,String key){
        public List<String> command(String action){
            if(!Set.of("run","pause","stop","status","resume").contains(action))throw new IllegalArgumentException("农场操作无效");
            return List.of(python.toString(),"-u",script.toString(),"--game-dir",game.toString(),"--profile",profilePath.toString(),action);
        }
    }
    public static Installation installed(Path game)throws IOException{
        game=game.toAbsolutePath().normalize();Path config=game.resolve("config/twob2tkit"),root=config.resolve("material-worker");
        Path script=root.resolve("farm_caretaker_cli.py");verifySources(root);
        Path marker=root.resolve("runtime-python.txt");
        if(!Files.isRegularFile(marker))throw new IllegalStateException("农场本地 Python 运行环境未安装");
        Path python=MaterialJobProtocol.resolvePython("",script,null,null);
        if(!Files.isRegularFile(python)||!Files.isExecutable(python)||!python.getFileName().toString().matches("python(?:3(?:\\.\\d+)?)?"))
            throw new IllegalStateException("农场 Python 路径无效，不能作为任意程序入口");
        Path profilePath=config.resolve("farm-caretaker-profile.json");JsonObject profile=profile(read(profilePath));
        String key=hash((text(profile,"server")+"|"+text(profile,"dimension")).getBytes(StandardCharsets.UTF_8)).substring(0,20);
        Path home=config.resolve("automation/farm-caretakers").resolve(key),directory=home.resolve("journal");
        Path registry=home.resolve("registry.json");
        if(Files.exists(registry)){
            JsonObject value=read(registry);
            if(!profile.equals(value.get("profile"))||!directory.equals(Path.of(text(value,"directory")).toAbsolutePath().normalize()))
                throw new IllegalStateException("农场登记配置或记录目录已改变，请先人工核对原周期");
        }
        return new Installation(game,python,script,profilePath,profile,directory,key);
    }
    /** Verify every installed Python source listed by the existing installer manifest, including imports. */
    public static void verifySources(Path root)throws IOException{
        JsonObject manifest=read(root.resolve("worker-manifest.json"));
        if(integer(manifest,"schema")!=1||!manifest.has("files")||!manifest.get("files").isJsonObject())throw new IllegalStateException("农场后台清单无效");
        JsonObject files=manifest.getAsJsonObject("files");
        if(files.size()>1024||!files.has("farm_caretaker_cli.py")||!files.has("farm_caretaker.py")||!files.has("farm_caretaker_stages.py"))
            throw new IllegalStateException("农场后台源码未安装完整");
        Path actualRoot=root.toRealPath();long total=0;
        for(var entry:files.entrySet()){
            String relative=entry.getKey(),expected=entry.getValue().getAsString();Path path=root.resolve(relative).normalize();
            if((!relative.endsWith(".py")&&!relative.equals("requirements.txt"))||Path.of(relative).isAbsolute()||!path.startsWith(root.normalize())
                    ||!expected.matches("[a-f0-9]{64}")||!Files.isRegularFile(path)||!path.toRealPath().startsWith(actualRoot)
                    ||Files.size(path)>2_000_000||(total+=Files.size(path))>20_000_000||!hash(Files.readAllBytes(path)).equals(expected))
                throw new IllegalStateException("农场后台源码校验失败，请更新 Kit 后台");
        }
    }
    public static JsonObject profile(JsonObject input){
        JsonObject p=input.deepCopy();
        if(integer(p,"schema")!=1||!bool(p,"authorized")||text(p,"server").isBlank()||!text(p,"dimension").equals("minecraft:overworld"))
            throw new IllegalArgumentException("需要已授权的本地农场配置");
        p.addProperty("server",server(text(p,"server").strip()));
        defaults(p,"interval_seconds",300,1,86400);defaults(p,"adult_keep",20,2,64);
        defaults(p,"potato_reserve",4,4,4);defaults(p,"cooked_food_reserve",8,8,64);
        if(!p.has("potato_fields"))p.add("potato_fields",new JsonArray());
        if(!p.has("livestock_types")){var types=new JsonArray();if(p.has("livestock_region")){types.add("minecraft:cow");types.add("minecraft:sheep");}p.add("livestock_types",types);}
        if(p.getAsJsonArray("potato_fields").size()>8||p.getAsJsonArray("livestock_types").size()>3
                ||p.getAsJsonArray("potato_fields").isEmpty()&&p.getAsJsonArray("livestock_types").isEmpty())throw new IllegalArgumentException("农场尚未登记田块或畜牧区域");
        for(var field:p.getAsJsonArray("potato_fields")){
            var f=field.getAsJsonObject();int radius=f.has("radius")?(int)integer(f,"radius"):2;
            if(!bool(f,"authorized")||radius<1||radius>2)throw new IllegalArgumentException("仅支持已登记的小型土豆田");blockPoint(f.getAsJsonArray("center"));
            double y=f.getAsJsonArray("center").get(1).getAsDouble();if(y< -63||y>317)throw new IllegalArgumentException("土豆田高度无效");
        }
        var seen=new HashSet<String>();for(var type:p.getAsJsonArray("livestock_types"))
            if(!Set.of("minecraft:cow","minecraft:sheep","minecraft:chicken").contains(type.getAsString())||!seen.add(type.getAsString()))throw new IllegalArgumentException("畜牧类型无效");
        point(p.getAsJsonArray("park_target"));var depots=p.getAsJsonArray("depots");if(depots.isEmpty()||depots.size()>16)throw new IllegalArgumentException("请登记农场存箱位置");
        var points=new ArrayList<JsonArray>();var depotKeys=new HashSet<String>();
        for(var d:depots){blockPoint(d.getAsJsonArray());if(!depotKeys.add(d.toString()))throw new IllegalArgumentException("存箱位置不能重复");points.add(d.getAsJsonArray());}
        for(var f:p.getAsJsonArray("potato_fields"))points.add(f.getAsJsonObject().getAsJsonArray("center"));
        if(!p.getAsJsonArray("livestock_types").isEmpty()){
            var region=p.getAsJsonObject("livestock_region");if(region==null)throw new IllegalArgumentException("畜牧区域尚未登记");
            var low=region.getAsJsonArray("min");var high=region.getAsJsonArray("max");blockPoint(low);blockPoint(high);long volume=1;
            for(int i=0;i<3;i++){long width=high.get(i).getAsLong()-low.get(i).getAsLong()+1;if(width<1||width>32)throw new IllegalArgumentException("畜牧区域超过已支持的边界");volume*=width;}
            if(volume>8192)throw new IllegalArgumentException("畜牧区域过大");points.add(low);points.add(high);
        }
        var park=p.getAsJsonArray("park_target");for(var pos:points)if(Math.hypot(pos.get(0).getAsDouble()-park.get(0).getAsDouble(),pos.get(2).getAsDouble()-park.get(2).getAsDouble())>32)throw new IllegalArgumentException("所有登记区域须在停车点水平32格内");
        return p;
    }
    public static JsonObject journal(Installation installation)throws IOException{
        Path file=installation.directory().resolve("caretaker.json");if(!Files.exists(file))return null;
        JsonObject value=read(file);
        if(integer(value,"schema")!=1||!installation.profile().equals(value.get("profile"))||integer(value,"ai_calls")!=0
                ||integer(value,"cycle")<0||!Set.of("harvest_store","breed","surplus","cook_store").contains(text(value,"stage")))throw new IllegalStateException("农场原周期记录无效，禁止重新开始");
        bool(value,"enabled");bool(value,"paused");return value;
    }
    public static void requireReady(Installation installation,JsonObject state,JsonObject journal,long now,boolean allowKitScreen){
        if(journal!=null&&journal.has("pending")&&!journal.get("pending").isJsonNull())throw new IllegalStateException("原周期有未确认动作，须先人工核对，不能重放");
        if(!bool(state,"connected")||!server(text(state,"server")).equals(text(installation.profile(),"server"))
                ||!text(state,"dimension").equals(text(installation.profile(),"dimension"))||text(state,"world_session").isBlank()
                ||integer(state,"control_revision")<0||now-integer(state,"time")>2500||integer(state,"time")>now+2000
                ||integer(state,"health")!=20||integer(state,"food")<18||bool(state,"under_water")||bool(state,"manual_movement"))
            throw new IllegalStateException("世界、生命、食物、输入或新鲜状态尚未就绪");
        if(journal!=null&&journal.has("current_cycle")&&!journal.get("current_cycle").isJsonNull()
                &&(!text(journal,"world_session").equals(text(state,"world_session"))
                ||!text(journal.getAsJsonObject("current_cycle"),"world_session").equals(text(state,"world_session"))))
            throw new IllegalStateException("未完成原周期的世界已改变，须先人工核对");
        String screen=text(state,"screen");if(!screen.isBlank()&&!(allowKitScreen&&screen.startsWith("Kit")))throw new IllegalStateException("请先关闭其它界面");
        for(String flag:List.of("borer_active","chopping","navigating","printing","planter_active","feeder_active","fisher_active","native_material_busy","guard_busy","health_recovery_hold"))
            if(state.has(flag)&&bool(state,flag))throw new IllegalStateException("其他作业仍在运行，农场不会抢控制");
        if(state.has("build_job")&&state.getAsJsonObject("build_job").has("active")&&bool(state.getAsJsonObject("build_job"),"active"))throw new IllegalStateException("建造作业仍在运行");
        if(state.has("supervision_lease")&&!state.get("supervision_lease").isJsonNull()){
            var lease=state.getAsJsonObject("supervision_lease");
            // Explicit run/resume may reuse a proven idle high guarded park; never a running work lease.
            if(!text(lease,"kind").equals("parking")||!text(lease,"world_session").equals(text(state,"world_session"))
                    ||integer(lease,"revision")!=integer(state,"control_revision")||!bool(state,"guard_armed")||!bool(state,"guard_pve_only")||!bool(state,"flight"))
                throw new IllegalStateException("当前租约尚非空闲高空防护，农场不会接管");
        }
        var pos=state.getAsJsonArray("pos");point(pos);var park=installation.profile().getAsJsonArray("park_target");
        if(Math.hypot(pos.get(0).getAsDouble()-park.get(0).getAsDouble(),pos.get(2).getAsDouble()-park.get(2).getAsDouble())>32)
            throw new IllegalStateException("请先手动前往已登记农场附近");
    }
    public static void requireUnlocked(Path automation,JsonObject state)throws IOException{
        for(String name:List.of("assistant-control-hold.json","safety-hold.json")){
            Path path=automation.resolve(name);if(Files.exists(path)&&bool(read(path),"active"))throw new IllegalStateException("安全或控制锁仍开启，请先由玩家处理");
        }
        if(state.has("safety_hold")&&state.getAsJsonObject("safety_hold").has("active")&&bool(state.getAsJsonObject("safety_hold"),"active"))throw new IllegalStateException("游戏安全锁仍开启");
        Path health=automation.resolve("material-health-hold.json");if(Files.exists(health)){
            var hold=read(health);if(bool(hold,"active")){
                Path nativePath=automation.resolve("safety-hold.json");var nativeHold=Files.exists(nativePath)?read(nativePath):new JsonObject();
                if(!text(nativeHold,"cleared_by").equals("game_ui")||integer(nativeHold,"cleared_at")<=integer(hold,"time"))throw new IllegalStateException("生命值安全锁需要玩家恢复后确认");
            }
        }
    }
    public static void control(Installation installation,String action)throws IOException{
        if(!Set.of("pause","stop","resume").contains(action))throw new IllegalArgumentException("农场操作无效");
        if(journal(installation)==null)throw new IllegalStateException("尚无可控制的农场周期记录");
        var value=new JsonObject();value.addProperty("id",UUID.randomUUID().toString().replace("-",""));value.addProperty("action",action);value.addProperty("key",installation.key());
        Path path=installation.directory().resolve("control.json"),temp=Files.createTempFile(installation.directory(),".caretaker-control-",".json");
        try{Files.writeString(temp,value.toString());Files.move(temp,path,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}finally{Files.deleteIfExists(temp);}
    }
    /** Only the verified CLI's real flock probe can establish an external worker is alive. */
    public static boolean workerRunning(JsonObject reply){return bool(reply,"worker_running");}
    public static String summary(JsonObject p){
        int potatoes=0;for(var raw:p.getAsJsonArray("potato_fields")){var f=raw.getAsJsonObject();int r=f.has("radius")?(int)integer(f,"radius"):2;potatoes+=(2*r+1)*(2*r+1)-1;}
        var types=new ArrayList<String>();for(var t:p.getAsJsonArray("livestock_types"))types.add(switch(t.getAsString()){case "minecraft:cow"->"牛";case "minecraft:sheep"->"羊";case "minecraft:chicken"->"鸡";default->"未登记";});
        return "已登记 "+potatoes+" 格土豆田 · "+String.join("、",types)+"；每 "+integer(p,"interval_seconds")+" 秒检查，每种保留 "+integer(p,"adult_keep")+" 成体、"+integer(p,"potato_reserve")+" 种薯、"+integer(p,"cooked_food_reserve")+" 熟食。";
    }
    public static String status(JsonObject journal,boolean alive){
        String process=alive?"本地后台存活":"后台未确认运行";if(journal==null)return process+" · 尚无周期记录";
        boolean pending=journal.has("pending")&&!journal.get("pending").isJsonNull();
        return process+" · "+(pending?"原动作待核对，不能重放":bool(journal,"paused")?"已暂停":bool(journal,"enabled")?"记录已启用":"记录已停用")
            +" · 第 "+integer(journal,"cycle")+" 轮 · "+switch(text(journal,"stage")){case "harvest_store"->"收田存箱";case "breed"->"繁殖";case "surplus"->"检查富余成体";case "cook_store"->"烹饪存箱";default->"未知阶段";}
            +(text(journal,"reason").isBlank()?"":" · "+text(journal,"reason"));
    }
    public static JsonObject read(Path path)throws IOException{
        if(!Files.isRegularFile(path)||Files.size(path)>262144)throw new IllegalStateException("农场配置或记录不可读取");
        try{return JsonParser.parseString(Files.readString(path)).getAsJsonObject();}catch(RuntimeException error){throw new IllegalStateException("农场配置或记录格式无效",error);}
    }
    private static void defaults(JsonObject p,String key,int defaultValue,int low,int high){if(!p.has(key))p.addProperty(key,defaultValue);long value=integer(p,key);if(value<low||value>high)throw new IllegalArgumentException("农场策略无效："+key);}
    private static void point(JsonArray values){
        if(values==null||values.size()!=3)throw new IllegalArgumentException("农场坐标无效");
        for(var v:values)if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isNumber()||!Double.isFinite(v.getAsDouble()))throw new IllegalArgumentException("农场坐标无效");
        if(Math.abs(values.get(0).getAsDouble())>30000000||Math.abs(values.get(2).getAsDouble())>30000000||values.get(1).getAsDouble()< -64||values.get(1).getAsDouble()>319)throw new IllegalArgumentException("农场坐标超出支持范围");
    }
    private static void blockPoint(JsonArray values){point(values);for(var value:values)if(value.getAsDouble()!=Math.rint(value.getAsDouble()))throw new IllegalArgumentException("方块位置必须是整数");}
    public static String text(JsonObject object,String key){return object.has(key)&&!object.get(key).isJsonNull()?object.get(key).getAsString():"";}
    private static long integer(JsonObject object,String key){try{var p=object.getAsJsonPrimitive(key);double value=p.getAsDouble();if(!p.isNumber()||!Double.isFinite(value)||value!=Math.rint(value))throw new IllegalArgumentException();return p.getAsLong();}catch(RuntimeException e){throw new IllegalStateException("农场状态字段缺失或无效："+key);}}
    private static boolean bool(JsonObject object,String key){try{var p=object.getAsJsonPrimitive(key);if(!p.isBoolean())throw new IllegalArgumentException();return p.getAsBoolean();}catch(RuntimeException e){throw new IllegalStateException("农场状态字段缺失或无效："+key);}}
    private static String server(String value){value=value.toLowerCase(Locale.ROOT);return value.endsWith(":25565")?value.substring(0,value.length()-6):value;}
    private static String hash(byte[] bytes){try{return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(bytes));}catch(java.security.NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}}
}
