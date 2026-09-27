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
    private StorageLifecycle(){}
    record Scope(String server,String worldId,String dimension){}
    record Sight(boolean loaded,boolean container,String blockId,Set<BlockPos> parts){}
    interface World { Sight at(BlockPos pos); }
    public static String serverKey(String server){return server==null?"":server.trim().toLowerCase(Locale.ROOT).replaceFirst(":25565$","");}
    private static Scope scope(Minecraft c){
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
            case ACTIVE->"已核实";case MISSING->"容器已搬走或移除";
            case RECHECK->"容器已变化 · 请重新开箱";default->"历史记录 · 待核实";
        };
    }
    public static void normalize(KitConfig.StorageSnapshot record){
        if(record.server==null)record.server="";else record.server=serverKey(record.server);
        if(record.worldId==null)record.worldId="";
        if(record.invalidReason==null)record.invalidReason="";
        if(record.containerPositions==null)record.containerPositions=new ArrayList<>();
        if(record.history==null)record.history=new ArrayList<>();
        if(!known(record))record.status=UNKNOWN;
        else if(!Set.of(ACTIVE,MISSING,RECHECK,UNKNOWN).contains(record.status==null?"":record.status))record.status=RECHECK;
    }
    private static Set<BlockPos> positions(KitConfig.StorageSnapshot record){
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
        if(!ACTIVE.equals(record.status))return transition(record,RECHECK,"该位置已有容器，请开箱核对当前内容",now);
        return false;
    }
    private static boolean transition(KitConfig.StorageSnapshot record,String next,String reason,long now){
        if(next.equals(record.status)&&reason.equals(record.invalidReason))return false;
        archive(record);record.status=next;record.invalidReason=reason;record.lastVerifiedAt=now;return true;
    }
    public static int refresh(Minecraft c,KitConfig config){
        Scope scope=scope(c);if(scope==null||config==null||config.storageSnapshots==null)return 0;
        var world=world(c.level);int changed=0;long now=System.currentTimeMillis();
        for(var record:config.storageSnapshots)if(observe(record,scope,world,now))changed++;
        if(changed>0)config.save();return changed;
    }
    /** Closed-container maintenance runs independently of which UI is open. */
    public static void tick(Minecraft c,KitConfig config){
        if(c==null||c.level==null){observedLevel=null;return;}
        if(observedLevel!=c.level){observedLevel=c.level;dirty=true;}
        if(dirty||++ticks%20==0){dirty=false;refresh(c,config);}
    }
    /** Called only from authoritative server block-update packet tails. */
    public static void blockUpdated(Minecraft c,BlockPos position){
        if(c==null||c.level==null)return;
        var config=KitClient.config();if(config==null||config.storageSnapshots==null)return;
        for(var record:config.storageSnapshots)if(sameScope(c,record)
                &&new BlockPos(record.x,record.y,record.z).distManhattan(position)<=1){dirty=true;return;}
    }
    public static boolean usable(Minecraft c,KitConfig.StorageSnapshot record){
        if(!sameScope(c,record))return false;
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
        record.status=ACTIVE;record.invalidReason="";record.lastVerifiedAt=System.currentTimeMillis();
        record.containerPositions=new ArrayList<>();
        seen.parts.stream().sorted(Comparator.<BlockPos>comparingInt(BlockPos::getX).thenComparingInt(BlockPos::getY).thenComparingInt(BlockPos::getZ))
            .forEach(p->record.containerPositions.add(new int[]{p.getX(),p.getY(),p.getZ()}));
        return true;
    }
    public static void inherit(KitConfig.StorageSnapshot previous,KitConfig.StorageSnapshot fresh){
        if(previous==null)return;
        normalize(previous);fresh.history=new ArrayList<>(previous.history);
        var entry=historical(previous);fresh.history.add(entry);while(fresh.history.size()>8)fresh.history.removeFirst();
        if(previous.note!=null&&!previous.note.isBlank())fresh.note=previous.note;
    }
    private static void archive(KitConfig.StorageSnapshot record){
        if(record.history==null)record.history=new ArrayList<>();record.history.add(historical(record));
        while(record.history.size()>8)record.history.removeFirst();
    }
    private static KitConfig.StorageHistory historical(KitConfig.StorageSnapshot record){
        var history=new KitConfig.StorageHistory();history.server=record.server;history.worldId=record.worldId;
        history.observedAt=record.lastSeenEpochMillis;history.status=record.status;history.reason=record.invalidReason;
        history.note=record.note;history.blockId=record.blockId;
        if(record.items!=null)for(var item:record.items)history.items.add(new KitConfig.StoredItem(item.id,item.name,item.count));
        return history;
    }
}
