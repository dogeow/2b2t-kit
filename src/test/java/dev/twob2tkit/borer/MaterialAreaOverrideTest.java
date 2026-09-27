package dev.twob2tkit.borer;

import dev.twob2tkit.KitConfig;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.game.GameProvider;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import static org.junit.jupiter.api.Assertions.*;

class MaterialAreaOverrideTest {
    @TempDir static Path gameDir;
    @BeforeAll static void loader(){
        var provider=(GameProvider)Proxy.newProxyInstance(GameProvider.class.getClassLoader(),
            new Class<?>[]{GameProvider.class},(proxy,method,args)->{
                if(method.getName().equals("getLaunchDirectory"))return gameDir;
                throw new AssertionError(method.getName());
            });
        FabricLoaderImpl.INSTANCE.setGameProvider(provider);
        net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();
    }
    @Test void scopedAreaDoesNotOverwriteSavedMarksOrMode()throws Exception{
        KitConfig config=new KitConfig();config.borerAreaAx=900;config.borerAreaAy=20;
        config.borerLastMode="ORE";config.borerHomeOnDone=true;config.borerAreaStoreDrops=true;
        Class<?> type=Class.forName("dev.twob2tkit.borer.TunnelBorer$HostBridge");
        var ctor=type.getDeclaredConstructor(KitConfig.class);ctor.setAccessible(true);
        var host=ctor.newInstance(config);
        Class<?> areaType=Class.forName("dev.twob2tkit.borer.TunnelBorer$MaterialArea");
        var areaCtor=areaType.getDeclaredConstructor(BlockPos.class,BlockPos.class);areaCtor.setAccessible(true);
        var field=type.getDeclaredField("materialArea");field.setAccessible(true);
        field.set(host,areaCtor.newInstance(new BlockPos(10,65,20),new BlockPos(17,70,27)));
        var api=(dev.twob2tkit.runtime.api.BorerHost)host;
        assertEquals(10,api.borerAreaAx());assertEquals(65,api.borerAreaAy());
        assertFalse(api.borerHomeOnDone());assertFalse(api.borerAreaStoreDrops());
        api.setBorerLastMode("AREA");assertEquals("ORE",config.borerLastMode);
        assertEquals(900,config.borerAreaAx);assertEquals(20,config.borerAreaAy);
        field.set(host,null);
        assertEquals(900,api.borerAreaAx());assertTrue(api.borerHomeOnDone());
    }
    @Test void materialAreaOwnershipRequiresLiveAreaAndExactBoundaries()throws Exception{
        Class<?> type=Class.forName("dev.twob2tkit.borer.TunnelBorer$MaterialArea");
        var ctor=type.getDeclaredConstructor(BlockPos.class,BlockPos.class);ctor.setAccessible(true);
        var owns=type.getDeclaredMethod("owns",boolean.class,String.class,BlockPos.class,BlockPos.class);owns.setAccessible(true);
        BlockPos min=new BlockPos(760976,49,797914),max=new BlockPos(760977,66,797915);
        var area=ctor.newInstance(min,max);
        assertEquals(true,owns.invoke(area,true,"AREA",min,max));
        assertEquals(false,owns.invoke(area,false,"AREA",min,max));
        assertEquals(false,owns.invoke(area,true,"ORE",min,max));
        assertEquals(false,owns.invoke(area,true,"AREA",min.above(),max));
        assertEquals(false,owns.invoke(area,true,"AREA",min,max.below()));
        assertEquals(false,owns.invoke(area,true,"AREA",min.east(),max.east()));
        assertEquals(false,owns.invoke(area,true,"AREA",null,max));
    }

}
