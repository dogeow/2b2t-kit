package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.nio.file.Path;
import java.nio.file.Files;
import java.util.Map;
import static org.junit.jupiter.api.Assertions.*;

class BorerAreaProgressRegionsTest {
    @TempDir Path dir;
    private BorerAreaPlan.Snapshot snapshot(BlockPos min,BlockPos max){
        return new BorerAreaPlan(min,max,new BorerAreaPlan.Pose(min.getX()+.5,max.getY()+3,min.getZ()+.5,0,0,0)).snapshot();
    }
    @Test void switchingQuarriesRetainsThePreviousRegionAndWorld()throws Exception{
        Path file=dir.resolve("area-progress.json");
        BlockPos a=new BlockPos(1,64,2),b=new BlockPos(3,70,4),c=new BlockPos(20,65,30),d=new BlockPos(24,68,34);
        BorerAreaProgress.write(file,"world-a",snapshot(a,b));
        BorerAreaProgress.write(file,"world-a",snapshot(c,d));
        assertArrayEquals(snapshot(a,b).bounds(),BorerAreaProgress.read(file,"world-a",a,b).bounds());
        assertArrayEquals(snapshot(c,d).bounds(),BorerAreaProgress.read(file,"world-a",c,d).bounds());
        assertNull(BorerAreaProgress.read(file,"world-b",a,b));
    }
    @Test void firstNewWriteArchivesALegacySingleRegionCheckpoint()throws Exception{
        Path file=dir.resolve("area-progress.json");
        BlockPos a=new BlockPos(1,64,2),b=new BlockPos(3,70,4),c=new BlockPos(20,65,30),d=new BlockPos(24,68,34);
        Files.writeString(file,new Gson().toJson(Map.of("schema",1,"world","world-a","plan",snapshot(a,b))));
        BorerAreaProgress.write(file,"world-a",snapshot(c,d));
        assertNotNull(BorerAreaProgress.read(file,"world-a",a,b));
    }
}
