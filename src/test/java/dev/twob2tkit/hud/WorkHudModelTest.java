package dev.twob2tkit.hud;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class WorkHudModelTest {
    @Test void oldAirArrivalCannotOverrideANewMovingCruise(){
        var s=state();s.addProperty("navigating",true);s.addProperty("op","navigate");s.addProperty("phase","running");
        s.add("material_air_navigation",json("{phase:'confirmed',outcome:'done',horizontal_error:0,vertical_error:0}"));
        assertEquals("",WorkHudModel.navigation(s));
    }
    JsonObject json(String s){return JsonParser.parseString(s).getAsJsonObject();}
    JsonObject state(){return json("{connected:true,world_session:'w',control_revision:3,supervision_lease:{job_session:'j'},concrete:{active:true,completed:2,limit:8,status:'凝固中'}}");}
    JsonObject job(){return json("{active:true,world_session:'w',task_session:'j',control_revision:3,updated_at:10000,title:'混凝土制作',done:101,total:800,phase:'凝固并回收'}");}
    @Test void shortMaterialFlightHasItsOwnNavigationLineAlongsideTheTask() {
        var s=state();s.addProperty("navigating",true);
        s.add("material_air_navigation",json("{phase:'cruising',horizontal_error:8,vertical_error:0.1}"));
        assertEquals("巡航 · 剩余 8.0 格 · 预计 计算中 · 前进",WorkHudModel.navigation(s));
        assertEquals("101/800",WorkHudModel.select(s,job(),10001).progress());
        s.getAsJsonObject("material_air_navigation").addProperty("vertical_error",10);
        assertTrue(WorkHudModel.navigation(s).contains("调整高度"));
        s.getAsJsonObject("material_air_navigation").addProperty("phase","precise_braking");
        String braking=WorkHudModel.navigation(s);
        assertTrue(braking.contains("剩余 12.8 格"));
        assertTrue(braking.contains("预计"));assertTrue(braking.contains("精确停靠"));
        s.addProperty("navigating",false);assertEquals("",WorkHudModel.navigation(s));
    }
    @Test void stoppedAirReceiptNeverHidesCurrentOrdinaryCruiseMetrics(){
        for(String outcome:new String[]{"done","stopped","waiting","error","manual_handoff"}){
            var s=state();s.addProperty("navigating",true);
            s.add("material_air_navigation",json("{phase:'precise_braking',outcome:'"+outcome+"',horizontal_error:23,vertical_error:14}"));
            assertEquals("",WorkHudModel.navigation(s),outcome);
        }
    }
    @Test void airCruiseEtaUsesActualProgressAndResetsForTheNextRequest(){
        var s=state();s.addProperty("navigating",true);s.addProperty("last_request","eta-live-test");
        s.addProperty("time",1000);
        s.add("material_air_navigation",json("{phase:'cruising',horizontal_error:100,vertical_error:0}"));
        assertTrue(WorkHudModel.navigation(s).contains("计算中"));
        s.addProperty("time",2000);s.getAsJsonObject("material_air_navigation").addProperty("horizontal_error",90);
        assertTrue(WorkHudModel.navigation(s).contains("预计 9秒"));
        s.addProperty("time",3000);s.getAsJsonObject("material_air_navigation").addProperty("phase","precise_braking");
        s.getAsJsonObject("material_air_navigation").addProperty("horizontal_error",80);
        String line=WorkHudModel.navigation(s);assertTrue(line.contains("剩余 80.0 格"));assertTrue(line.contains("预计 8秒"));
        s.addProperty("last_request","eta-new-test");
        assertTrue(WorkHudModel.navigation(s).contains("计算中"));
    }
    @Test void navigationDurationRemainsReadableAndDoesNotClaimArrival(){
        assertEquals("1秒",WorkHudModel.durationLabel(0));
        assertEquals("1分32秒",WorkHudModel.durationLabel(92));
        assertEquals("1小时1分",WorkHudModel.durationLabel(3662));
    }
    @Test void navigationIgnoresOldMalformedAndManualState() {
        for(String change:new String[]{"manual","disconnected","ended","missing","invalid"}) {
            var s=state();s.addProperty("navigating",true);
            s.add("material_air_navigation",json("{phase:'cruising',horizontal_error:8,vertical_error:0.1}"));
            switch(change) {
                case "manual"->s.addProperty("manual_movement",true);
                case "disconnected"->s.addProperty("connected",false);
                case "ended"->s.getAsJsonObject("material_air_navigation").addProperty("phase","done");
                case "missing"->s.getAsJsonObject("material_air_navigation").remove("vertical_error");
                case "invalid"->s.getAsJsonObject("material_air_navigation").addProperty("horizontal_error",-1);
            }
            assertEquals("",WorkHudModel.navigation(s),change);
        }
    }
    @Test void overallQuotaWinsOverSubBatch(){assertEquals("混凝土制作 · 101/800 · 凝固并回收",WorkHudModel.select(state(),job(),10001).line());}
    @Test void expiredWrongOwnerAndWorldFallBackToNative(){
        assertEquals("2/8",WorkHudModel.select(state(),job(),15001).progress());
        for(String field:new String[]{"world_session","task_session"}) {var j=job();j.addProperty(field,"other");assertEquals("2/8",WorkHudModel.select(state(),j,10001).progress());}
        var j=job();j.addProperty("control_revision",2);assertEquals("2/8",WorkHudModel.select(state(),j,10001).progress());
        assertEquals("2/8",WorkHudModel.select(state(),job(),9999).progress());
    }
    @Test void defensePreservesProgress(){var s=state();s.addProperty("guard_busy",true);var result=WorkHudModel.select(s,job(),10001);assertEquals("101/800",result.progress());assertEquals("防护中",result.phase());assertTrue(result.attention());}
    @Test void inventoryPauseRetainsTaskProgressAndDoesNotAnnounceCruising(){
        var s=state();s.addProperty("inventory_interface_paused",true);s.addProperty("navigating",true);
        s.add("material_air_navigation",json("{phase:'cruising',horizontal_error:8,vertical_error:0.1}"));
        assertEquals("101/800",WorkHudModel.select(s,job(),10001).progress());
        assertEquals("查看背包，施工暂停",WorkHudModel.select(s,job(),10001).phase());
        assertEquals("",WorkHudModel.navigation(s));
        s.addProperty("inventory_interface_paused",false);
        assertEquals("凝固并回收",WorkHudModel.select(s,job(),10001).phase());
    }
    @Test void enabledAutoEatDoesNotHideTheCurrentWorkPhase(){
        var s=state();s.add("guard_food",json("{active:true,eating:false}"));
        var result=WorkHudModel.select(s,job(),10001);
        assertEquals("凝固并回收",result.phase());assertFalse(result.attention());
        s.add("guard_food",json("{active:true}"));
        assertEquals("凝固并回收",WorkHudModel.select(s,job(),10001).phase());
    }
    @Test void actualEatingRetainsOverallQuotaAndEndsWhenEatingEnds(){
        var s=state();s.add("guard_food",json("{active:true,eating:true}"));
        var result=WorkHudModel.select(s,job(),10001);
        assertEquals("进食中",result.phase());assertEquals("101/800",result.progress());
        assertTrue(result.attention());s.getAsJsonObject("guard_food").addProperty("eating",false);
        assertEquals("凝固并回收",WorkHudModel.select(s,job(),10001).phase());
    }
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
