package dev.twob2tkit.storage;

import dev.twob2tkit.*;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.core.registries.BuiltInRegistries;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

/** Nearby accounting page never opens containers or starts supply automation. */
public final class NearbyInventoryScreen {
    private NearbyInventoryScreen() {}
    private static final DateTimeFormatter TIME=DateTimeFormatter.ofPattern("MM-dd HH:mm").withZone(ZoneId.systemDefault());
    private static String time(long value){return value<=0?"时间未知":TIME.format(Instant.ofEpochMilli(value));}
    static String summary(NearbyInventory.Item item){
        if(item.sources().isEmpty())return "附近没有此物品的已记录缓存";
        return "缓存内容 "+time(item.oldestContentTime())+(item.latestContentTime()==item.oldestContentTime()?"":" ～ "+time(item.latestContentTime()))
            +" · "+item.sources().size()+" 处"+(item.dirty()?" · 待确认":" · 取料时确认");
    }
    private static final class View {
        private final KitConfig config;private List<NearbyInventory.Item> items=List.of();
        View(KitConfig config){this.config=config;revision();}
        long revision(){
            var c=Minecraft.getInstance();var backpack=new ArrayList<KitConfig.StoredItem>();
            if(c.player!=null&&c.level!=null)for(int i=0;i<c.player.getInventory().getContainerSize();i++){
                var stack=c.player.getInventory().getItem(i);if(!stack.isEmpty())backpack.add(new KitConfig.StoredItem(
                    BuiltInRegistries.ITEM.getKey(stack.getItem()).toString(),stack.getHoverName().getString(),stack.getCount()));
            }
            items=NearbyInventory.summarize(backpack,config.storageSnapshots,StorageLifecycle.scope(c),c.player==null?"":c.player.getUUID().toString(),
                c.player==null?0:c.player.getX(),c.player==null?0:c.player.getZ());
            return items.hashCode();
        }
    }
    public static void open(Screen parent,KitConfig config){
        var view=new View(config);
        var list=new KitCollectionScreen<NearbyInventory.Item>(parent,config,"nearby-inventory","查看我物品数量 · 附近物资",
            "当前服务器与维度 · 水平4096格内；附近缓存是已记录预计数量",
            ()->view.items,item->item.name()+" · 预计总量 "+item.estimatedTotal()+"（含缓存）",
            item->item.id()+"\n背包实际 "+item.carried()+"；附近缓存 "+item.cached()+"\n"+summary(item),
            item->item.name()+" "+item.id()).key(NearbyInventory.Item::id)
            .icon(item->StorageItems.stack(new KitConfig.StoredItem(item.id(),item.name(),1)))
            .comparisonColumns(item->"背包实际："+item.carried(),item->"附近缓存："+item.cached())
            .summary((item,query)->summary(item)).searchHint("搜索物品名称或ID…")
            .liveDescription(()->"当前服务器/维度 · 水平4096格内 · 背包含装备/副手 · 缓存取料时确认")
            .refreshWhen(view::revision);
        list.onOpen(item->sources(list,config,view,item.id()));
        list.footer("刷新数量",()->{view.revision();list.refresh();});Minecraft.getInstance().setScreen(list);
    }
    private static void sources(Screen parent,KitConfig config,View view,String id){
        var item=view.items.stream().filter(row->row.id().equals(id)).findFirst().orElse(null);if(item==null)return;
        if(item.sources().isEmpty()){
            var detail=new KitFormScreen(parent,item.name(),"背包物品数量").bind(config);
            detail.note(item.id()+" · 打开时背包实际 "+item.carried());
            detail.note("附近缓存 0；只汇总当前服务器/维度水平4096格内已记录的内容");
            Minecraft.getInstance().setScreen(detail);return;
        }
        var list=new KitCollectionScreen<NearbyInventory.Source>(parent,config,"nearby-sources:"+id,item.name()+" · 缓存来源",
            "背包实际 "+item.carried()+" · 附近缓存 "+item.cached()+" · 预计总量 "+item.estimatedTotal()+"（含缓存）",
            ()->view.items.stream().filter(row->row.id().equals(id)).findFirst().map(NearbyInventory.Item::sources).orElse(List.of()),
            source->StorageLabels.headline(source.record())+" · 缓存 "+source.count(),
            source->"X "+source.record().x+" Y "+source.record().y+" Z "+source.record().z+"\n"+StorageLabels.evidenceSummary(source.record()),
            source->StorageLabels.headline(source.record())+" "+source.record().x+" "+source.record().z)
            .key(NearbyInventory.Source::key).summary((source,query)->"水平 "+Math.round(source.distance())+" 格 · 内容 "+time(source.observedAt())
                +(source.dirty()?" · 待确认":" · 取料时确认")).refreshWhen(view::revision)
            .liveDescription(()->{
                var current=view.items.stream().filter(row->row.id().equals(id)).findFirst().orElse(null);
                return "背包实际 "+(current==null?0:current.carried())+" · 附近缓存 "+(current==null?0:current.cached())
                    +" · 当前维度4096格内 · 末影共享只计一次";
            });
        list.onOpen(source->Minecraft.getInstance().setScreen(new StorageDetailScreen(list,source.record())));
        Minecraft.getInstance().setScreen(list);
    }
}
