package dev.twob2tkit.storage;

import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.Level;
import java.util.*;

/** Storage observations are scoped evidence, never permission to invent contents or delete history. */
public final class StorageLifecycle {
    public static final String ACTIVE="active", MISSING="missing", RECHECK="recheck", UNKNOWN="unknown_scope";
    private static boolean dirty;
    private static int ticks;
    private static Object observedLevel;
    private static final String PACKET_RECHECK="容器附近收到服务器更新，结构和库存待复核";
    static final Map<KitConfig.StorageSnapshot,BlockUpdate> blockUpdates=new IdentityHashMap<>();
    static final class BlockUpdate {
        final String status,invalidReason,contentsDirtyReason;
        final boolean contentsDirty;
        final long contentsDirtyAt;
        boolean direct,persisted;
        BlockUpdate(KitConfig.StorageSnapshot record,boolean direct){
            status=record.status;invalidReason=record.invalidReason;contentsDirty=record.contentsDirty;
            contentsDirtyReason=record.contentsDirtyReason;contentsDirtyAt=record.contentsDirtyAt;
            this.direct=direct;
        }
        void restore(KitConfig.StorageSnapshot record){
            record.status=status;record.invalidReason=invalidReason;record.contentsDirty=contentsDirty;
            record.contentsDirtyReason=contentsDirtyReason;record.contentsDirtyAt=contentsDirtyAt;
        }
    }
    private StorageLifecycle(){}
    record Scope(String server,String worldId,String dimension){}
    record Sight(boolean loaded,boolean container,String blockId,Set<BlockPos> parts){}
    interface World { Sight at(BlockPos pos); }
    public static String serverKey(String server){return server==null?"":server.trim().toLowerCase(Locale.ROOT).replaceFirst(":25565$","");}
    static Scope scope(Minecraft c){
        if(c==null||c.level==null)return null;
        return new Scope(serverKey(c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip),
            c.getSingleplayerServer()==null?"":c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize().toString(),
            KitConfig.normalizeDimension(c.level.dimension().identifier().toString()));
    }
    private static World world(Level level){return pos->{
        if(!level.hasChunkAt(pos))return new Sight(false,false,"",Set.of());
        String id=BuiltInRegistries.BLOCK.getKey(level.getBlockState(pos).getBlock()).toString();
        boolean storage=StorageLabels.isStorageBlock(level,pos);
        return new Sight(true,storage,id,storage?StorageLabels.cluster(level,pos):Set.of());
    };}
    static boolean known(KitConfig.StorageSnapshot record){
        return record!=null&&!serverKey(record.server).isBlank()
            &&(!serverKey(record.server).equals("singleplayer")||record.worldId!=null&&!record.worldId.isBlank());
    }
    static boolean same(KitConfig.StorageSnapshot record,Scope scope){
        return known(record)&&scope!=null&&serverKey(record.server).equals(scope.server)
            &&Objects.equals(record.worldId,scope.worldId)&&KitConfig.normalizeDimension(record.dimension).equals(scope.dimension);
    }
    public static boolean sameScope(Minecraft c,KitConfig.StorageSnapshot record){return same(record,scope(c));}
    public static String statusLabel(KitConfig.StorageSnapshot record){
        if(record==null||!known(record))return "历史记录 · 来源待核实";
        return switch(record.status==null?UNKNOWN:record.status){
            case ACTIVE->record.contentsDirty?"开箱缓存 · 待确认":"容器结构有效 · 开箱缓存";
            case MISSING->"容器已搬走或移除 · 历史缓存";
            case RECHECK->"容器已变化 · 缓存待确认";default->"历史记录 · 待核实";
        };
    }
    public static void normalize(KitConfig.StorageSnapshot record){
        if(record.server==null)record.server="";else record.server=serverKey(record.server);
        if(record.worldId==null)record.worldId="";
        if(record.playerId==null)record.playerId="";
        if(record.invalidReason==null)record.invalidReason="";
        if(record.contentsDirtyReason==null)record.contentsDirtyReason="";
        // Older versions mixed topology observation times into lastVerifiedAt.
        if(record.lastStructureObservedAt==0)record.lastStructureObservedAt=record.lastVerifiedAt;
        record.lastVerifiedAt=record.lastSeenEpochMillis;
        if(record.containerPositions==null)record.containerPositions=new ArrayList<>();
        if(record.history==null)record.history=new ArrayList<>();
        if(!known(record))record.status=UNKNOWN;
        else if(!Set.of(ACTIVE,MISSING,RECHECK,UNKNOWN).contains(record.status==null?"":record.status))record.status=RECHECK;
        if(MISSING.equals(record.status)||RECHECK.equals(record.status)){
            record.contentsDirty=true;
            if(record.contentsDirtyReason.isBlank())record.contentsDirtyReason=record.invalidReason;
        }
    }
    static Set<BlockPos> positions(KitConfig.StorageSnapshot record){
        var parts=new LinkedHashSet<BlockPos>();
        if(record.containerPositions!=null)for(int[] p:record.containerPositions){
            if(p==null||p.length!=3||parts.size()>=2)return Set.of();parts.add(new BlockPos(p[0],p[1],p[2]));
        }
        BlockPos primary=new BlockPos(record.x,record.y,record.z);
        if(parts.isEmpty())parts.add(primary);
        if(!parts.contains(primary)||parts.stream().anyMatch(p->p.distManhattan(primary)>1))return Set.of();
        return parts;
    }
    /** Missing chunks and foreign/legacy scopes leave prior evidence untouched. */
    static boolean observe(KitConfig.StorageSnapshot record,Scope scope,World world,long now){
        if(!same(record,scope))return false;
        pendingUpdate(record); // A real menu may already have replaced the provisional invalidation.
        var parts=positions(record);if(parts.isEmpty())return transition(record,RECHECK,"容器组合记录不完整，请重新开箱",now);
        var seen=new LinkedHashMap<BlockPos,Sight>();
        for(var pos:parts)seen.put(pos,world.at(pos));
        if(seen.values().stream().anyMatch(v->!v.loaded)){
            // An unseen half proves nothing; a loaded half that has changed is
            // nevertheless enough to invalidate the old combined contents.
            if(seen.values().stream().anyMatch(v->v.loaded&&(!v.container||!record.blockId.equals(v.blockId)||!parts.equals(v.parts))))
                return transition(record,RECHECK,"已加载的容器部分已变化，另一半尚未加载",now);
            return false;
        }
        if(seen.values().stream().noneMatch(Sight::container))return transition(record,MISSING,"当前世界已加载位置没有容器",now);
        BlockPos pos=new BlockPos(record.x,record.y,record.z);var primary=seen.get(pos);
        if(!primary.container)return transition(record,RECHECK,"原容器的一半已变化，旧合计库存待复核",now);
        if(!parts.equals(primary.parts))return transition(record,RECHECK,"容器类型或双箱组合已变化，旧库存待复核",now);
        // The other half can be in a neighboring unloaded chunk. Never infer its absence.
        for(var member:primary.parts)if(!world.at(member).loaded)return false;
        boolean matching=primary.blockId.equals(record.blockId)&&parts.equals(primary.parts)
            &&seen.values().stream().allMatch(v->v.container&&v.blockId.equals(record.blockId)&&parts.equals(v.parts));
        if(!matching)return transition(record,RECHECK,"容器类型或双箱组合已变化，旧库存待复核",now);
        var update=blockUpdates.remove(record);
        if(update!=null){
            update.restore(record);
            if(update.direct)
                return transition(record,RECHECK,"已记录的容器位置收到服务器更新，历史库存待确认",now);
            // A neighboring update is only provisional: fully loaded matching topology settles it.
            boolean changed=update.persisted;
            if(now-record.lastStructureObservedAt>=60_000||record.lastStructureObservedAt==0){
                record.lastStructureObservedAt=now;changed=true;
            }
            return changed;
        }
        if(MISSING.equals(record.status))return transition(record,RECHECK,"原位置重新出现容器，历史库存待确认",now);
        // Matching topology neither refreshes contents nor overwrites the original dirty reason.
        if(now-record.lastStructureObservedAt>=60_000||record.lastStructureObservedAt==0){
            record.lastStructureObservedAt=now;return true;
        }
        return false;
    }
    private static boolean transition(KitConfig.StorageSnapshot record,String next,String reason,long now){
        if(next.equals(record.status)&&reason.equals(record.invalidReason))return false;
        archive(record);record.status=next;record.invalidReason=reason;record.lastStructureObservedAt=now;
        record.contentsDirty=true;record.contentsDirtyReason=reason;record.contentsDirtyAt=now;return true;
    }
    /** A failed real inventory interaction invalidates confidence, never deletes the recorded quantities. */
    public static boolean markContentsDirty(KitConfig.StorageSnapshot record,String reason,long now){
        if(record==null)return false;
        String why=reason==null||reason.isBlank()?"取料未获服务器确认":reason;
        if(record.contentsDirty&&why.equals(record.contentsDirtyReason))return false;
        archive(record);record.contentsDirty=true;record.contentsDirtyReason=why;record.contentsDirtyAt=now;
        return true;
    }
    public static int refresh(Minecraft c,KitConfig config){
        Scope scope=scope(c);if(scope==null||config==null||config.storageSnapshots==null)return 0;
        return refresh(config.storageSnapshots,scope,world(c.level),System.currentTimeMillis(),config::save);
    }
    static int refresh(List<KitConfig.StorageSnapshot> records,Scope scope,World world,long now,Runnable save){
        // Removed/replaced records must not leave retained references in the transient packet queue.
        var retained=new HashSet<>(records);blockUpdates.keySet().removeIf(record->!retained.contains(record));
        int changed=0;
        for(var record:records){
            boolean changedRecord=observe(record,scope,world,now);
            var update=pendingUpdate(record);
            if(update!=null&&!update.persisted){update.persisted=true;changedRecord=true;}
            if(changedRecord)changed++;
        }
        // All packet invalidations and structure observations share one persistence write.
        if(changed>0)save.run();return changed;
    }
    /** Closed-container maintenance runs independently of which UI is open. */
    public static void tick(Minecraft c,KitConfig config){
        if(c==null||c.level==null){observedLevel=null;return;}
        if(observedLevel!=c.level){observedLevel=c.level;dirty=true;}
        if(dirty||++ticks%20==0){dirty=false;refresh(c,config);}
    }
    /** Called only from authoritative server block-update packet tails. */
    public static void blockUpdated(Minecraft c,BlockPos position){
        if(c==null||c.level==null||position==null)return;
        var config=KitClient.config();if(config==null||config.storageSnapshots==null)return;
        dirty|=markBlockUpdated(config.storageSnapshots,scope(c),position,System.currentTimeMillis());
    }
    /** Packet callbacks touch metadata only; world reads, history copies and saves belong to refresh. */
    static boolean markBlockUpdated(List<KitConfig.StorageSnapshot> records,Scope scope,BlockPos position,long now){
        boolean affected=false;
        for(var record:records){
            if(!same(record,scope))continue;
            int distance=Math.abs(record.x-position.getX())+Math.abs(record.y-position.getY())+Math.abs(record.z-position.getZ());
            boolean direct=distance==0,nearby=distance<=1;
            if(record.containerPositions!=null)for(var part:record.containerPositions){
                if(part==null||part.length!=3)continue;
                distance=Math.abs(part[0]-position.getX())+Math.abs(part[1]-position.getY())+Math.abs(part[2]-position.getZ());
                direct|=distance==0;nearby|=distance<=1;
            }
            if(!nearby)continue;
            affected=true;var update=pendingUpdate(record);
            if(update!=null){update.direct|=direct;continue;}
            if(!ACTIVE.equals(record.status))continue;
            blockUpdates.put(record,new BlockUpdate(record,direct));
            record.status=RECHECK;record.invalidReason=PACKET_RECHECK;
            record.contentsDirty=true;
            if(record.contentsDirtyReason==null||record.contentsDirtyReason.isBlank()){
                record.contentsDirtyReason=PACKET_RECHECK;record.contentsDirtyAt=now;
            }
        }
        return affected;
    }
    private static BlockUpdate pendingUpdate(KitConfig.StorageSnapshot record){
        var update=blockUpdates.get(record);
        if(update!=null&&(!RECHECK.equals(record.status)||!PACKET_RECHECK.equals(record.invalidReason))){
            blockUpdates.remove(record);return null;
        }
        return update;
    }
    public static boolean usable(Minecraft c,KitConfig.StorageSnapshot record){
        if(!sameScope(c,record))return false;
        if(pendingUpdate(record)!=null)return false;
        if(observe(record,scope(c),world(c.level),System.currentTimeMillis()))KitClient.config().save();
        return ACTIVE.equals(record.status);
    }
    /** A real open menu supplies fresh contents; merely replacing a block never does. */
    public static boolean capture(Minecraft c,BlockPos pos,KitConfig.StorageSnapshot record){
        Scope scope=scope(c);if(scope==null||pos==null)return false;
        var observed=world(c.level);var seen=observed.at(pos);
        if(!seen.loaded||!seen.container||seen.parts.isEmpty()||seen.parts.size()>2)return false;
        for(var p:seen.parts){var part=observed.at(p);if(!part.loaded||!part.container||!seen.parts.equals(part.parts))return false;}
        record.server=scope.server;record.worldId=scope.worldId;record.dimension=scope.dimension;
        record.playerId=c.player==null?"":c.player.getUUID().toString();
        record.status=ACTIVE;record.invalidReason="";record.lastStructureObservedAt=System.currentTimeMillis();
        record.lastVerifiedAt=record.lastSeenEpochMillis;
        record.contentsDirty=false;record.contentsDirtyReason="";record.contentsDirtyAt=0;
        record.containerPositions=new ArrayList<>();
        seen.parts.stream().sorted(Comparator.<BlockPos>comparingInt(BlockPos::getX).thenComparingInt(BlockPos::getY).thenComparingInt(BlockPos::getZ))
            .forEach(p->record.containerPositions.add(new int[]{p.getX(),p.getY(),p.getZ()}));
        return true;
    }
    public static void inherit(KitConfig.StorageSnapshot previous,KitConfig.StorageSnapshot fresh){
        if(previous==null)return;
        if(pendingUpdate(previous)!=null)archive(previous);
        normalize(previous);fresh.history=new ArrayList<>(previous.history);
        var entry=historical(previous);fresh.history.add(entry);while(fresh.history.size()>8)fresh.history.removeFirst();
        if(previous.note!=null&&!previous.note.isBlank())fresh.note=previous.note;
    }
    private static void archive(KitConfig.StorageSnapshot record){
        var history=historical(record);var update=blockUpdates.remove(record);
        if(update!=null){
            history.status=update.status;history.contentsDirty=update.contentsDirty;
            history.reason=update.contentsDirty&&update.contentsDirtyReason!=null&&!update.contentsDirtyReason.isBlank()
                ?update.contentsDirtyReason:update.invalidReason;
        }
        if(record.history==null)record.history=new ArrayList<>();record.history.add(history);
        while(record.history.size()>8)record.history.removeFirst();
    }
    private static KitConfig.StorageHistory historical(KitConfig.StorageSnapshot record){
        var history=new KitConfig.StorageHistory();history.server=record.server;history.worldId=record.worldId;
        history.observedAt=record.lastSeenEpochMillis;history.status=record.status;history.contentsDirty=record.contentsDirty;
        history.reason=record.contentsDirty&&!record.contentsDirtyReason.isBlank()?record.contentsDirtyReason:record.invalidReason;
        history.note=record.note;history.blockId=record.blockId;
        if(record.items!=null)for(var item:record.items)history.items.add(new KitConfig.StoredItem(item.id,item.name,item.count));
        return history;
    }
}
