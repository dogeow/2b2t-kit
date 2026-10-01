package dev.twob2tkit.structure;

import org.junit.jupiter.api.Test;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;

final class SeedScoutScanBudgetTest {
    @Test void explicitEnableAndLiveDemandAreBothRequired() throws Exception {
        String config=Files.readString(Path.of("src/client/java/dev/twob2tkit/KitConfig.java"));
        assertTrue(config.contains("public boolean seedScoutEnabled;"));
        assertFalse(SeedScoutScanBudget.shouldScan(false,true,false));
        assertFalse(SeedScoutScanBudget.shouldScan(true,false,false));
        assertFalse(SeedScoutScanBudget.shouldScan(true,true,true));
        assertTrue(SeedScoutScanBudget.shouldScan(true,true,false));
    }
    @Test void nestedClassifierResumesAcrossTicksWithoutExceedingActualReadBudget() {
        var budget=new SeedScoutScanBudget<Integer>();var reads=new AtomicInteger();boolean complete=false;
        for(int tick=1;tick<=4;tick++) {
            budget.beginTick(tick);
            try {
                for(int n=0;n<500;n++) { int value=n;budget.block(n,()->{reads.incrementAndGet();return value;}); }
                complete=true;
            } catch(SeedScoutScanBudget.Exhausted ignored) { assertFalse(complete); }
            assertTrue(budget.reads()<=128);
        }
        assertTrue(complete);assertEquals(500,reads.get());
    }
    @Test void baseBlocksHeightAndOtherWorldReadsShareOneBudget() {
        var budget=new SeedScoutScanBudget<Integer>();var actual=new AtomicInteger();budget.beginTick(1);
        for(int n=0;n<126;n++) budget.block(n,actual::incrementAndGet);
        budget.surface(7,actual::incrementAndGet);budget.uncached(actual::incrementAndGet);
        assertThrows(SeedScoutScanBudget.Exhausted.class,()->budget.block(999,actual::incrementAndGet));
        assertThrows(SeedScoutScanBudget.Exhausted.class,()->budget.uncached(actual::incrementAndGet));
        assertEquals(128,actual.get());assertEquals(128,budget.reads());
        // Cached observations remain usable when this tick's native-read budget is exhausted.
        budget.block(0,()->{fail("cached block reread");return 0;});
    }
    @Test void cacheExpiresIsBoundedAndClearsAtWorldChange() {
        var budget=new SeedScoutScanBudget<Integer>();var actual=new AtomicInteger();budget.beginTick(1);
        assertEquals(1,budget.block(1,actual::incrementAndGet));budget.beginTick(200);
        assertEquals(1,budget.block(1,actual::incrementAndGet));budget.beginTick(201);
        assertEquals(2,budget.block(1,actual::incrementAndGet));budget.clear();budget.beginTick(202);
        assertEquals(3,budget.block(1,actual::incrementAndGet));
        for(int n=0;n<5000;n++) { if(n%128==0) budget.beginTick(203+n/128);budget.block(n,()->0); }
        assertEquals(SeedScoutScanBudget.BLOCK_CACHE_SIZE,budget.cachedBlocks());
        budget.clear();assertEquals(0,budget.cachedBlocks());
    }
    @Test void cachedWorkStillHasAnInspectionBudgetAndUiActuallyProvidesOptIn() throws Exception {
        var budget=new SeedScoutScanBudget<Integer>();budget.beginTick(1);
        for(int n=0;n<64;n++) assertTrue(budget.inspect());assertFalse(budget.inspect());
        String source=Files.readString(Path.of("src/client/java/dev/twob2tkit/structure/SeedScout.java"));
        assertEquals(1,source.split("level\\.getBlockState\\(",-1).length-1);
        assertTrue(source.contains("client.screen==scanScreen"));
        assertTrue(source.indexOf("shouldScan(")<source.indexOf("scanNearby(client)"));
        String screen=Files.readString(Path.of("src/client/java/dev/twob2tkit/structure/NearbyStructuresScreen.java"));
        assertTrue(screen.contains("config.seedScoutEnabled=value"));assertTrue(screen.contains("scout.requestScanningFor(page)"));
    }
}
