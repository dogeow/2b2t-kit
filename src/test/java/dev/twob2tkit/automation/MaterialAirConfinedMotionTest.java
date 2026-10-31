package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import net.minecraft.world.phys.Vec3;
import java.util.List;
import org.objectweb.asm.*;
import org.objectweb.asm.tree.*;
import static org.junit.jupiter.api.Assertions.*;
class MaterialAirConfinedMotionTest {
 @Test void nearbyCollisionCapsHorizontalStepsWithoutChangingOpenAirOrVerticalMotion(){
  var error=new Vec3(12,-8,3);assertEquals(.06,MaterialAirArrivalPolicy.motion(error,false).speed());
  assertEquals(.025,MaterialAirArrivalPolicy.motion(error,true).speed());
  assertEquals(.08,MaterialAirArrivalPolicy.motion(new Vec3(0,-20,0),true).speed());
  assertEquals(MaterialAirArrivalPolicy.motion(new Vec3(.2,0,0)),MaterialAirArrivalPolicy.motion(new Vec3(.2,0,0),true));
 }
 @Test void confinedRoutesConvergeFromRecordedErrorsAndRetainBothStationaryChecks(){
  for(var initial:List.of(new Vec3(0,-.03125,1.8240788),new Vec3(-.6477574,-.03125,0),new Vec3(12,0,3))){
   var error=initial;var settle=new MaterialAirArrivalPolicy.Settlement(.2);
   for(int tick=0;tick<256&&!settle.done();tick++){
    var m=MaterialAirArrivalPolicy.motion(error,true);double h=Math.hypot(error.x,error.z);var step=Vec3.ZERO;
    if(m.horizontal()){assertTrue(m.speed()<=.025);step=new Vec3(error.x/h*m.speed()*10,0,error.z/h*m.speed()*10);}
    else if(m.vertical())step=new Vec3(0,Math.copySign(m.speed()*5,error.y),0);
    error=error.subtract(step);settle.observe(error,step,m.moving()?step:new Vec3(0,-.0784,0));
   }assertTrue(settle.done());assertEquals(8,settle.stableTicks());assertEquals(8,settle.restoredTicks());assertEquals(1,settle.restorations());
  }
 }
 @Test void liveNavigationUsesActualNearbyCollisionGeometry()throws Exception{
  var n=new ClassNode();try(var in=getClass().getResourceAsStream("/dev/twob2tkit/automation/MaterialAirNavigation.class")){assertNotNull(in);new ClassReader(in).accept(n,0);}
  var input=n.methods.stream().filter(m->m.name.equals("input")).findFirst().orElseThrow();boolean collision=false,inflated=false,policy=false;
  for(var i:input.instructions)if(i instanceof MethodInsnNode c){inflated|=c.name.equals("inflate");collision|=c.name.equals("noCollision");policy|=c.name.equals("motion")&&c.desc.contains(";Z)");}
  assertTrue(inflated&&collision&&policy);
 }
}
