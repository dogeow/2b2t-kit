package dev.twob2tkit.storage;

import com.google.gson.Gson;
import dev.twob2tkit.KitConfig;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.game.GameProvider;
import net.minecraft.core.BlockPos;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class StorageLifecycleTest {
    @TempDir static Path directory;
    @BeforeAll static void loader(){
        var provider=(GameProvider)Proxy.newProxyInstance(GameProvider.class.getClassLoader(),new Class<?>[]{GameProvider.class},(p,m,a)->{
            if(m.getName().equals("getLaunchDirectory"))return directory;throw new AssertionError(m.getName());});
        FabricLoaderImpl.INSTANCE.setGameProvider(provider);
    }
    private final StorageLifecycle.Scope current=new StorageLifecycle.Scope("simpcraft.com","","minecraft:overworld");
    private final BlockPos position=new BlockPos(761016,65,797834);
    private KitConfig.StorageSnapshot record(){
        var r=new KitConfig.StorageSnapshot();r.server="simpcraft.com:25565";r.dimension="minecraft:overworld";
        r.x=position.getX();r.y=position.getY();r.z=position.getZ();r.blockId="minecraft:shulker_box";
        r.status=StorageLifecycle.ACTIVE;r.note="用户保留的铁库存备注";r.lastSeenEpochMillis=100;
        r.items.add(new KitConfig.StoredItem("minecraft:iron_ingot","铁锭",64));
        r.containerPositions.add(new int[]{r.x,r.y,r.z});return r;
    }
    private StorageLifecycle.Sight air(){return new StorageLifecycle.Sight(true,false,"minecraft:air",Set.of());}
    private StorageLifecycle.Sight unloaded(){return new StorageLifecycle.Sight(false,false,"",Set.of());}
    private StorageLifecycle.Sight box(BlockPos p,String id){return new StorageLifecycle.Sight(true,true,id,Set.of(p));}
    @Test void observedAirMarksMovedButRetainsUserNoteAndRecordedItems(){
        var r=record();assertTrue(StorageLifecycle.observe(r,current,p->air(),200));
        assertEquals(StorageLifecycle.MISSING,r.status);assertEquals(64,r.items.getFirst().count);assertTrue(r.note.contains("用户"));
        assertEquals(100,r.lastSeenEpochMillis);assertEquals(200,r.lastVerifiedAt);assertEquals(1,r.history.size());
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
    }
}
