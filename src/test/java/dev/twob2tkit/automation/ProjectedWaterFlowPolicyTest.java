package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.HashMap;
import java.util.HashSet;
import static org.junit.jupiter.api.Assertions.*;
import static dev.twob2tkit.automation.ProjectedWaterFlowPolicy.*;

class ProjectedWaterFlowPolicyTest {
    final Cell source=new Cell(0,181,0);
    final Bounds bounds=new Bounds(new Cell(-8,55,-8),new Cell(8,182,8));
    static final class Scene implements World {
        final HashMap<Cell,Kind> cells=new HashMap<>();final HashSet<Cell> occupants=new HashSet<>();
        public Kind kind(Cell p){return cells.getOrDefault(p,p.y()<=60?Kind.BARRIER:p.y()==61?Kind.SOURCE:Kind.AIR);}
        public boolean living(Cell p){return occupants.contains(p);}
    }
    Scene scene(){
        var w=new Scene();
        for(var p:new Cell[]{source.offset(1,0,0),source.offset(-1,0,0),source.offset(0,0,1),source.offset(0,0,-1)})w.cells.put(p,Kind.BARRIER);
        w.cells.put(new Cell(0,61,0),Kind.FLOWING);return w;
    }
    @Test void longUnwalledFallIntoExistingWaterDoesNotInventSideFlowInMidAir(){
        assertNull(rejection(scene(),bounds,source));
    }
    @Test void landingCanFillAnEnclosedAirPocketWithoutReplacingItsReceivingSources(){
        var w=scene();w.cells.put(new Cell(1,61,0),Kind.AIR);w.cells.put(new Cell(2,61,0),Kind.BARRIER);
        assertNull(rejection(w,bounds,source));
        w.cells.put(new Cell(1,61,0),Kind.UNSAFE);assertNotNull(rejection(w,bounds,source));
    }
    @Test void everyLandingProtectsDecorationsContainersAndOtherFluids(){
        for(int y:new int[]{180,77,62,61,60}){
            var w=scene();w.cells.put(new Cell(0,y,0),Kind.UNSAFE);
            assertNotNull(rejection(w,bounds,source),"Unsafe cell at "+y);
        }
    }
    @Test void loadedEvidenceAndLivingEntitiesAreCheckedDownTheWholeColumn(){
        var w=scene();w.cells.put(new Cell(0,100,0),Kind.UNLOADED);assertNotNull(rejection(w,bounds,source));
        w=scene();w.occupants.add(new Cell(0,77,0));assertNotNull(rejection(w,bounds,source));
    }
    @Test void waterCannotEscapeTheDeclaredBottom(){
        var w=scene();for(int y=55;y<=61;y++)w.cells.put(new Cell(0,y,0),Kind.AIR);
        assertNotNull(rejection(w,bounds,source));
    }
    @Test void lateralFlowHasSevenStepsButDownstreamLandingsResetThatReach(){
        var w=scene();
        for(int x=1;x<=7;x++)w.cells.put(new Cell(x,61,0),Kind.AIR);
        w.cells.put(new Cell(8,61,0),Kind.UNSAFE);
        assertNull(rejection(w,bounds,source),"An eighth horizontal step is not reached");
        w.cells.put(new Cell(7,60,0),Kind.AIR);w.cells.put(new Cell(7,59,0),Kind.AIR);
        w.cells.put(new Cell(8,59,0),Kind.AIR);w.cells.put(new Cell(9,59,0),Kind.AIR);
        assertNotNull(rejection(w,bounds,source),"A new lower landing must not inherit an exhausted horizontal budget");
    }
    @Test void boundedInputRejectsOverflowAndExcessiveScanWork(){
        assertFalse(new Bounds(new Cell(Integer.MIN_VALUE,0,0),new Cell(Integer.MAX_VALUE,10,10)).valid());
        assertFalse(new Bounds(new Cell(0,0,0),new Cell(32,191,32)).valid());
        assertNotNull(rejection(scene(),null,source));
    }
    @Test void waterSourcesAlreadyPresentAreTerminalRatherThanDestructivelyReplaced(){
        var w=scene();w.cells.put(new Cell(0,80,0),Kind.SOURCE);
        w.cells.put(new Cell(0,79,0),Kind.UNSAFE);
        // A receiving source stops downward replacement; its horizontal surface
        // still needs a safe enclosure, hence use a source plane at that level.
        for(int x=-8;x<=8;x++)for(int z=-8;z<=8;z++)w.cells.put(new Cell(x,80,z),Kind.SOURCE);
        assertNull(rejection(w,bounds,source));
    }
}
