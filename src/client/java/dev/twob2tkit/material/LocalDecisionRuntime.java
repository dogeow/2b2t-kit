package dev.twob2tkit.material;

import com.google.gson.*;
import dev.twob2tkit.KitConfig;
import net.minecraft.client.Minecraft;
import java.nio.file.*;
import java.util.UUID;

/** Optional Kit-owned local model service. No player actions are performed here. */
public final class LocalDecisionRuntime {
    private static Process process;
    private static long nextAttempt;
    private static Path folder(Minecraft c){return c.gameDirectory.toPath().resolve("config/twob2tkit/decision-advisor");}
    private LocalDecisionRuntime() {}
    public static JsonObject settings(Minecraft c){
        Path path=folder(c).resolve("settings.json");
        try{var j=defaults();if(Files.exists(path))JsonParser.parseString(Files.readString(path)).getAsJsonObject().entrySet().forEach(e->j.add(e.getKey(),e.getValue()));return j;}
        catch(Exception e){throw new IllegalStateException("本地模型配置不可读",e);}
    }
    private static JsonObject defaults(){
        var j=new JsonObject();j.addProperty("provider","native");j.addProperty("enabled",true);
        j.addProperty("local_model","clef-flash");j.addProperty("context_length",4096);
        j.addProperty("keep_loaded",true);j.addProperty("vision_mode","auto");j.addProperty("timeout_seconds",10);return j;
    }
    public static boolean enabled(Minecraft c){var j=settings(c);return j.has("provider")&&j.get("provider").getAsString().equals("ollama")&&j.get("enabled").getAsBoolean();}
    public static void configure(Minecraft c,String key,String value){
        var j=settings(c);j.addProperty(key,value);save(c,j);
    }
    public static void configure(Minecraft c,String key,int value){var j=settings(c);j.addProperty(key,value);save(c,j);}
    public static void configure(Minecraft c,String key,boolean value){var j=settings(c);j.addProperty(key,value);save(c,j);}
    public static void enable(Minecraft c,boolean value){
        var j=settings(c);j.addProperty("provider",value?"ollama":"native");j.addProperty("enabled",true);save(c,j);
        if(value)nextAttempt=0;else stop(c);
    }
    private static void save(Minecraft c,JsonObject value){
        try{Path folder=folder(c);Files.createDirectories(folder);Path temp=folder.resolve("settings.tmp");
            Files.writeString(temp,value.toString());Files.move(temp,folder.resolve("settings.json"),StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
        }catch(Exception e){throw new IllegalStateException("无法保存本地模型设置",e);}
    }
    public static String status(Minecraft c){
        try{
            var path=folder(c).resolve("runtime.json");if(!Files.exists(path))return enabled(c)?"等待启动本地服务":"本地模型关闭 · 原生任务仍可使用";
            var j=JsonParser.parseString(Files.readString(path)).getAsJsonObject();String phase=j.get("phase").getAsString();
            if(j.has("time")&&System.currentTimeMillis()-j.get("time").getAsDouble()*1000>20000)return "等待本地服务恢复";
            if(phase.equals("ready"))return "本地模型就绪："+j.get("model").getAsString()+" · "+j.get("context_length").getAsInt()+" 上下文 · "+String.format(java.util.Locale.ROOT,"%.1f",j.get("resident_bytes").getAsLong()/1e9)+" GB";
            if(phase.equals("warming"))return "模型加载中，当前仍由原生规则处理任务";
            if(phase.equals("error"))return "本地服务暂不可用："+j.get("detail").getAsString();
            return "本地模型服务已停止";
        }catch(Exception e){return "等待本地模型状态";}
    }
    public static void tick(Minecraft c,KitConfig config){
        if(System.currentTimeMillis()<nextAttempt)return;
        nextAttempt=System.currentTimeMillis()+5000;
        try{if(!enabled(c)||process!=null&&process.isAlive())return;}catch(RuntimeException invalidConfig){return;}
        try{
            Path worker=c.gameDirectory.toPath().resolve("config/twob2tkit/material-worker");
            Path script=worker.resolve("local_decision_runtime.py");if(!Files.isRegularFile(script))return;
            Path python=MaterialJobProtocol.resolvePython(config.materialJobsPython,worker,System.getenv("HOME"),System.getProperty("user.home"));
            Files.createDirectories(folder(c));
            process=new ProcessBuilder(python.toString(),script.toString(),"--game",c.gameDirectory.toPath().toString(),
                "--parent-pid",Long.toString(ProcessHandle.current().pid()))
                .redirectErrorStream(true).redirectOutput(ProcessBuilder.Redirect.appendTo(folder(c).resolve("service.log").toFile())).start();
        }catch(Exception e){nextAttempt=System.currentTimeMillis()+30000;}
    }
    public static void stop(Minecraft c){
        try{var j=new JsonObject();j.addProperty("id",UUID.randomUUID().toString());j.addProperty("kind","stop");
            Files.createDirectories(folder(c));Files.writeString(folder(c).resolve("control.json"),j.toString());
        }catch(Exception ignored){}
        if(process!=null&&process.isAlive())process.destroy();process=null;
    }
    public static void probeImage(Minecraft c,JsonObject image){
        try{var j=new JsonObject();j.addProperty("id",UUID.randomUUID().toString());j.addProperty("kind","probe_image");j.add("image",image);
            Files.writeString(folder(c).resolve("control.json"),j.toString());
        }catch(Exception e){throw new IllegalStateException("无法提交画面测试",e);}
    }
    public static String lastTest(Minecraft c){
        try{var j=JsonParser.parseString(Files.readString(folder(c).resolve("runtime.json"))).getAsJsonObject();
            if(!j.has("last_test")||j.get("last_test").isJsonNull())return "画面测试尚未运行";
            var result=j.getAsJsonObject("last_test");return result.has("choice")?"画面分类："+result.get("choice").getAsString()+" · "+result.get("elapsed_ms").getAsDouble()+" ms":"画面测试暂不可用";
        }catch(Exception e){return "画面测试尚未运行";}
    }
}
