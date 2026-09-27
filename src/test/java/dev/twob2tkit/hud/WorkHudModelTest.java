package dev.twob2tkit.hud;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class WorkHudModelTest {
    JsonObject json(String s){return JsonParser.parseString(s).getAsJsonObject();}
    JsonObject state(){return json("{connected:true,world_session:'w',control_revision:3,supervision_lease:{job_session:'j'},concrete:{active:true,completed:2,limit:8,status:'凝固中'}}");}
    JsonObject job(){return json("{active:true,world_session:'w',task_session:'j',control_revision:3,updated_at:10000,title:'混凝土制作',done:101,total:800,phase:'凝固并回收'}");}
    @Test void overallQuotaWinsOverSubBatch(){assertEquals("混凝土制作 · 101/800 · 凝固并回收",WorkHudModel.select(state(),job(),10001).line());}
    @Test void expiredWrongOwnerAndWorldFallBackToNative(){
        assertEquals("2/8",WorkHudModel.select(state(),job(),15001).progress());
        for(String field:new String[]{"world_session","task_session"}) {var j=job();j.addProperty(field,"other");assertEquals("2/8",WorkHudModel.select(state(),j,10001).progress());}
        var j=job();j.addProperty("control_revision",2);assertEquals("2/8",WorkHudModel.select(state(),j,10001).progress());
        assertEquals("2/8",WorkHudModel.select(state(),job(),9999).progress());
    }
    @Test void defensePreservesProgress(){var s=state();s.addProperty("guard_busy",true);var result=WorkHudModel.select(s,job(),10001);assertEquals("101/800",result.progress());assertEquals("防护中",result.phase());assertTrue(result.attention());}
    @Test void disconnectManualAndIdleClear(){var s=state();s.addProperty("connected",false);assertNull(WorkHudModel.select(s,job(),10001));s=state();s.addProperty("manual_movement",true);assertNull(WorkHudModel.select(s,job(),10001));assertNull(WorkHudModel.select(json("{connected:true}"),null,10001));}
    @Test void unlimitedHasNoDenominatorOrDuplicateCount(){var s=json("{connected:true,gravel:{active:true,collected:23,limit:0,status:'正在回收 · 已收集 23 块'}}");assertEquals("采集沙砾 · 已完成 23 · 正在回收",WorkHudModel.select(s,null,0).line());}
    @Test void malformedDataDoesNotCrash(){assertNull(WorkHudModel.select(json("{connected:true,concrete:[]}"),json("{active:[]}"),0));assertEquals("hello world",WorkHudModel.clean("§ahello\nworld"));}
    @Test void localMaterialTaskUsesExistingOverlayAndDefensePriority(){
        var s=state();s.add("material_job",json("{active:true,world_session:'w',title:'获取 白色混凝土',done:101,total:800,phase:'合成中'}"));
        assertEquals("获取 白色混凝土 · 101/800 · 合成中",WorkHudModel.select(s,null,10001).line());
        s.addProperty("guard_busy",true);assertEquals("防护中",WorkHudModel.select(s,null,10001).phase());
        s.addProperty("guard_busy",false);s.getAsJsonObject("material_job").addProperty("world_session","old-world");
        assertEquals("2/8",WorkHudModel.select(s,null,10001).progress());
    }
}
