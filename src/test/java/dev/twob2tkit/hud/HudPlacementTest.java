package dev.twob2tkit.hud;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class HudPlacementTest {
    @Test void withoutTooltipUsesTop(){assertEquals(8,HudPlacement.below(100,200,20,400));}
    @Test void keepsSixPixelGapBelowActualAndExpandingTooltip(){assertEquals(89,HudPlacement.below(100,200,20,400,new HudPlacement.Rect(140,4,100,32),new HudPlacement.Rect(120,4,180,79)));}
    @Test void horizontallySeparateTooltipDoesNotPushPanel(){assertEquals(8,HudPlacement.below(100,200,20,400,new HudPlacement.Rect(320,4,70,60)));}
    @Test void tooTallHidesInsteadOfClampingOverTooltipOrCrosshair(){assertEquals(-1,HudPlacement.below(100,200,20,200,new HudPlacement.Rect(120,4,100,100)));}
    @Test void invalidOrEmptyBoundsIgnored(){assertEquals(8,HudPlacement.below(100,200,20,400,new HudPlacement.Rect(100,4,0,400),new HudPlacement.Rect(100,Double.NaN,100,40)));}
}
