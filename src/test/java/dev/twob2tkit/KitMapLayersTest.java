package dev.twob2tkit;

import static org.junit.jupiter.api.Assertions.*;
import dev.twob2tkit.map.MapViewport;
import dev.twob2tkit.runtime.api.MapTaskView.Area;
import org.junit.jupiter.api.Test;

class KitMapLayersTest {
    @Test void mapViewportPreservesNegativeCoordinatesAndGuiScale() {
        var view = new MapViewport(800, 450, 400, 225, -200, 50, 2);
        assertEquals(new Area(-400, -63, 0, 162), view.bounds());
        assertEquals(400, view.x(-200));
        assertEquals(227, view.z(51));
    }

    @Test void materialKeywordsMatchChineseNamesAndEnchantIds() {
        assertTrue(KitMapLayers.matchesQuery("工具柜 剪刀 minecraft:shears · 经验修补 mending", "剪刀 MENDING"));
        assertFalse(KitMapLayers.matchesQuery("附魔书 未记录附魔", "经验修补"));
    }

    @Test void projectionArrowUsesMinecraftClockwiseRotation() {
        assertEquals(Math.PI / 2, KitMapLayers.projectionBearing("CLOCKWISE_90"));
        assertEquals(-Math.PI / 2, KitMapLayers.projectionBearing("COUNTERCLOCKWISE_90"));
    }
}
