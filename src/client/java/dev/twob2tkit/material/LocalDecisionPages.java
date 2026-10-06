package dev.twob2tkit.material;

import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitFormScreen;
import dev.twob2tkit.automation.DecisionImageCapture;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import java.nio.file.*;
import java.util.UUID;
import com.google.gson.JsonParser;

public final class LocalDecisionPages {
    private LocalDecisionPages() {}
    private static Minecraft mc(){return Minecraft.getInstance();}
    public static void open(Screen parent,KitConfig config){
        var page=new KitFormScreen(parent,"本地决策模型","Kit 直接调用本机模型并执行原生任务，不需要打开 ChatGPT 或 Ollama 窗口。")
            .bind(config).id("local-decision").lockWhen(MaterialJobs::running).status(()->LocalDecisionRuntime.status(mc()));
        page.bool("启用本地决策", "启用后服务随游戏运行；关闭后继续使用原生规则。",()->LocalDecisionRuntime.enabled(mc()),v->LocalDecisionRuntime.enable(mc(),v));
        page.cycle("模型", "只常驻一个模型；Clef Flash 可接收 Kit 游戏画面。",new String[]{"Clef Flash（文字与图片）","Nimble（结构化状态）"},
            ()->LocalDecisionRuntime.settings(mc()).get("local_model").getAsString().equals("nimble")?1:0,
            i->LocalDecisionRuntime.configure(mc(),"local_model",i==0?"clef-flash":"nimble"));
        page.bool("持续驻留", "同一模型连续复用，不在每次任务结束后卸载。退出游戏或关闭本地决策后释放。",
            ()->LocalDecisionRuntime.settings(mc()).get("keep_loaded").getAsBoolean(),v->LocalDecisionRuntime.configure(mc(),"keep_loaded",v));
        page.cycle("上下文", "较小上下文减少模型工作内存；过长输入会被拒绝，不截断事实。",new String[]{"2048","4096","8192"},
            ()->switch(LocalDecisionRuntime.settings(mc()).get("context_length").getAsInt()){case 2048->0;case 8192->2;default->1;},
            i->LocalDecisionRuntime.configure(mc(),"context_length",new int[]{2048,4096,8192}[i]));
        page.cycle("游戏画面", "自动：只在控制器要求视觉判断时截取游戏帧，不读取桌面。",new String[]{"关闭","自动","每次阶段决策"},
            ()->switch(LocalDecisionRuntime.settings(mc()).get("vision_mode").getAsString()){case "off"->0;case "always"->2;default->1;},
            i->LocalDecisionRuntime.configure(mc(),"vision_mode",new String[]{"off","auto","always"}[i]));
        page.liveNote(()->LocalDecisionRuntime.lastTest(mc()));
        page.action("测试当前游戏画面", "关闭界面，截取一帧并做只读分类，不移动或放置方块。",()->{
            try{
                if(!LocalDecisionRuntime.enabled(mc())||!LocalDecisionRuntime.settings(mc()).get("local_model").getAsString().equals("clef-flash"))throw new IllegalStateException("请先启用 Clef Flash");
                if(mc().player==null||mc().level==null)throw new IllegalStateException("进入世界后才能测试游戏画面");
                var state=JsonParser.parseString(Files.readString(mc().gameDirectory.toPath().resolve("config/twob2tkit/automation/status.json"))).getAsJsonObject();
                String world=state.get("world_session").getAsString();long revision=state.get("control_revision").getAsLong();
                mc().setScreen(null);
                DecisionImageCapture.request(mc(),"vision-probe-"+UUID.randomUUID().toString(),world,revision,
                    ()->{try{return JsonParser.parseString(Files.readString(mc().gameDirectory.toPath().resolve("config/twob2tkit/automation/status.json"))).getAsJsonObject().get("control_revision").getAsLong();}catch(Exception e){return -1L;}},
                    image->{if(!image.has("error"))LocalDecisionRuntime.probeImage(mc(),image);});
            }catch(Exception e){page.message(e.getMessage(),0xFFFF77);}
        });
        mc().setScreen(page);
    }
}
