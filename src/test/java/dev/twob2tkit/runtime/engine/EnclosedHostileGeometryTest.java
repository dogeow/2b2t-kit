package dev.twob2tkit.runtime.engine;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class EnclosedHostileGeometryTest {
    static final EnclosedHostileGeometry.Box MOB=new EnclosedHostileGeometry.Box(1.2,.5,1.2,1.8,2.2,1.8);
    static final EnclosedHostileGeometry.Box PLAYER=new EnclosedHostileGeometry.Box(3.2,-1,1.2,3.8,.8,1.8);
    static final class World implements EnclosedHostileGeometry.World {
        final Set<String> walls=new HashSet<>();boolean floor=true,clear=true;
        World(){for(int y=1;y<=2;y++){for(int n=1;n<=2;n++){add(0,y,n);add(3,y,n);add(n,y,0);add(n,y,3);}}}
        void add(int x,int y,int z){walls.add(x+","+y+","+z);}
        public boolean wall(int x,int y,int z){return walls.contains(x+","+y+","+z);}
        public boolean floor(int x,int z,double feet){return floor&&x>=1&&x<=2&&z>=1&&z<=2&&feet==.5;}
        public boolean clear(int x,int z,int w,int d,double feet,double top){return clear;}
    }
    @Test void actualTwoByTwoSlabPocketWithTwoWallCoursesCanYieldMovement(){assertTrue(EnclosedHostileGeometry.sealed(new World(),MOB,PLAYER));}
    @Test void everyMissingSideWallCellRefusesDeferral(){var full=new World();for(var missing:full.walls){var w=new World();w.walls.remove(missing);assertFalse(EnclosedHostileGeometry.sealed(w,MOB,PLAYER),missing);}}
    @Test void singleWallCourseIsNotAProof(){var w=new World();w.walls.removeIf(v->v.split(",")[1].equals("2"));assertFalse(EnclosedHostileGeometry.sealed(w,MOB,PLAYER));}
    @Test void missingOrWetFloorRefusesDeferral(){var w=new World();w.floor=false;assertFalse(EnclosedHostileGeometry.sealed(w,MOB,PLAYER));}
    @Test void InteriorStepOrFluidRefusesDeferral(){var w=new World();w.clear=false;assertFalse(EnclosedHostileGeometry.sealed(w,MOB,PLAYER));}
    @Test void playerInsidePocketRefusesDeferral(){assertFalse(EnclosedHostileGeometry.sealed(new World(),MOB,new EnclosedHostileGeometry.Box(2.1,.5,2.1,2.7,2.3,2.7)));}
    @Test void tinyMobCouldEscapeUnderFirstCourse(){assertFalse(EnclosedHostileGeometry.sealed(new World(),new EnclosedHostileGeometry.Box(1.2,.5,1.2,1.8,.9,1.8),PLAYER));}
    @Test void boundaryTouchIsAllowedButCrossingIsNot(){var touching=new EnclosedHostileGeometry.Box(2.4,.5,1.2,3,2.2,1.8);assertTrue(EnclosedHostileGeometry.sealed(new World(),touching,PLAYER));assertFalse(EnclosedHostileGeometry.sealed(new World(),new EnclosedHostileGeometry.Box(2.5,.5,1.2,3.1,2.2,1.8),PLAYER));}
    @Test void invalidBoxesCannotGrantDeferral(){assertFalse(EnclosedHostileGeometry.sealed(new World(),new EnclosedHostileGeometry.Box(Double.NaN,.5,1.2,1.8,2.2,1.8),PLAYER));}
    @Test void ordinaryJumpStepAndGravityAreRequired(){assertTrue(EnclosedHostileGeometry.ordinaryMovement(.42,.6,.08));assertFalse(EnclosedHostileGeometry.ordinaryMovement(.6,.6,.08));assertFalse(EnclosedHostileGeometry.ordinaryMovement(.42,1,.08));assertFalse(EnclosedHostileGeometry.ordinaryMovement(.42,.6,.03));}
    @Test void fallingMobNeedsEveryWallCourseToItsRealFloor(){
        var w=new World();for(int y=3;y<11;y++)for(int n=1;n<=2;n++){w.add(0,y,n);w.add(3,y,n);w.add(n,y,0);w.add(n,y,3);}
        var falling=new EnclosedHostileGeometry.Box(1.2,8.5,1.2,1.8,10.2,1.8);
        assertTrue(EnclosedHostileGeometry.sealed(w,falling,PLAYER));w.walls.remove("0,5,1");assertFalse(EnclosedHostileGeometry.sealed(w,falling,PLAYER));
    }
    @Test void unboundedFallCannotGrantDeferral(){var w=new World();assertFalse(EnclosedHostileGeometry.sealed(w,new EnclosedHostileGeometry.Box(1.2,30.5,1.2,1.8,32.2,1.8),PLAYER));}
    @Test void nonFiniteMovementCannotGrantDeferral(){for(double bad:new double[]{Double.NaN,Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY}){assertFalse(EnclosedHostileGeometry.ordinaryMovement(bad,.6,.08));assertFalse(EnclosedHostileGeometry.ordinaryMovement(.42,bad,.08));assertFalse(EnclosedHostileGeometry.ordinaryMovement(.42,.6,bad));}}
}
