package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonObject;
import java.util.ArrayDeque;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LoadedVillagerEventsTest {
    @Test void native_handoffs_keep_queued_receipts_but_reload_world_exit_and_manual_stop_invalidate_them()throws Exception{
        var observer=new LoadedVillagerEvents();var field=LoadedVillagerEvents.class.getDeclaredField("epoch");field.setAccessible(true);
        var epoch=(java.util.concurrent.atomic.AtomicLong)field.get(observer);long initial=epoch.get();
        observer.workStopped("切换到脚本任务");observer.workStopped("使用投影打印机");assertEquals(initial,epoch.get());
        for(String reason:java.util.List.of("重新加载运行引擎","离开世界","工具箱停止全部","未知停止")){
            long before=epoch.get();observer.workStopped(reason);assertTrue(epoch.get()>before);
        }
    }
    @Test void impossible_pickup_quantities_and_nonfinite_positions_are_not_evidence(){
        assertFalse(LoadedVillagerEvents.validPickup(0));assertFalse(LoadedVillagerEvents.validPickup(-1));
        assertFalse(LoadedVillagerEvents.validPickup(65));assertTrue(LoadedVillagerEvents.validPickup(1));assertTrue(LoadedVillagerEvents.validPickup(64));
        assertTrue(LoadedVillagerEvents.validPoint(1,64,2));assertFalse(LoadedVillagerEvents.validPoint(Double.NaN,64,2));
        assertFalse(LoadedVillagerEvents.validPoint(1,Double.POSITIVE_INFINITY,2));
    }
    @Test void event_history_is_bounded_and_does_not_keep_old_world_pickup_times(){
        var events=new ArrayDeque<JsonObject>();
        for(int i=0;i<300;i++){var row=new JsonObject();row.addProperty("received_at",1000+i);row.addProperty("sequence",i);LoadedVillagerEvents.retain(events,row,1300);}
        assertEquals(256,events.size());assertEquals(44,events.getFirst().get("sequence").getAsInt());
        var latest=new JsonObject();latest.addProperty("received_at",200000);LoadedVillagerEvents.retain(events,latest,200000);
        assertEquals(1,events.size());assertSame(latest,events.getFirst());
    }
}
