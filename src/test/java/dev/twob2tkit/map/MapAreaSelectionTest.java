package dev.twob2tkit.map;

import dev.twob2tkit.borer.AreaDrafts;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class MapAreaSelectionTest {
    @Test void inclusiveDragPreservesBothDraftHeightsAndUsesBlockPrecision() {
        var draft = new AreaDrafts.Draft("world","project","mine","4 81 5","7 45 9","30","30","30");
        var a = new MapAreaSelection.Point(-80,127);
        var b = new MapAreaSelection.Point(-17,64);
        assertTrue(MapAreaSelection.fits(a,b));
        assertTrue(MapAreaSelection.fits(a,new MapAreaSelection.Point(47,64)));   // 128 blocks inclusive
        assertFalse(MapAreaSelection.fits(a,new MapAreaSelection.Point(48,64)));  // 129 blocks
        var result = MapAreaSelection.fill(draft,a,b,70,69);
        assertEquals("-80 81 127",result.a());
        assertEquals("-17 45 64",result.b());
        assertEquals("project",result.source());
        assertEquals(-4, MapAreaSelection.blockAt(399,800,-2,.5));
    }

    @Test void clickKeepsTheContextMenuAndUnsetHeightAvoidsDeepExcavation() {
        assertFalse(MapAreaSelection.dragged(100,100,101,101));
        assertTrue(MapAreaSelection.dragged(100,100,99,106));
        var draft = new AreaDrafts.Draft("world","","mine","0 69 0","","30","30","30");
        var result = MapAreaSelection.fill(draft,new MapAreaSelection.Point(0,0),new MapAreaSelection.Point(2,9),70,69);
        assertEquals("0 69 0",result.a());
        assertEquals("2 70 9",result.b());
    }
}
