package dev.twob2tkit;

import dev.twob2tkit.skills.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.world.item.*;

/** Skill browsing only. No task starts when opening a skill. */
public final class KitSkillPages {
    public static void open(Screen parent,KitConfig config){
        var feed=new SkillCatalogFeed(SkillCatalog.defaultPath());
        var list=new KitCollectionScreen<SkillCatalog.Entry>(parent,config,"skills","技能库","自动更新技能目录",
            ()->feed.view().entries(),SkillCatalog.Entry::rowTitle,
            e->e.description()+"\n"+e.originLabel()+" · 实战成功 "+e.successes()+" 次",SkillCatalog.Entry::search)
            .key(SkillCatalog.Entry::name).searchHint("搜索技能名称、用途或动作…")
            .liveDescription(()->feed.view().summary(System.currentTimeMillis())).refreshWhen(feed::revision)
            .filters(new String[]{"全部","已验证","候选"},(e,i)->i==0||(i==1?e.verified():!e.verified()))
            .icon(e->new ItemStack(e.verified()?Items.ENCHANTED_BOOK:Items.BOOK));
        list.onOpen(e->details(list,config,e));
        list.footer("刷新",feed::refresh);
        list.footer("学习说明",()->{
            var info=new KitFormScreen(list,"技能如何增加","查看规则不会启动任务").bind(config).recordDraft().id("skill-help");
            info.note("新技能会自动出现在列表中，可以搜索和按状态筛选。候选技能需要两次独立的原生成功记录，才会标记为已验证。");
            info.note("AI 建议先保存为经验；实际背包、位置或服务器放置确认参与验收。技能修改后生成新版本，重新积累验证。");
            info.note("当前记录的是 Kit 技能。Voyager 的原生 Mineflayer 技能尚未逐项迁移。这里可以查看技能，执行仍由 Kit 的任务控制器负责。");
            Minecraft.getInstance().setScreen(info);
        });
        Minecraft.getInstance().setScreen(list);
    }
    private static void details(Screen parent,KitConfig config,SkillCatalog.Entry e){
        var page=new KitFormScreen(parent,e.title(),"技能详情 · 查看不会执行").bind(config).recordDraft().id("skill:"+e.name()+":"+e.version());
        page.note(e.statusLabel()+" · 版本 "+e.version()+"\n来源："+e.originLabel());
        page.note(e.description());
        page.section("实际验证");page.note("成功 "+e.successes()+" 次 · 失败 "+e.failures()+" 次");
        page.section("使用参数");page.note(e.parameters().isEmpty()?"无额外参数":String.join("\n",e.parameters()));
        page.section("执行步骤");
        for(int i=0;i<e.steps().size();i++)page.note((i+1)+". "+e.steps().get(i));
        page.section("成功条件");page.note(String.join("\n",e.checks()));
        page.note("技能标识："+e.name());
        Minecraft.getInstance().setScreen(page);
    }
    private KitSkillPages(){}
}
