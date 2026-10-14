package dev.twob2tkit.builder;

import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class LitematicaLayerBoundaryTest {
    public static class AllLayers {
        public String getLayerMode(){return "ALL";}
        public String getAxis(){return "y";}
        public int getMinLayerBoundary(){return -30_000_000;}
        public int getMaxLayerBoundary(){return 30_000_000;}
    }
    public static class OneLayer extends AllLayers {
        @Override public String getLayerMode(){return "SINGLE";}
        @Override public int getMinLayerBoundary(){return 64;}
        @Override public int getMaxLayerBoundary(){return 64;}
    }
    @Test void actualBoundaryAccessorsPreserveTheOriginalWholeMapKey()throws Exception {
        assertEquals("/ALL/y/-30000000/30000000",LitematicaAccess.layerKey(new AllLayers()));
    }
    @Test void selectedLayerNeverBecomesAWholeMapClaim()throws Exception {
        assertEquals("/SINGLE/y/64/64",LitematicaAccess.layerKey(new OneLayer()));
    }
    @Test void missingBoundaryInterfaceNeverInventsDefaults() {
        assertThrows(ReflectiveOperationException.class,()->LitematicaAccess.layerKey(new Object()));
    }
}
