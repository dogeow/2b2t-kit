package dev.twob2tkit.storage;

import dev.twob2tkit.KitConfig;
import java.util.*;

/** Explicit depot permission updates. Stored contents are never refreshed by registration. */
public final class ProjectionSupplyRegistry {
    private ProjectionSupplyRegistry(){}
    public record Update(List<KitConfig.ProjectionSupplySource> sources,boolean changed){}
    public static Update set(List<KitConfig.ProjectionSupplySource> sources,String server,String world,String dimension,
                             KitConfig.StorageSnapshot record,boolean enabled){
        var scope=new StorageLifecycle.Scope(StorageLifecycle.serverKey(server),world,dimension);
        if(!StorageLifecycle.same(record,scope)||enabled&&!StorageLifecycle.ACTIVE.equals(record.status))
            throw new IllegalArgumentException("仓库记录不属于当前世界或结构已失效");
        var result=new ArrayList<KitConfig.ProjectionSupplySource>();int matching=0;
        if(sources!=null)for(var source:sources){
            if(source!=null&&StorageLifecycle.serverKey(source.server).equals(scope.server())
                    &&Objects.equals(source.worldId,world)&&Objects.equals(source.dimension,dimension)
                    &&source.x==record.x&&source.y==record.y&&source.z==record.z)matching++;
            else result.add(source);
        }
        if(enabled){
            var source=new KitConfig.ProjectionSupplySource();source.server=scope.server();source.worldId=world;
            source.dimension=dimension;source.x=record.x;source.y=record.y;source.z=record.z;result.add(source);
        }
        return new Update(result,matching!=(enabled?1:0));
    }
}
