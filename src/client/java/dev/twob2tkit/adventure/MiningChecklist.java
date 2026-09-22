package dev.twob2tkit.adventure;

import dev.twob2tkit.KitConfig;
import net.minecraft.client.Minecraft;

/** Preparation belongs to the mining page, not chat on every B press. */
public final class MiningChecklist {
    private String summary="进入世界后检查挖矿物资";
    private int checkTicks;
    public void beforeStart(Minecraft client,KitConfig config){
        if(client.player==null||client.level==null)return;
        ActivityRequirements.ensureLists(config);config.save();refresh(client,config);checkTicks=0;
    }
    public void tick(Minecraft client,KitConfig config,boolean active){
        if(!active||client.player==null||client.level==null){checkTicks=0;return;}
        if(++checkTicks>=200){checkTicks=0;refresh(client,config);}
    }
    public String summary(Minecraft client,KitConfig config){refresh(client,config);return summary;}
    private void refresh(Minecraft client,KitConfig config){
        if(client.player==null)return;
        String missing=ActivityRequirements.miningMissingSummary(client.player,config);
        summary=missing.isEmpty()?"挖矿物资已齐，记得预留背包空位":"物资提醒："+missing+"（不阻止开挖）";
    }
}
