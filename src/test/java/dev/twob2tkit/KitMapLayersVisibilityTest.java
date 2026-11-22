package dev.twob2tkit;

import org.junit.jupiter.api.Test;
import java.util.EnumSet;
import java.util.List;
import java.util.Set;
import static org.junit.jupiter.api.Assertions.*;

class KitMapLayersVisibilityTest {
    @Test void hiddenLayersRoundTripThroughConfigNames() {
        var visible = EnumSet.allOf(KitMapLayers.Layer.class);
        visible.remove(KitMapLayers.Layer.ROUTES);
        Set<String> hidden = KitMapLayers.hiddenNames(visible);
        assertEquals(Set.of("ROUTES"), hidden);
        assertEquals(visible, KitMapLayers.visibleLayers(hidden));
    }
    @Test void missingOrUnknownSavedNamesShowEveryLayer() {
        assertEquals(EnumSet.allOf(KitMapLayers.Layer.class), KitMapLayers.visibleLayers(null));
        assertEquals(EnumSet.allOf(KitMapLayers.Layer.class), KitMapLayers.visibleLayers(List.of("OLD_LAYER")));
    }
}
