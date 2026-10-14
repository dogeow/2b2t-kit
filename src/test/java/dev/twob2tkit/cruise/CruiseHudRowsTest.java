package dev.twob2tkit.cruise;

import dev.twob2tkit.hud.WorkHudModel;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class CruiseHudRowsTest {
    private final WorkHudModel.Summary task=new WorkHudModel.Summary("地图","13067/16512","铺设木板",false);
    @Test void movingAndArrivalKeepTheTaskInItsOwnFirstRow() {
        for(String cruise:new String[]{"巡航 · 剩余 8 格","已到达目标"}) {
            var rows=CruiseHudRows.select(task,cruise,true);
            assertEquals(2,rows.size());
            assertEquals("任务 · 地图 · 13067/16512 · 铺设木板",rows.getFirst().line());
            assertTrue(rows.get(1).line().startsWith("巡航"));
            assertFalse(rows.getFirst().notice());assertTrue(rows.get(1).notice());
        }
    }
    @Test void endingCruiseOnlyRemovesItsOwnRow() {
        var rows=CruiseHudRows.select(task,"",false);
        assertEquals(1,rows.size());assertTrue(rows.getFirst().line().contains("13067/16512"));
        assertEquals("巡航 · 前进",CruiseHudRows.select(null,"巡航 · 前进",false).getFirst().line());
        assertTrue(CruiseHudRows.select(null,null,false).isEmpty());
    }
    @Test void taskProtectionDoesNotColorTheCruiseAsAnAlert() {
        var rows=CruiseHudRows.select(new WorkHudModel.Summary("地图","10/20","防护中",true),"巡航 · 升高",false);
        assertTrue(rows.getFirst().attention());assertFalse(rows.get(1).attention());
    }
}
