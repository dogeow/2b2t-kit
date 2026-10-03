package dev.twob2tkit.storage;

import com.google.gson.Gson;
import dev.twob2tkit.KitConfig;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.game.GameProvider;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.util.*;
import java.util.concurrent.atomic.AtomicInteger;
import static org.junit.jupiter.api.Assertions.*;
class StorageLifecycleTest {
    @TempDir static Path directory;
    @BeforeAll static void loader(){
        var provider=(GameProvider)Proxy.newProxyInstance(GameProvider.class.getClassLoader(),new Class<?>[]{GameProvider.class},(p,m,a)->{
            if(m.getName().equals("getLaunchDirectory"))return directory;throw new AssertionError(m.getName());});
        FabricLoaderImpl.INSTANCE.setGameProvider(provider);
        net.minecraft.SharedConstants.tryDetectVersion();net.minecraft.server.Bootstrap.bootStrap();
    }
    @BeforeEach void clearPendingPackets(){StorageLifecycle.blockUpdates.clear();}
    private final StorageLifecycle.Scope current=new StorageLifecycle.Scope("simpcraft.com","","minecraft:overworld");
    private final BlockPos position=new BlockPos(761016,65,797834);
    private KitConfig.StorageSnapshot record(){
        var r=new KitConfig.StorageSnapshot();r.server="simpcraft.com:25565";r.dimension="minecraft:overworld";
        r.x=position.getX();r.y=position.getY();r.z=position.getZ();r.blockId="minecraft:shulker_box";
        r.status=StorageLifecycle.ACTIVE;r.note="用户保留的铁库存备注";r.lastSeenEpochMillis=100;
        r.lastVerifiedAt=100;r.lastStructureObservedAt=100;
        r.items.add(new KitConfig.StoredItem("minecraft:iron_ingot","铁锭",64));
        r.containerPositions.add(new int[]{r.x,r.y,r.z});return r;
    }
    private StorageLifecycle.Sight air(){return new StorageLifecycle.Sight(true,false,"minecraft:air",Set.of());}
    private StorageLifecycle.Sight unloaded(){return new StorageLifecycle.Sight(false,false,"",Set.of());}
    private StorageLifecycle.Sight box(BlockPos p,String id){return new StorageLifecycle.Sight(true,true,id,Set.of(p));}
    @Test void observedAirMarksMovedButRetainsUserNoteAndRecordedItems(){
        var r=record();assertTrue(StorageLifecycle.observe(r,current,p->air(),200));
        assertEquals(StorageLifecycle.MISSING,r.status);assertEquals(64,r.items.getFirst().count);assertTrue(r.note.contains("用户"));
        assertEquals(100,r.lastSeenEpochMillis);assertEquals(100,r.lastVerifiedAt);assertEquals(200,r.lastStructureObservedAt);
        assertTrue(r.contentsDirty);assertEquals(1,r.history.size());
        assertFalse(StorageLifecycle.observe(r,current,p->air(),201),"Unchanged observations do not keep saving or growing history");
    }
    @Test void unloadedForeignDimensionOrDifferentServerCannotGuessAContainerMissing(){
        var r=record();assertFalse(StorageLifecycle.observe(r,current,p->unloaded(),200));
        for(var scope:List.of(new StorageLifecycle.Scope("other.example","","minecraft:overworld"),
                new StorageLifecycle.Scope("simpcraft.com","","minecraft:the_nether"))){
            assertFalse(StorageLifecycle.observe(r,scope,p->{throw new AssertionError("Foreign worlds must not be probed");},200));}
        assertEquals(StorageLifecycle.ACTIVE,r.status);assertTrue(r.history.isEmpty());
    }
    @Test void unknownLegacyRecordKeepsUnknownProvenanceUntilARealOpen(){
        var r=record();r.server="";StorageLifecycle.normalize(r);assertEquals(StorageLifecycle.UNKNOWN,r.status);
        assertFalse(StorageLifecycle.observe(r,current,p->{throw new AssertionError("Legacy origin cannot be inferred from this server");},200));
        var fresh=record();fresh.note="";fresh.items.getFirst().count=8;StorageLifecycle.inherit(r,fresh);
        assertEquals(StorageLifecycle.ACTIVE,fresh.status);assertEquals("simpcraft.com:25565",fresh.server);
        assertEquals(8,fresh.items.getFirst().count);assertEquals(r.note,fresh.note);
        assertEquals("",fresh.history.getLast().server);assertEquals(64,fresh.history.getLast().items.getFirst().count);
        r.items.getFirst().count=1;assertEquals(64,fresh.history.getLast().items.getFirst().count);
    }
    @Test void replacingSameCoordinateRequiresNewContentsNotAutomaticResurrection(){
        var r=record();StorageLifecycle.observe(r,current,p->air(),200);
        assertTrue(StorageLifecycle.observe(r,current,p->box(p,r.blockId),300));assertEquals(StorageLifecycle.RECHECK,r.status);
        assertFalse(StorageLifecycle.observe(r,current,p->box(p,r.blockId),301));assertEquals(64,r.items.getFirst().count);
        var fresh=record();fresh.items.getFirst().count=2;StorageLifecycle.inherit(r,fresh);
        assertEquals(StorageLifecycle.ACTIVE,fresh.status);assertEquals(2,fresh.items.getFirst().count);assertFalse(fresh.history.isEmpty());
    }
    private KitConfig.StorageSnapshot doubleChest(){var r=record();r.blockId="minecraft:chest";r.containerPositions.add(new int[]{r.x+1,r.y,r.z});return r;}
    @Test void losingOneDoubleChestHalfInvalidatesCombinedCountWithoutClaimingBothGone(){
        var r=doubleChest();var other=position.east();
        assertTrue(StorageLifecycle.observe(r,current,p->p.equals(position)?air():box(other,r.blockId),200));
        assertEquals(StorageLifecycle.RECHECK,r.status);assertEquals(64,r.items.getFirst().count);
        assertTrue(StorageLifecycle.observe(r,current,p->air(),201));assertEquals(StorageLifecycle.MISSING,r.status);
    }
    @Test void doubleChestAcrossUnloadedChunkIsNotInventedMissingButKnownHalfChangeStillRequiresRecheck(){
        var r=doubleChest();var pair=Set.of(position,position.east());
        assertFalse(StorageLifecycle.observe(r,current,p->p.equals(position)?new StorageLifecycle.Sight(true,true,r.blockId,pair):unloaded(),200));
        assertEquals(StorageLifecycle.ACTIVE,r.status);
        assertTrue(StorageLifecycle.observe(r,current,p->p.equals(position)?air():unloaded(),201));
        assertEquals(StorageLifecycle.RECHECK,r.status);
    }
    @Test void changingTypeOrJoiningAnotherChestNeverReusesTheOldCountsAsVerified(){
        var r=record();assertTrue(StorageLifecycle.observe(r,current,p->box(p,"minecraft:barrel"),200));assertEquals(StorageLifecycle.RECHECK,r.status);
        var single=record();single.blockId="minecraft:chest";
        assertTrue(StorageLifecycle.observe(single,current,p->new StorageLifecycle.Sight(true,true,"minecraft:chest",Set.of(position,position.east())),200));
        assertEquals(StorageLifecycle.RECHECK,single.status);
    }
    @Test void scopedKeysSeparateServersAndSingleplayerSavesWithoutChangingSourceProtocol(){
        var one=record();var two=record();two.server="other.example";
        assertEquals(one.key(),two.key());assertNotEquals(one.scopedKey(),two.scopedKey());
        two.server="SIMPCraft.com";assertEquals(one.scopedKey(),two.scopedKey());
        one.server=two.server="singleplayer";one.worldId="/save/a";two.worldId="/save/b";
        assertNotEquals(one.scopedKey(),two.scopedKey());
        assertFalse(StorageLifecycle.same(one,new StorageLifecycle.Scope("singleplayer","/save/b","minecraft:overworld")));
        one.worldId="";assertFalse(StorageLifecycle.known(one));
    }
    @Test void statusProvenanceTopologyAndHistoryRoundTripWithoutMinecraftClient(){
        var r=record();StorageLifecycle.observe(r,current,p->air(),200);
        var gson=new Gson();var restored=gson.fromJson(gson.toJson(r),KitConfig.StorageSnapshot.class);
        assertEquals(r.scopedKey(),restored.scopedKey());assertEquals(StorageLifecycle.MISSING,restored.status);
        assertArrayEquals(new int[]{761016,65,797834},restored.containerPositions.getFirst());
        assertEquals(r.note,restored.note);assertEquals(64,restored.history.getFirst().items.getFirst().count);
        assertTrue(restored.contentsDirty);assertEquals(200,restored.lastStructureObservedAt);
    }
    @Test void sameShapeDirtyRecordRetainsTheOriginalReasonAndContentTime(){
        var r=record();r.lastVerifiedAt=100;
        StorageLifecycle.observe(r,current,p->box(p,"minecraft:barrel"),200);
        var reason=r.invalidReason;int history=r.history.size();
        assertFalse(StorageLifecycle.observe(r,current,p->box(p,r.blockId),300));
        assertEquals(reason,r.invalidReason);assertEquals(history,r.history.size());
        assertEquals(100,r.lastSeenEpochMillis);assertEquals(100,r.lastVerifiedAt);assertTrue(r.contentsDirty);
    }
    @Test void matchingStructureAfterUnloadAndRelogNeverRefreshesContentsOrMarksThemDirty(){
        var r=record();r.lastVerifiedAt=100;r.lastStructureObservedAt=100;
        assertFalse(StorageLifecycle.observe(r,current,p->unloaded(),200));
        var restored=new Gson().fromJson(new Gson().toJson(r),KitConfig.StorageSnapshot.class);
        StorageLifecycle.normalize(restored);
        assertFalse(StorageLifecycle.observe(restored,current,p->box(p,r.blockId),300));
        assertEquals(StorageLifecycle.ACTIVE,restored.status);assertFalse(restored.contentsDirty);
        assertEquals(100,restored.lastSeenEpochMillis);assertTrue(restored.history.isEmpty());
        assertTrue(StorageLifecycle.observe(restored,current,p->box(p,r.blockId),70_000));
        assertEquals(70_000,restored.lastStructureObservedAt);assertEquals(100,restored.lastVerifiedAt);
    }
    @Test void withdrawalFailureMarksOnlyConfidenceAndKeepsHistoryAndCachedCounts(){
        var r=record();r.lastVerifiedAt=100;
        assertTrue(StorageLifecycle.markContentsDirty(r,"Withdrawal not confirmed",200));
        assertEquals(StorageLifecycle.ACTIVE,r.status);assertTrue(r.contentsDirty);
        assertEquals(200,r.contentsDirtyAt);assertEquals(100,r.lastSeenEpochMillis);assertEquals(100,r.lastVerifiedAt);
        assertEquals(64,r.items.getFirst().count);assertEquals(64,r.history.getFirst().items.getFirst().count);
        assertFalse(StorageLifecycle.markContentsDirty(r,"Withdrawal not confirmed",201));
        assertFalse(StorageLifecycle.observe(r,current,p->box(p,r.blockId),300));
        assertEquals("Withdrawal not confirmed",r.contentsDirtyReason);
    }
    @Test void legacyMixedVerificationTimestampIsMigratedWithoutMakingContentsNewer(){
        var r=record();r.lastVerifiedAt=500;r.lastStructureObservedAt=0;
        StorageLifecycle.normalize(r);
        assertEquals(100,r.lastVerifiedAt);assertEquals(500,r.lastStructureObservedAt);
        assertEquals(100,r.lastSeenEpochMillis);
    }
    @Test void unchangedRealOpenObservationClearsDirtyWithoutLosingRecordedCountsOrHistory(){
        var config=new KitConfig();var r=record();StorageLifecycle.normalize(r);
        StorageLifecycle.markContentsDirty(r,"Withdrawal not confirmed",200);config.storageSnapshots.add(r);
        var confirmed=record();StorageLifecycle.normalize(confirmed);confirmed.lastSeenEpochMillis=300;
        confirmed.lastStructureObservedAt=300;config.patchStorageLabels(confirmed);
        assertFalse(r.contentsDirty);assertEquals("",r.contentsDirtyReason);assertEquals(0,r.contentsDirtyAt);
        assertEquals(300,r.lastSeenEpochMillis);assertEquals(300,r.lastVerifiedAt);
        assertEquals(64,r.items.getFirst().count);assertEquals(1,r.history.size());
    }
    @Test void sectionPacketBurstInvalidatesImmediatelyButCopiesHistoryAndSavesOnlyOnceOnRefresh(){
        var first=record();var second=record();second.x+=10;second.containerPositions.clear();
        second.containerPositions.add(new int[]{second.x,second.y,second.z});
        var records=List.of(first,second);var saves=new AtomicInteger();var reads=new AtomicInteger();
        for(int i=0;i<4096;i++)assertTrue(StorageLifecycle.markBlockUpdated(records,current,
            i%2==0?position:new BlockPos(second.x,second.y,second.z),200+i));
        for(var r:records){
            assertEquals(StorageLifecycle.RECHECK,r.status);assertTrue(r.contentsDirty);
            assertTrue(r.history.isEmpty(),"Packet callbacks must not copy inventory history");
            assertEquals(100,r.lastSeenEpochMillis);assertEquals(100,r.lastVerifiedAt);
            assertEquals(64,r.items.getFirst().count);assertTrue(r.note.contains("用户"));
        }
        assertEquals(0,saves.get());
        assertEquals(2,StorageLifecycle.refresh(records,current,p->{reads.incrementAndGet();return box(p,first.blockId);},5000,saves::incrementAndGet));
        assertEquals(1,saves.get());assertEquals(4,reads.get());
        for(var r:records){
            assertEquals(StorageLifecycle.RECHECK,r.status,"Same-shape replacements do not resurrect old contents");
            assertEquals(1,r.history.size());assertEquals(StorageLifecycle.ACTIVE,r.history.getFirst().status);
            assertFalse(r.history.getFirst().contentsDirty);assertEquals(64,r.history.getFirst().items.getFirst().count);
        }
        assertEquals(0,StorageLifecycle.refresh(records,current,p->box(p,first.blockId),5001,saves::incrementAndGet));
        assertEquals(1,saves.get());
    }
    @Test void neighboringUpdateIsProvisionalUntilLoadedMatchingTopologyThenKeepsOriginalContentsConfidence(){
        var r=record();var saves=new AtomicInteger();
        assertTrue(StorageLifecycle.markBlockUpdated(List.of(r),current,position.north(),200));
        assertEquals(StorageLifecycle.RECHECK,r.status);assertTrue(r.contentsDirty);
        assertEquals(0,StorageLifecycle.refresh(List.of(r),current,p->box(p,r.blockId),300,saves::incrementAndGet));
        assertEquals(StorageLifecycle.ACTIVE,r.status);assertFalse(r.contentsDirty);
        assertEquals("",r.invalidReason);assertEquals("",r.contentsDirtyReason);assertEquals(0,r.contentsDirtyAt);
        assertEquals(100,r.lastSeenEpochMillis);assertEquals(100,r.lastVerifiedAt);assertTrue(r.history.isEmpty());
        assertEquals(0,saves.get(),"Settling a harmless neighbor update need not persist a transient marker");
    }
    @Test void unloadedPacketAffectedContainerStaysInvalidAndItsMarkerIsPersistedOnlyOnceUntilRechecked(){
        var r=record();var saves=new AtomicInteger();
        StorageLifecycle.markBlockUpdated(List.of(r),current,position.north(),200);
        assertEquals(1,StorageLifecycle.refresh(List.of(r),current,p->unloaded(),300,saves::incrementAndGet));
        assertEquals(StorageLifecycle.RECHECK,r.status);assertTrue(r.contentsDirty);assertTrue(r.history.isEmpty());
        assertEquals(0,StorageLifecycle.refresh(List.of(r),current,p->unloaded(),301,saves::incrementAndGet));
        assertEquals(1,saves.get());
        assertEquals(1,StorageLifecycle.refresh(List.of(r),current,p->box(p,r.blockId),302,saves::incrementAndGet));
        assertEquals(StorageLifecycle.ACTIVE,r.status);assertFalse(r.contentsDirty);assertEquals(2,saves.get());
    }
    @Test void directUpdateOfOtherDoubleChestHalfInvalidatesTheOriginalCombinedInventory(){
        var r=doubleChest();var pair=Set.of(position,position.east());var saves=new AtomicInteger();
        assertTrue(StorageLifecycle.markBlockUpdated(List.of(r),current,position.east().east(),200));
        assertEquals(0,StorageLifecycle.refresh(List.of(r),current,p->new StorageLifecycle.Sight(true,true,r.blockId,pair),201,saves::incrementAndGet));
        assertEquals(StorageLifecycle.ACTIVE,r.status);
        assertTrue(StorageLifecycle.markBlockUpdated(List.of(r),current,position.east(),202));
        assertEquals(1,StorageLifecycle.refresh(List.of(r),current,p->new StorageLifecycle.Sight(true,true,r.blockId,pair),203,saves::incrementAndGet));
        assertEquals(StorageLifecycle.RECHECK,r.status);assertTrue(r.contentsDirty);
        assertEquals(64,r.items.getFirst().count);assertEquals(1,r.history.size());assertEquals(1,saves.get());
    }
    @Test void aRealOpenAfterPacketInvalidationSupersedesThePendingMarker(){
        var config=new KitConfig();var r=record();StorageLifecycle.normalize(r);config.storageSnapshots.add(r);
        StorageLifecycle.markBlockUpdated(config.storageSnapshots,current,position,200);
        var confirmed=record();StorageLifecycle.normalize(confirmed);confirmed.lastSeenEpochMillis=300;
        confirmed.lastStructureObservedAt=300;config.patchStorageLabels(confirmed);
        var saves=new AtomicInteger();
        assertEquals(0,StorageLifecycle.refresh(config.storageSnapshots,current,p->box(p,r.blockId),301,saves::incrementAndGet));
        assertEquals(StorageLifecycle.ACTIVE,r.status);assertFalse(r.contentsDirty);
        assertEquals(300,r.lastSeenEpochMillis);assertEquals(300,r.lastVerifiedAt);assertEquals(0,saves.get());
        assertTrue(StorageLifecycle.blockUpdates.isEmpty());
    }
    @Test void packetMetadataInvalidationLeavesForeignAndUnrelatedRecordsUntouched(){
        var r=record();var foreign=record();foreign.server="other.example";
        assertFalse(StorageLifecycle.markBlockUpdated(List.of(r,foreign),current,position.above(2),200));
        assertTrue(StorageLifecycle.markBlockUpdated(List.of(r,foreign),current,position,201));
        assertEquals(StorageLifecycle.ACTIVE,foreign.status);assertFalse(foreign.contentsDirty);assertTrue(foreign.history.isEmpty());
        var saves=new AtomicInteger();
        StorageLifecycle.refresh(List.of(r,foreign),current,p->air(),202,saves::incrementAndGet);
        assertEquals(StorageLifecycle.MISSING,r.status);assertEquals(StorageLifecycle.ACTIVE,foreign.status);
        assertEquals(StorageLifecycle.ACTIVE,r.history.getFirst().status);assertEquals(1,saves.get());
    }
}
