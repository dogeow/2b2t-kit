package dev.twob2tkit.automation;
import com.google.gson.JsonObject;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.level.block.Block;
import net.minecraft.world.level.block.Blocks;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import java.util.ArrayList;
/** Re-prove local floor and the original water operation on every ownership check. */
final class ProjectedFloorWaterGuard {
    static boolean supportedGroundMob(String type){
        return java.util.Set.of("minecraft:zombie","minecraft:skeleton","minecraft:slime","minecraft:spider","minecraft:cave_spider").contains(type);
    }
    private static boolean loaded(Minecraft c,BlockPos p){
        return !c.level.isOutsideBuildHeight(p)&&c.level.getWorldBorder().isWithinBounds(p)
            &&LoadedServerChunkEvidence.isServerChunk(c.level,c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false));
    }
    static boolean floorSeal(net.minecraft.world.level.block.state.BlockState s,net.minecraft.world.level.BlockGetter level,BlockPos pos){
        return !s.is(Blocks.MAGMA_BLOCK)&&!s.is(Blocks.CAMPFIRE)&&!s.is(Blocks.SOUL_CAMPFIRE)
            &&Block.isFaceFull(s.getCollisionShape(level,pos),Direction.UP);
    }
    static boolean shieldedWorkspace(Minecraft c,JsonObject r){
        try{
            if(c.player==null||c.level==null)return false;
            var target=ProjectedSourceColumnGuard.point(r.get("pos"));boolean geometry=false;
            if("bucket_place".equals(ProjectionLoadPolicy.text(r,"op",64))&&ProjectedTrapdoorWaterlog.requested(r)){
                var g=new ProjectedTrapdoorWaterlog(c,r,target,true);g.require(c,false);geometry=true;
            }else if("bucket_fill".equals(ProjectionLoadPolicy.text(r,"op",64))&&ProjectedWaterlogDrain.requested(r)){
                var g=new ProjectedWaterlogDrain(c,r,target,true);geometry=g.current(c);
            }
            if(!geometry)return false;
            var p=c.player;var body=p.getBoundingBox();int x=(int)Math.floor(p.getX()),z=(int)Math.floor(p.getZ()),y=(int)Math.floor(body.minY+1e-7)-1;
            boolean pose=body.minX>=x+.05&&body.maxX<=x+.95&&body.minZ>=z+.05&&body.maxZ<=z+.95
                &&body.minY>=y+1-1e-7&&body.minY<=y+1.25&&body.getCenter().distanceToSqr(net.minecraft.world.phys.Vec3.atCenterOf(target))<=25;
            boolean floor=true;
            for(int dx=-1;dx<=1;dx++)for(int dz=-1;dz<=1;dz++){
                var pos=new BlockPos(x+dx,y,z+dz);if(!loaded(c,pos))return false;var s=c.level.getBlockState(pos);
                floor&=c.level.getBlockEntity(pos)==null&&floorSeal(s,c.level,pos);
            }
            long now=System.currentTimeMillis(),hurt=KitClient.config().lastAttackTimeEpochMillis;
            boolean quiet=hurt>=0&&hurt<=now&&(hurt==0||now-hurt>=5000);
            boolean projectileFree=c.level.getEntities(p,body.inflate(24),e->e instanceof Projectile projectile&&e.isAlive()
                &&projectile.getOwner()!=p&&e.getDeltaMovement().lengthSqr()>.0001).isEmpty();
            var threats=new ArrayList<ProjectedFloorWaterThreatPolicy.Threat>();
            for(var e:c.level.getEntities(p,body.inflate(16),e->e instanceof Enemy&&e.isAlive())){
                var type=BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();
                boolean supported=supportedGroundMob(type);
                threats.add(new ProjectedFloorWaterThreatPolicy.Threat(e.level()==c.level&&c.level.getEntity(e.getId())==e&&loaded(c,e.blockPosition()),
                    supported,p.hasLineOfSight(e),e.getBoundingBox().maxY));
            }
            return ProjectedFloorWaterThreatPolicy.permit(geometry,floor,pose,quiet,projectileFree,y,threats);
        }catch(RuntimeException unproved){return false;}
    }
}
