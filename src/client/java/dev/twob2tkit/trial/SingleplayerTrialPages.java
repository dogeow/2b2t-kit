package dev.twob2tkit.trial;
import dev.twob2tkit.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.screens.worldselection.CreateWorldScreen;
public final class SingleplayerTrialPages {
    private SingleplayerTrialPages(){}
    public static void open(Screen parent,KitConfig config){
        var c=Minecraft.getInstance();var page=new KitFormScreen(parent,"单人通关试验","Clef Flash 选择阶段步骤，Kit 正常挖掘、合成和移动；记录真实结果与经验。")
            .bind(config).id("singleplayer-trial").status(()->SingleplayerTrialRuntime.status(c));
        page.note("目标：击败末影龙。只操作你在此页面登记的单人生存试验存档；允许死亡和正常复活。经验可以在第二个试验世界复用，地点重新发现。");
        page.action("新建独立单人世界","退出当前世界后，创建以 Clef Dragon Trial 开头的普通生存世界。",()->{
            if(c.player!=null){page.message("请先保存退出当前世界，再新建独立试验世界",0xFFFF77);return;}
            perform(page,()->SingleplayerTrialApi.create(c));
        });
        page.action("开始打龙目标","登记当前新建单人存档并启动游戏托管试验。",()->perform(page,()->SingleplayerTrialRuntime.start(c,config)));
        page.action("暂停试验","停止当前动作后保留目标、阶段和经验。",()->perform(page,()->SingleplayerTrialRuntime.control(c,"pause")));
        page.action("继续试验","重新核对当前单人存档后继续，不复用旧世界坐标。",()->perform(page,()->SingleplayerTrialRuntime.control(c,"resume")));
        page.action("停止试验","只结束本轮，保留真实进度和经验文件。",()->perform(page,()->SingleplayerTrialRuntime.control(c,"cancel")));
        page.action("本地决策模型","查看 Clef Flash 是否就绪与游戏画面设置。",()->dev.twob2tkit.material.LocalDecisionPages.open(page,config));
        page.liveNote(()->SingleplayerTrialRuntime.status(c));
        c.setScreen(page);
    }
    private static void perform(KitFormScreen page,Runnable action){try{action.run();}catch(Exception e){page.message(e.getMessage(),0xFFFF77);}}
}
