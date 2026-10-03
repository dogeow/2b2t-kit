package dev.twob2tkit.storage;

import dev.twob2tkit.KitConfig;
import org.junit.jupiter.api.Test;
import java.util.ArrayList;
import static org.junit.jupiter.api.Assertions.*;

class StorageCacheTest {
    private KitConfig.StorageSnapshot record(String block,long time) {
        var r=new KitConfig.StorageSnapshot();r.blockId="minecraft:"+block;r.lastSeenEpochMillis=time;return r;
    }
    @Test void anOldCoalChestSurvivesHundredsOfRecentEmptyHoppers() {
        var records=new ArrayList<KitConfig.StorageSnapshot>();var coal=record("chest",1);
        coal.items.add(new KitConfig.StoredItem("minecraft:coal","煤炭",192));records.add(coal);
        for(int i=0;i<1000;i++)records.add(0,record("hopper",i+2));
        StorageCache.trim(records);
        assertEquals(StorageCache.MAX_EMPTY_HOPPERS+1,records.size());assertTrue(records.contains(coal));
        assertEquals(192,coal.items.getFirst().count);assertEquals(1,coal.lastSeenEpochMillis);
        assertEquals(1001,records.getFirst().lastSeenEpochMillis);
    }
    @Test void theOverallLimitEvictsEmptyUnlabelledStorageBeforeRecordedSuppliesAndUserNotes() {
        var records=new ArrayList<KitConfig.StorageSnapshot>();
        var supplies=record("barrel",1);supplies.items.add(new KitConfig.StoredItem("minecraft:coal","煤炭",64));
        var named=record("chest",2);named.note="用户保留的补货点";
        records.add(supplies);records.add(named);
        for(int i=0;i<StorageCache.MAX_RECORDS;i++)records.add(0,record("chest",i+3));
        StorageCache.trim(records);
        assertEquals(StorageCache.MAX_RECORDS,records.size());assertTrue(records.contains(supplies));assertTrue(records.contains(named));
        assertTrue(records.stream().noneMatch(r->r.lastSeenEpochMillis==3||r.lastSeenEpochMillis==4));
    }
    @Test void hopperWithNamedOrHistoricalSuppliesIsNotTreatedAsDiscardableEmptyTransit() {
        var records=new ArrayList<KitConfig.StorageSnapshot>();
        var historical=record("hopper",1);var old=new KitConfig.StorageHistory();
        old.items.add(new KitConfig.StoredItem("minecraft:coal","煤炭",64));historical.history.add(old);records.add(historical);
        var named=record("hopper",2);named.note="熔炉煤炭入口";records.add(named);
        for(int i=0;i<100;i++)records.add(0,record("hopper",i+3));
        StorageCache.trim(records);
        assertEquals(StorageCache.MAX_EMPTY_HOPPERS+2,records.size());assertTrue(records.contains(named));assertTrue(records.contains(historical));
        assertEquals(64,historical.history.getFirst().items.getFirst().count);
    }
    @Test void boundedUsefulCacheKeepsTheMostRecentContentsWhenAllRecordsHaveSupplies() {
        var records=new ArrayList<KitConfig.StorageSnapshot>();
        for(int i=0;i<StorageCache.MAX_RECORDS+10;i++){
            var r=record("chest",i+1);r.items.add(new KitConfig.StoredItem("minecraft:stone","石头",64));records.add(0,r);
        }
        StorageCache.trim(records);assertEquals(StorageCache.MAX_RECORDS,records.size());
        assertEquals(11,records.getLast().lastSeenEpochMillis);
    }
}
