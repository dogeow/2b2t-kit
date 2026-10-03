package dev.twob2tkit.storage;

import com.google.gson.Gson;
import dev.twob2tkit.KitConfig;
import net.fabricmc.loader.impl.FabricLoaderImpl;
import net.fabricmc.loader.impl.game.GameProvider;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import java.lang.reflect.Proxy;
import java.nio.file.Path;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class NearbyInventoryTest {
    @TempDir static Path directory;
    @BeforeAll static void isolatedLoader(){
        var provider=(GameProvider)Proxy.newProxyInstance(GameProvider.class.getClassLoader(),new Class<?>[]{GameProvider.class},(p,m,a)->{
            if(m.getName().equals("getLaunchDirectory"))return directory;throw new AssertionError(m.getName());});
        FabricLoaderImpl.INSTANCE.setGameProvider(provider);
    }
    private final StorageLifecycle.Scope scope=new StorageLifecycle.Scope("example.com","","minecraft:overworld");
    private KitConfig.StoredItem item(String id,int count){return new KitConfig.StoredItem("minecraft:"+id,id,count);}
    private KitConfig.StorageSnapshot chest(int x,int z,int count,long observed){
        var r=new KitConfig.StorageSnapshot();r.server="EXAMPLE.com:25565";r.dimension="minecraft:overworld";r.x=x;r.y=64;r.z=z;
        r.blockId="minecraft:chest";r.status=StorageLifecycle.ACTIVE;r.lastSeenEpochMillis=observed;r.items.add(item("coal",count));
        r.containerPositions.add(new int[]{x,64,z});return r;
    }
    private List<NearbyInventory.Item> summarize(List<KitConfig.StoredItem> backpack,KitConfig.StorageSnapshot... records){
        return NearbyInventory.summarize(backpack,Arrays.asList(records),scope,"player-a",.5,.5);
    }
    @Test void includes4096ButExcludes4097AndTheRadiusIsHorizontalRatherThanVerticalOrASquare(){
        var boundary=chest(4096,0,64,100);boundary.y=3000;boundary.containerPositions=List.of(new int[]{4096,3000,0});
        var far=chest(4097,0,999,200);var diagonal=chest(3000,3000,888,300);var negativeBoundary=chest(0,-4096,32,400);
        var coal=summarize(List.of(),boundary,far,diagonal,negativeBoundary).getFirst();
        assertEquals(96,coal.cached());assertEquals(2,coal.sources().size());
        assertTrue(coal.sources().stream().allMatch(s->s.distance()==4096));
    }
    @Test void foreignUnknownFarOldHomeAndMissingContainersNeverContribute(){
        var current=chest(12,0,24,100);var foreign=chest(14,0,999,200);foreign.server="other.example";
        var otherDim=chest(16,0,999,200);otherDim.dimension="minecraft:the_nether";
        var unknown=chest(18,0,999,200);unknown.server="";
        var missing=chest(20,0,999,200);missing.status=StorageLifecycle.MISSING;
        var oldHome=chest(20000,0,999,200);var unscopedDimension=chest(22,0,999,200);unscopedDimension.dimension="";
        assertEquals(24,summarize(List.of(),current,foreign,otherDim,unknown,missing,oldHome,unscopedDimension).getFirst().cached());
    }
    @Test void singleplayerCachesMustBelongToTheExactSave(){
        var right=chest(10,0,8,100);right.server="singleplayer";right.worldId="/saves/a";
        var other=chest(20,0,64,200);other.server="singleplayer";other.worldId="/saves/b";
        var legacy=chest(30,0,999,300);legacy.server="singleplayer";
        var rows=NearbyInventory.summarize(List.of(),List.of(right,other,legacy),new StorageLifecycle.Scope("singleplayer","/saves/a","minecraft:overworld"),"player-a",0,0);
        assertEquals(8,rows.getFirst().cached());
    }
    @Test void doubleChestDuplicateHalvesAndLegacySingleHalfUseOneLatestCombinedContentsSnapshot(){
        var first=chest(10,0,128,100);first.containerPositions.add(new int[]{11,64,0});
        var other=chest(11,0,96,200);other.containerPositions.add(new int[]{10,64,0});
        var legacyHalf=chest(11,0,64,50);
        var coal=summarize(List.of(item("coal",12)),legacyHalf,first,other).getFirst();
        assertEquals(12,coal.carried());assertEquals(96,coal.cached());assertEquals(108,coal.estimatedTotal());
        assertEquals(1,coal.sources().size());assertSame(other,coal.sources().getFirst().record());
        assertEquals(200,coal.oldestContentTime());assertEquals(200,coal.latestContentTime());
    }
    @Test void doubleChestStraddlingTheDistanceBoundaryUsesTheNearbyHalf(){
        var r=chest(4097,0,64,100);r.containerPositions.add(new int[]{4096,64,0});
        assertEquals(64,summarize(List.of(),r).getFirst().cached());
    }
    @Test void enderSharedInventoryCountsOnceForTheCurrentPlayerAndDoesNotInventLegacyOwnership(){
        var first=chest(10,0,64,100);first.blockId="minecraft:ender_chest";first.playerId="player-a";
        var latest=chest(20,0,96,200);latest.blockId="minecraft:ender_chest";latest.playerId="player-a";
        var otherPlayer=chest(30,0,999,300);otherPlayer.blockId="minecraft:ender_chest";otherPlayer.playerId="player-b";
        var legacy=chest(40,0,999,400);legacy.blockId="minecraft:ender_chest";
        var coal=summarize(List.of(),first,latest,otherPlayer,legacy).getFirst();
        assertEquals(96,coal.cached());assertEquals(1,coal.sources().size());assertEquals("ender:player-a",coal.sources().getFirst().key());
        assertEquals("player-a",new Gson().fromJson(new Gson().toJson(latest),KitConfig.StorageSnapshot.class).playerId);
    }
    @Test void dirtyCacheIsAnExplicitEstimateAndUsesContentTimeRatherThanTheLatestStructureCheck(){
        var r=chest(10,0,64,100);r.contentsDirty=true;r.contentsDirtyReason="取料未确认";r.lastStructureObservedAt=900;
        var coal=summarize(List.of(item("coal",7)),r).getFirst();
        assertEquals(7,coal.carried());assertEquals(64,coal.cached());assertEquals(71,coal.estimatedTotal());
        assertTrue(coal.dirty());assertEquals(100,coal.oldestContentTime());assertEquals("取料未确认",coal.sources().getFirst().reason());
        assertTrue(NearbyInventoryScreen.summary(coal).contains("待确认"));
        assertEquals(64,r.items.getFirst().count);assertEquals(100,r.lastSeenEpochMillis);
    }
    @Test void currentBackpackIsCountedByIdSeparatelyFromCacheAndRefreshNeverReusesItsPreviousCount(){
        var r=chest(10,0,20,100);r.items.add(item("coal",4));r.items.add(item("charcoal",6));
        var first=summarize(List.of(item("coal",32),item("coal",5),item("charcoal",3)),r);
        var coal=first.stream().filter(row->row.id().equals("minecraft:coal")).findFirst().orElseThrow();
        assertEquals(37,coal.carried());assertEquals(24,coal.cached());assertEquals(61,coal.estimatedTotal());
        var refreshed=summarize(List.of(item("coal",2)),r).stream().filter(row->row.id().equals("minecraft:coal")).findFirst().orElseThrow();
        assertEquals(2,refreshed.carried());assertEquals(24,refreshed.cached());
        assertEquals(3,first.stream().filter(row->row.id().equals("minecraft:charcoal")).findFirst().orElseThrow().carried());
    }
    @Test void absentOrEvictedCachesRemainZeroAndUnobservedContainersAreNeverInvented(){
        var rows=summarize(List.of(item("coal",4)));assertEquals(4,rows.getFirst().carried());assertEquals(0,rows.getFirst().cached());
        assertTrue(rows.getFirst().sources().isEmpty());assertTrue(summarize(List.of()).isEmpty());
        assertEquals("附近没有此物品的已记录缓存",NearbyInventoryScreen.summary(rows.getFirst()));
    }
}
