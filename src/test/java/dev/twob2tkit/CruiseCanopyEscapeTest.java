package dev.twob2tkit;

import dev.twob2tkit.cruise.CruiseCanopyEscape;
import dev.twob2tkit.cruise.CruiseCanopyEscape.Offset;
import net.minecraft.world.phys.AABB;
import org.junit.jupiter.api.Test;
import java.util.List;
import static org.junit.jupiter.api.Assertions.*;

class CruiseCanopyEscapeTest {
    @Test void borrowedFlightSpeedCannotOvershootAShortExitEvenWhileSprinting(){
        for(double gap:new double[]{.26,.5,1,3,6}){
            double speed=CruiseCanopyEscape.speed(gap);
            assertTrue(speed<=.02);assertTrue(speed*15<gap);
        }
        assertThrows(IllegalArgumentException.class,()->CruiseCanopyEscape.speed(Double.NaN));
    }
    @Test void movesUnderLeavesBeforeFindingARealClearAscentColumn(){
        var body=new AABB(.2,65,.2,.8,66.8,.8);
        var crown=new AABB(-2,66.8,-2,3,70,3);
        var path=CruiseCanopyEscape.find(6,(a,b)->!dev.twob2tkit.cruise.CruiseCollisionPath.horizontal(
            body.move(a.x(),0,a.z()),b.x()-a.x(),b.z()-a.z()).intersects(crown),
            a->!dev.twob2tkit.cruise.CruiseCollisionPath.vertical(body.move(a.x(),0,a.z()),30).intersects(crown));
        assertEquals(3,path.size());
        assertTrue(Math.abs(path.getLast().x())>=3||Math.abs(path.getLast().z())>=3);
        for(int i=0;i<path.size();i++){
            var prev=i==0?new Offset(0,0):path.get(i-1);var next=path.get(i);
            assertEquals(1,Math.abs(prev.x()-next.x())+Math.abs(prev.z()-next.z()));
        }
    }
    @Test void leavesGlassPlatformBeforeTryingToDescendToTheSavedCruiseHeight(){
        var body=new AABB(.2,70,.2,.8,71.8,.8);
        var platform=new AABB(-1,68,-1,2,70,2);
        assertTrue(CruiseCanopyEscape.needsEscape(70,64.2,false,true));
        double probe=CruiseCanopyEscape.columnProbeY(70,64.2);
        assertEquals(68,probe);
        var path=CruiseCanopyEscape.find(6,(a,b)->!dev.twob2tkit.cruise.CruiseCollisionPath.horizontal(
            body.move(a.x(),0,a.z()),b.x()-a.x(),b.z()-a.z()).intersects(platform),
            a->!dev.twob2tkit.cruise.CruiseCollisionPath.vertical(body.move(a.x(),0,a.z()),probe-70).intersects(platform));
        assertFalse(path.isEmpty());
        var end=path.getLast();
        assertFalse(dev.twob2tkit.cruise.CruiseCollisionPath.vertical(body.move(end.x(),0,end.z()),probe-70).intersects(platform));
        assertFalse(CruiseCanopyEscape.needsEscape(70,64.2,false,false));
    }
    @Test void descentDoesNotChangeLeafAscentOrInventAnEscapeForOrdinaryAltitudeAdjustments(){
        assertTrue(CruiseCanopyEscape.needsEscape(70,90,true,false));
        assertFalse(CruiseCanopyEscape.needsEscape(70,90,false,true));
        assertFalse(CruiseCanopyEscape.needsEscape(70,70.2,true,true));
        assertFalse(CruiseCanopyEscape.needsEscape(Double.NaN,64,false,true));
        assertEquals(90,CruiseCanopyEscape.columnProbeY(70,90));
        assertEquals(69,CruiseCanopyEscape.columnProbeY(70,69));
    }
    @Test void controllerUsesDescentPolicyWithoutChangingOwnedAirOnlyWaypoints()throws Exception{
        var node=new org.objectweb.asm.tree.ClassNode();
        try(var in=getClass().getResourceAsStream("/dev/twob2tkit/KitController.class")){
            assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);
        }
        var method=node.methods.stream().filter(m->m.name.equals("tickCanopyEscape")).findFirst().orElseThrow();
        var calls=new java.util.ArrayList<String>();
        for(var instruction:method.instructions)if(instruction instanceof org.objectweb.asm.tree.MethodInsnNode call)calls.add(call.name);
        assertTrue(calls.containsAll(List.of("managedAirOnlyNavigation","needsEscape","columnProbeY")));
        assertTrue(calls.indexOf("managedAirOnlyNavigation")<calls.indexOf("needsEscape"));
    }
    @Test void aWallUnknownCellsOrAnUnreachableColumnCannotBecomeAnExit(){
        assertTrue(CruiseCanopyEscape.find(6,(a,b)->false,a->a.x()!=0).isEmpty());
        assertTrue(CruiseCanopyEscape.find(6,(a,b)->true,a->Math.abs(a.x())>6).isEmpty());
        assertTrue(CruiseCanopyEscape.find(6,(a,b)->true,a->false).isEmpty());
    }
    @Test void canTakeAShortConnectedSideRouteAroundATrunk(){
        var path=CruiseCanopyEscape.find(3,(a,b)->!b.equals(new Offset(1,0))&&b.z()>=0,
            a->a.equals(new Offset(2,0)));
        assertEquals(List.of(new Offset(0,1),new Offset(1,1),new Offset(2,1),new Offset(2,0)),path);
    }
}
