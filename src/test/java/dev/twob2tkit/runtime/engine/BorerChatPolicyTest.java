package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class BorerChatPolicyTest {
    @Test void startAndManualPauseStayShortButTheFlightHandoffIsNotLost(){
        assertEquals("已开始区域挖，按 B 暂停",BorerChatPolicy.started("区域挖"));
        assertEquals("挖矿已暂停；已保留飞行",BorerChatPolicy.stopped("按键停止","已保留飞行"));
        assertNull(BorerChatPolicy.stopped("离开世界",""));
    }
    @Test void realFailuresAndCompletionResultsAreNeverSilenced(){
        for(String reason:new String[]{"所有镐均已达到防破门槛","方块更新连续 5 秒未获确认","区域已复核挖完：20 列"})
            assertTrue(BorerChatPolicy.stopped(reason,"").contains(reason));
        assertNotNull(BorerChatPolicy.stopped(null,""));
    }
}
