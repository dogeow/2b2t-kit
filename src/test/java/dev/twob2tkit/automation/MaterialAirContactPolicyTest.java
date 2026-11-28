package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
import net.minecraft.world.phys.AABB;
import net.minecraft.world.phys.shapes.Shapes;
import net.minecraft.world.phys.shapes.BooleanOp;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.tree.*;
final class MaterialAirContactPolicyTest {
    @Test void observedFloatingPointFloorContactDoesNotEnterTheLowerFluidVoxel(){
        assertEquals(63,MaterialAirContactPolicy.minimumCell(62.999999999999986));
        assertEquals(63,MaterialAirContactPolicy.minimumCell(63));
        assertEquals(62,MaterialAirContactPolicy.minimumCell(62.99999));
        assertEquals(62,MaterialAirContactPolicy.maximumCell(63));
        assertEquals(62,MaterialAirContactPolicy.maximumCell(Math.nextUp(63.0)));
        assertEquals(63,MaterialAirContactPolicy.maximumCell(63.00001));
    }
    @Test void slabContactIsPermittedButRealPenetrationIsNot(){
        var slab=Shapes.box(0,.5,0,1,1,1);
        var contact=new AABB(.2,Math.nextDown(1.0),.2,.8,2.8,.8);
        assertFalse(Shapes.joinIsNotEmpty(Shapes.create(contact.deflate(MaterialAirContactPolicy.EPSILON)),slab,BooleanOp.AND));
        var penetration=new AABB(.2,.99999,.2,.8,2.8,.8);
        assertTrue(Shapes.joinIsNotEmpty(Shapes.create(penetration.deflate(MaterialAirContactPolicy.EPSILON)),slab,BooleanOp.AND));
    }
    @Test void invalidBodyCoordinatesNeverAuthorizeMovement(){
        for(double v:new double[]{Double.NaN,Double.POSITIVE_INFINITY,Double.NEGATIVE_INFINITY}){
            assertThrows(IllegalArgumentException.class,()->MaterialAirContactPolicy.minimumCell(v));
            assertThrows(IllegalArgumentException.class,()->MaterialAirContactPolicy.maximumCell(v));
        }
    }
    @Test void actualAirGateRetainsCollisionFluidAndHazardChecks()throws Exception{
        var node=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/AutomationBridge.class")){assertNotNull(in);new ClassReader(in).accept(node,0);}
        var m=node.methods.stream().filter(v->v.name.equals("airNavigationClear")).findFirst().orElseThrow();
        var calls=java.util.stream.StreamSupport.stream(m.instructions.spliterator(),false).filter(i->i instanceof MethodInsnNode).map(i->((MethodInsnNode)i).name).toList();
        for(String name:new String[]{"minimumCell","maximumCell","deflate","noCollision","getFluidState","getBlockState","cactusTransitionSafe"})assertTrue(calls.contains(name),name);
        assertFalse(calls.contains("setBlock"));
    }
    @Test void cactusContactRejectsApproachButPermitsDirectEscape(){
        var cactus=new net.minecraft.core.BlockPos(0,0,0);
        var approach=new AABB(-1,1,-.3,-.4,2.8,.3);
        assertFalse(MaterialAirContactPolicy.cactusTransitionSafe(approach,new net.minecraft.world.phys.Vec3(.3,0,0),cactus));
        var near=new AABB(-.5,1,-.3,.1,2.8,.3);
        assertTrue(MaterialAirContactPolicy.cactusTransitionSafe(near,new net.minecraft.world.phys.Vec3(-1,0,0),cactus));
        assertFalse(MaterialAirContactPolicy.cactusTransitionSafe(near,new net.minecraft.world.phys.Vec3(2,0,0),cactus));
        var above=new AABB(.2,1,.2,.8,2.8,.8);
        assertTrue(MaterialAirContactPolicy.cactusTransitionSafe(above,new net.minecraft.world.phys.Vec3(0,1,0),cactus));
        assertFalse(MaterialAirContactPolicy.cactusTransitionSafe(above,new net.minecraft.world.phys.Vec3(0,.1,0),cactus));
        assertFalse(MaterialAirContactPolicy.cactusTransitionSafe(above,new net.minecraft.world.phys.Vec3(Double.NaN,0,0),cactus));
        var clearHigh=new AABB(-2,2,.2,-1.4,3.8,.8);
        assertTrue(MaterialAirContactPolicy.cactusTransitionSafe(clearHigh,new net.minecraft.world.phys.Vec3(4,0,0),cactus));
        var clearSide=new AABB(-2,1,2,-1.4,2.8,2.6);
        assertTrue(MaterialAirContactPolicy.cactusTransitionSafe(clearSide,new net.minecraft.world.phys.Vec3(4,0,0),cactus));
    }
    @org.junit.jupiter.api.Test void dryFeetAboveActualWaterSurfaceCanRiseWithoutEnteringTheFluidVoxel(){
        org.junit.jupiter.api.Assertions.assertFalse(MaterialAirContactPolicy.fluidIntersects(62.94375,65.2,62,8d/9));
        org.junit.jupiter.api.Assertions.assertFalse(MaterialAirContactPolicy.fluidIntersects(62.8,65.2,62,7d/9));
        org.junit.jupiter.api.Assertions.assertTrue(MaterialAirContactPolicy.fluidIntersects(62.94375,65.2,62,1));
        org.junit.jupiter.api.Assertions.assertTrue(MaterialAirContactPolicy.fluidIntersects(62.88,65.2,62,8d/9));
        org.junit.jupiter.api.Assertions.assertFalse(MaterialAirContactPolicy.fluidIntersects(63,64.8,62,1));
    }
    @org.junit.jupiter.api.Test void invalidSurfaceAndBodyEvidenceNeverCertifiesDryAir(){
        for(double h:new double[]{Double.NaN,Double.POSITIVE_INFINITY,-1,0,1.01})org.junit.jupiter.api.Assertions.assertTrue(MaterialAirContactPolicy.fluidIntersects(64,65,62,h));
        org.junit.jupiter.api.Assertions.assertTrue(MaterialAirContactPolicy.fluidIntersects(Double.NaN,65,62,8d/9));
        org.junit.jupiter.api.Assertions.assertTrue(MaterialAirContactPolicy.fluidIntersects(65,64,62,8d/9));
    }
}
