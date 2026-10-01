package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;

import java.nio.file.Path;
import java.util.ArrayList;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.Executors;

import static org.junit.jupiter.api.Assertions.*;

class HorseNudgePolicyTest {
    private static final HorseNudgePolicy.Point CELL=new HorseNudgePolicy.Point(.5,63.5,.5);
    private static final HorseNudgePolicy.Point HORSE=new HorseNudgePolicy.Point(2,64,.5);
    private static final HorseNudgePolicy.Point PLAYER=new HorseNudgePolicy.Point(.2,64,.5);
    private static final HorseNudgePolicy.Point ESCAPE=new HorseNudgePolicy.Point(7.1,64,.5);

    @Test void scopeRequiresFreshExactWorldRevisionAndExpiry(){
        assertTrue(HorseNudgePolicy.scopeValid("world","world",7,7,11_000,9_000,10_000));
        assertFalse(HorseNudgePolicy.scopeValid("old","world",7,7,11_000,9_000,10_000));
        assertFalse(HorseNudgePolicy.scopeValid("world","world",6,7,11_000,9_000,10_000));
        assertFalse(HorseNudgePolicy.scopeValid("world","world",7,7,9_999,9_000,10_000));
        assertFalse(HorseNudgePolicy.scopeValid("world","world",7,7,26_000,9_000,10_000));
        assertFalse(HorseNudgePolicy.scopeValid("world","world",7,7,11_000,6_999,10_000));
    }

    @Test void exactObservationPinsPositionAndHealth(){
        assertTrue(HorseNudgePolicy.exactObservation(HORSE,
            new HorseNudgePolicy.Point(2.2,64,.5),18,18));
        assertFalse(HorseNudgePolicy.exactObservation(HORSE,
            new HorseNudgePolicy.Point(2.36,64,.5),18,18));
        assertFalse(HorseNudgePolicy.exactObservation(HORSE,HORSE,18,17.5F));
    }

    @Test void oneHitRequiresEmptyHandGroundedCooldownAndLargeHealthMargin(){
        assertTrue(HorseNudgePolicy.safeEmptyHandHit(15,1,true,true,0,false,1));
        assertFalse(HorseNudgePolicy.safeEmptyHandHit(7.9F,1,true,true,0,false,1));
        assertFalse(HorseNudgePolicy.safeEmptyHandHit(15,1.01,true,true,0,false,1));
        assertFalse(HorseNudgePolicy.safeEmptyHandHit(15,1,false,true,0,false,1));
        assertFalse(HorseNudgePolicy.safeEmptyHandHit(15,1,true,false,0,false,1));
        assertFalse(HorseNudgePolicy.safeEmptyHandHit(15,1,true,true,.1,false,1));
        assertFalse(HorseNudgePolicy.safeEmptyHandHit(15,1,true,true,0,true,1));
        assertFalse(HorseNudgePolicy.safeEmptyHandHit(15,1,true,true,0,false,.94F));
    }

    @Test void escapeMustMoveMonotonicallyAwayWithPlayerBehindHorse(){
        assertNull(HorseNudgePolicy.geometryRejection(CELL,HORSE,PLAYER,ESCAPE,3));
        assertNotNull(HorseNudgePolicy.geometryRejection(CELL,HORSE,PLAYER,
            new HorseNudgePolicy.Point(5,64,.5),3));
        assertNotNull(HorseNudgePolicy.geometryRejection(CELL,HORSE,
            new HorseNudgePolicy.Point(3,64,.5),ESCAPE,3));
        assertNotNull(HorseNudgePolicy.geometryRejection(CELL,
            new HorseNudgePolicy.Point(5,64,.5),PLAYER,ESCAPE,3));
    }

    @Test void terminalStateNeverRequestsAnotherHit(){
        assertEquals(HorseNudgePolicy.Outcome.DONE,
            HorseNudgePolicy.outcome(true,true,14,6,false));
        assertEquals(HorseNudgePolicy.Outcome.RUNNING,
            HorseNudgePolicy.outcome(true,true,14,5.9,false));
        assertEquals(HorseNudgePolicy.Outcome.WAITING,
            HorseNudgePolicy.outcome(true,true,14,5.9,true));
        assertEquals(HorseNudgePolicy.Outcome.WAITING,
            HorseNudgePolicy.outcome(false,false,0,Double.NaN,true));
        assertEquals(HorseNudgePolicy.Outcome.WAITING,
            HorseNudgePolicy.outcome(true,false,0,3,false));
    }

    @Test void durableSpentKeyCannotBeClaimedTwice(@TempDir Path root)throws Exception{
        JsonObject first=new JsonObject();first.addProperty("stage","claimed_before_attack");
        Path path=HorseNudgeStore.claim(root,"horse-nudge-fixed-key",first);
        assertTrue(java.nio.file.Files.isRegularFile(path));
        assertThrows(java.nio.file.FileAlreadyExistsException.class,
            ()->HorseNudgeStore.claim(root,"horse-nudge-fixed-key",first));
        JsonObject finalReceipt=new JsonObject();finalReceipt.addProperty("stage","terminal_done");
        HorseNudgeStore.update(path,finalReceipt);
        assertTrue(java.nio.file.Files.readString(path).contains("terminal_done"));
    }

    @Test void canonicalSpentKeyPinsServerProjectionHorseAndCell(){
        String key=HorseNudgeStore.canonicalKey("simpcraft.com","minecraft:overworld","yard",
            "12345678-1234-5678-9234-567812345678",10,63,10);
        assertEquals("horse-nudge-a6fe36a4c029ccd9d9f4d6b4ac5c69d3",key);
        assertNotEquals(key,HorseNudgeStore.canonicalKey("simpcraft.com","minecraft:overworld","yard",
            "12345678-1234-5678-9234-567812345678",11,63,10));
    }

    @Test void concurrentClaimersHaveExactlyOneWinner(@TempDir Path root)throws Exception{
        var executor=Executors.newFixedThreadPool(8);var gate=new CountDownLatch(1);
        var futures=new ArrayList<java.util.concurrent.Future<Boolean>>();
        try{
            for(int i=0;i<16;i++)futures.add(executor.submit(()->{
                gate.await();JsonObject receipt=new JsonObject();receipt.addProperty("stage","claim");
                try{HorseNudgeStore.claim(root,"horse-nudge-race-key",receipt);return true;}
                catch(java.nio.file.FileAlreadyExistsException spent){return false;}
            }));
            gate.countDown();int winners=0;for(var future:futures)if(future.get())winners++;
            assertEquals(1,winners);
        }finally{executor.shutdownNow();}
    }
}
