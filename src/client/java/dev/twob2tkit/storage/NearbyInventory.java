package dev.twob2tkit.storage;

import dev.twob2tkit.KitConfig;
import net.minecraft.core.BlockPos;
import java.util.*;

/** Read-only accounting: carried counts are current observations; nearby contents are historical estimates. */
public final class NearbyInventory {
    public static final int RADIUS=4096;
    private NearbyInventory() {}
    public record Source(String key,KitConfig.StorageSnapshot record,long count,double distance,
                         long observedAt,boolean dirty,String reason) {}
    public record Item(String id,String name,long carried,long cached,List<Source> sources) {
        public long estimatedTotal(){return carried+cached;}
        public long oldestContentTime(){return sources.stream().mapToLong(Source::observedAt).min().orElse(0);}
        public long latestContentTime(){return sources.stream().mapToLong(Source::observedAt).max().orElse(0);}
        public boolean dirty(){return sources.stream().anyMatch(Source::dirty);}
    }
    private static final Comparator<BlockPos> POSITION=Comparator.<BlockPos>comparingInt(BlockPos::getX)
        .thenComparingInt(BlockPos::getZ).thenComparingInt(BlockPos::getY);
    private static BlockPos root(Map<BlockPos,BlockPos> parents,BlockPos position){
        var parent=parents.computeIfAbsent(position,p->p);
        if(!parent.equals(position)){parent=root(parents,parent);parents.put(position,parent);}return parent;
    }
    private static void join(Map<BlockPos,BlockPos> parents,BlockPos a,BlockPos b){
        a=root(parents,a);b=root(parents,b);
        if(!a.equals(b)){if(POSITION.compare(a,b)<0)parents.put(b,a);else parents.put(a,b);}
    }
    private static double distance(KitConfig.StorageSnapshot record,double x,double z){
        return StorageLifecycle.positions(record).stream().mapToDouble(p->Math.hypot(p.getX()+.5-x,p.getZ()+.5-z)).min().orElse(Double.POSITIVE_INFINITY);
    }
    private static KitConfig.StorageSnapshot newer(KitConfig.StorageSnapshot a,KitConfig.StorageSnapshot b){
        if(a.lastSeenEpochMillis!=b.lastSeenEpochMillis)return a.lastSeenEpochMillis>b.lastSeenEpochMillis?a:b;
        if(StorageLifecycle.ACTIVE.equals(a.status)!=StorageLifecycle.ACTIVE.equals(b.status))return StorageLifecycle.ACTIVE.equals(a.status)?a:b;
        return a.key().compareTo(b.key())<=0?a:b;
    }
    static List<Item> summarize(List<KitConfig.StoredItem> backpack,List<KitConfig.StorageSnapshot> snapshots,
                                StorageLifecycle.Scope scope,String playerId,double x,double z){
        var nearby=new ArrayList<KitConfig.StorageSnapshot>();var parents=new HashMap<BlockPos,BlockPos>();
        if(scope!=null&&Double.isFinite(x)&&Double.isFinite(z)&&snapshots!=null)for(var record:snapshots){
            if(record==null||!StorageLifecycle.same(record,scope)||StorageLifecycle.MISSING.equals(record.status)
                ||distance(record,x,z)>RADIUS)continue;
            if("minecraft:ender_chest".equals(record.blockId)){
                // Legacy ender snapshots have no player evidence and cannot safely be assigned to this account.
                if(playerId==null||playerId.isBlank()||!playerId.equals(record.playerId))continue;
            }else{
                var parts=StorageLifecycle.positions(record);var first=parts.iterator().next();
                for(var part:parts)join(parents,first,part);
            }
            nearby.add(record);
        }
        var unique=new TreeMap<String,KitConfig.StorageSnapshot>();
        for(var record:nearby){
            String key="minecraft:ender_chest".equals(record.blockId)?"ender:"+playerId
                :"container:"+root(parents,new BlockPos(record.x,record.y,record.z)).toShortString();
            unique.merge(key,record,NearbyInventory::newer);
        }
        var carried=new TreeMap<String,Long>();var cached=new TreeMap<String,Long>();var names=new HashMap<String,String>();
        var sources=new HashMap<String,List<Source>>();
        addCounts(backpack,carried,names);
        for(var entry:unique.entrySet()){
            var record=entry.getValue();var counts=new TreeMap<String,Long>();addCounts(record.items,counts,names);
            boolean dirty=record.contentsDirty||!StorageLifecycle.ACTIVE.equals(record.status);
            String reason=record.contentsDirtyReason==null||record.contentsDirtyReason.isBlank()?record.invalidReason:record.contentsDirtyReason;
            for(var item:counts.entrySet()){
                cached.merge(item.getKey(),item.getValue(),Long::sum);
                sources.computeIfAbsent(item.getKey(),id->new ArrayList<>()).add(new Source(entry.getKey(),record,item.getValue(),
                    distance(record,x,z),record.lastSeenEpochMillis,dirty,reason==null?"":reason));
            }
        }
        var ids=new TreeSet<String>(carried.keySet());ids.addAll(cached.keySet());var result=new ArrayList<Item>();
        for(var id:ids)result.add(new Item(id,names.getOrDefault(id,id),carried.getOrDefault(id,0L),cached.getOrDefault(id,0L),
            List.copyOf(sources.getOrDefault(id,List.of()).stream().sorted(Comparator.comparingDouble(Source::distance)).toList())));
        result.sort(Comparator.comparing(Item::name).thenComparing(Item::id));return List.copyOf(result);
    }
    private static void addCounts(List<KitConfig.StoredItem> items,Map<String,Long> counts,Map<String,String> names){
        if(items!=null)for(var item:items){
            if(item==null||item.id==null||item.id.isBlank()||item.count<=0)continue;
            counts.merge(item.id,(long)item.count,Long::sum);names.putIfAbsent(item.id,item.name==null||item.name.isBlank()?item.id:item.name);
        }
    }
}
