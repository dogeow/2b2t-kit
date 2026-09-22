package dev.twob2tkit.runtime.engine;
import dev.twob2tkit.runtime.api.BuildNavigation;
import net.minecraft.core.BlockPos;
import net.minecraft.world.phys.Vec3;
import org.junit.jupiter.api.Test;
import java.net.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class BuildNavigationReloadTest {
    private URLClassLoader isolated(){
        var url=DefaultBuildNavigation.class.getProtectionDomain().getCodeSource().getLocation();
        return new URLClassLoader(new URL[]{url},getClass().getClassLoader()){
            @Override protected Class<?> loadClass(String name,boolean resolve)throws ClassNotFoundException {
                synchronized(getClassLoadingLock(name)){
                    if(!name.startsWith("dev.twob2tkit.runtime.engine."))return super.loadClass(name,resolve);
                    var c=findLoadedClass(name);if(c==null)c=findClass(name);if(resolve)resolveClass(c);return c;
                }
            }
        };
    }
    @Test void independentReloadsShareOnlyTheStableApiAndPreserveVerifiedMotion()throws Exception {
        try(var first=isolated();var second=isolated()){
            String name=DefaultBuildNavigation.class.getName();
            var a=(BuildNavigation)first.loadClass(name).getConstructor().newInstance();
            var b=(BuildNavigation)second.loadClass(name).getConstructor().newInstance();
            assertNotSame(a.getClass(),b.getClass());assertEquals(first,a.getClass().getClassLoader());
            assertEquals(a.motion(new Vec3(.084,-.029,-.051)),b.motion(new Vec3(.084,-.029,-.051)));
            assertFalse(b.motion(new Vec3(.084,-.029,-.051)).arrived());
            var world=new BuildNavigation.World(){public boolean clear(BlockPos p){return true;}public boolean edge(BlockPos a,BlockPos b){return true;}};
            var oldSearch=a.search(world,BlockPos.ZERO,List.of(new BlockPos(20,0,0)));assertNull(oldSearch.advance(1,Long.MAX_VALUE));
            var newSearch=b.search(world,BlockPos.ZERO,List.of(new BlockPos(3,0,0)));
            assertEquals(4,newSearch.advance(16,Long.MAX_VALUE).nodes().size());assertEquals(1,oldSearch.expanded());
        }
    }
    @Test void badPolicyOrMovementFailsBeforeAnyInputIsApplied(){
        assertThrows(IllegalArgumentException.class,()->new BuildNavigation.Policy(10000,1,50000,6,100,50));
        assertThrows(IllegalArgumentException.class,()->new BuildNavigation.Motion(false,false,1,new Vec3(10,0,0)));
        assertThrows(IllegalArgumentException.class,()->new BuildNavigation.Motion(true,false,.01,Vec3.ZERO));
    }
    @Test void roundedWorldHeightAtToleranceDoesNotDemandAnUnsendableMicroStep(){
        var nav=new DefaultBuildNavigation();
        var delta=new Vec3(761011.5-761011.5000005532,61.02-61.025000000000006,797836.5-797836.4969446951);
        assertTrue(nav.motion(delta).arrived());assertEquals(0,nav.motion(delta).speed());
        assertFalse(nav.motion(new Vec3(0,.0051,0)).arrived());
    }
}
