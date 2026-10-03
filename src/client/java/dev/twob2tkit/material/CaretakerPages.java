package dev.twob2tkit.material;

import dev.twob2tkit.KitConfig;
import dev.twob2tkit.KitFormScreen;
import dev.twob2tkit.KitConfirmScreen;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;

/** Production entry for the existing registered farm cycles. Opening this page never starts a worker. */
public final class CaretakerPages {
    private CaretakerPages() {}
    public static void open(Screen parent,KitConfig config){
        var client=Minecraft.getInstance();CaretakerJobs.inspect(client);
        var page=new KitFormScreen(parent,"农场周期管家","本地周期收田、繁殖、检查富余成体、烹饪和存箱。")
            .bind(config).id("farm-caretaker").status(CaretakerJobs::status)
            .footerHint("只执行已登记区域 · 未确认动作须人工核对 · 恢复不会解除安全锁");
        page.liveNote(CaretakerJobs::scope);
        page.note("当前实际登记为小型土豆田和牛、羊区域。其它田块和动物不会自动纳入；是否完成以原周期回执为准。");
        page.section("当前周期记录").liveNote(CaretakerJobs::status);
        page.action("开始本地周期", "关闭页面，重新核对世界、输入、健康和已有任务，然后启动本地后台。",()->perform(page,()->CaretakerJobs.start(client)));
        page.action("暂停周期", "关闭页面，让当前动作安全收尾；记录确认后显示已暂停。",()->perform(page,()->CaretakerJobs.pause(client)));
        page.action("停止周期", "停止后保留已完成工作和未确认动作；不会自动恢复。",()->perform(page,()->CaretakerJobs.stopSchedule(client)));
        page.action("恢复已暂停周期", "重新核对实际安全和记录；原动作未确认时禁止重放。",()->perform(page,()->CaretakerJobs.resume(client)));
        page.action("查看待核对动作", "只读原阶段、所需物资和世界差异，列出实际需要核对的记录；不会清除或重放动作。",()->openReview(page,config));
        page.action("刷新真实记录", "读取同一农场持久记录；不会启动或执行游戏动作。",()->CaretakerJobs.refresh());
        page.action("复制周期记录路径", "复制原周期日志位置，便于核对待确认动作。",()->{
            var directory=CaretakerJobs.directory();if(directory==null){page.message("尚无可读取的农场记录目录",0xFFFF77);return;}
            client.keyboardHandler.setClipboard(directory.toString());page.message("已复制原周期记录路径",0x77DDCC);
        });
        client.setScreen(page);
    }
    private static void openReview(Screen parent,KitConfig config){
        var client=Minecraft.getInstance();
        var page=new KitFormScreen(parent,"农场待核对动作","核对原动作的实际结果，保留原周期历史。")
            .bind(config).id("farm-caretaker-review").status(CaretakerJobs::status).footerHint("原记录保留 · 归档须明确确认 · 安全锁保持原状态");
        page.liveNote(CaretakerJobs::status);
        for(String line:CaretakerJobs.pendingReview(client))page.note(line);
        page.action("归档旧周期并准备新周期","需明确确认已核对物品安全；保留原未知结果和全部证据，不重放旧动作。",()->openArchiveConfirmation(page,client));
        page.action("刷新核对记录","重新读取同一周期的记录。",()->openReview(parent,config));
        page.action("复制周期记录路径","复制原记录目录，查看原 stage.json 和 backend 回执。",()->{
            var directory=CaretakerJobs.directory();if(directory==null){page.message("尚无可读取的农场记录目录",0xFFFF77);return;}
            client.keyboardHandler.setClipboard(directory.toString());page.message("已复制原周期记录路径",0x77DDCC);
        });
        client.setScreen(page);
    }
    private static void openArchiveConfirmation(KitFormScreen page,Minecraft client){
        perform(page,()->{
            var preview=CaretakerJobs.previewArchive(client);
            client.setScreen(new KitConfirmScreen(page,"归档第 "+preview.cycle()+" 轮未知结果",
                "我已核对物品安全，归档旧周期并从当前状态新建。\n原周期及未确认动作完整保留，结果标为未知；归档不会取料或解除安全锁。\n归档完成后，再按“开始本地周期”才会新建第 "+(preview.cycle()+1)+" 轮。",
                ()->perform(page,()->CaretakerJobs.archivePending(client,preview))));
        });
    }
    private static void perform(KitFormScreen page,Runnable action){
        try{action.run();}catch(RuntimeException failure){page.message(failure.getMessage()==null?"农场操作未能执行":failure.getMessage(),0xFF7777);}
    }
}
