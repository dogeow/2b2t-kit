package dev.twob2tkit.automation;

import com.google.gson.*;
import dev.twob2tkit.builder.LitematicaAccess;
import dev.twob2tkit.runtime.engine.LoadedServerChunkEvidence;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.entity.projectile.Projectile;
import net.minecraft.world.entity.monster.Creeper;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.block.state.properties.Half;
import net.minecraft.world.level.block.state.properties.StairsShape;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.phys.AABB;
import java.util.*;

/** Pinned source-only chamber repair, preserving all existing sources and the bucket receipt path. */
final class ProjectedSourceColumnGuard {
    private final ProjectedSourceColumnPolicy.Bounds bounds;
    private final String placement;
    private final BlockPos target;
    private final Map<BlockPos,String> pins=new LinkedHashMap<>();
    private final Set<BlockPos> originalSources=new HashSet<>();
    static boolean requested(JsonObject r){
        if(!r.has("projected_source_column"))return false;
        var v=r.get("projected_source_column");
        if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("Source-column mode must be boolean");
        return v.getAsBoolean();
    }
    private static BlockPos point(JsonElement value){
        if(value==null||!value.isJsonArray()||value.getAsJsonArray().size()!=3)throw new IllegalArgumentException("Integer source-column XYZ required");
        int[] p=new int[3];
        for(int i=0;i<3;i++){
            var v=value.getAsJsonArray().get(i);
            if(!v.isJsonPrimitive()||!v.getAsJsonPrimitive().isNumber())throw new IllegalArgumentException("Integer source-column XYZ required");
            p[i]=v.getAsBigDecimal().intValueExact();
            if(Math.abs((long)p[i])>30000000)throw new IllegalArgumentException("Source-column XYZ outside world");
        }
        return new BlockPos(p[0],p[1],p[2]);
    }
    ProjectedSourceColumnGuard(Minecraft c,JsonObject r,BlockPos target){
        if(!r.has("source_column_bounds")||!r.get("source_column_bounds").isJsonObject())throw new IllegalArgumentException("Pinned source-column bounds required");
        var box=r.getAsJsonObject("source_column_bounds");var low=point(box.get("min"));var high=point(box.get("max"));
        bounds=new ProjectedSourceColumnPolicy.Bounds(low.getX(),low.getY(),low.getZ(),high.getX(),high.getY(),high.getZ());
        if(!bounds.contains(target.getX(),target.getY(),target.getZ()))throw new IllegalArgumentException("Only a source target inside the exact 3x1x9 chamber is supported");
        this.target=target.immutable();placement=ProjectionLoadPolicy.text(r,"placement_key",8192);
        if(placement.isBlank())throw new IllegalArgumentException("Locked source-column projection required");
        var required=new HashSet<BlockPos>();
        for(int x=bounds.minX();x<=bounds.maxX();x++)required.add(new BlockPos(x,bounds.minY()-1,bounds.minZ()));
        for(int y=bounds.minY();y<=bounds.maxY();y++){
            required.add(new BlockPos(bounds.minX()-1,y,bounds.minZ()));required.add(new BlockPos(bounds.maxX()+1,y,bounds.minZ()));
            for(int x=bounds.minX();x<=bounds.maxX();x++){
                required.add(new BlockPos(x,y,bounds.minZ()-1));required.add(new BlockPos(x,y,bounds.minZ()+1));
            }
        }
        if(!r.has("column_boundary_pins")||!r.get("column_boundary_pins").isJsonArray()
                ||r.getAsJsonArray("column_boundary_pins").size()!=75)throw new IllegalArgumentException("All 75 floor and wall pins are required");
        for(var raw:r.getAsJsonArray("column_boundary_pins")){
            if(!raw.isJsonObject())throw new IllegalArgumentException("Source-column pin object required");
            var pin=raw.getAsJsonObject();var pos=point(pin.get("pos"));String state=ProjectionLoadPolicy.text(pin,"expected_state",512);
            if(!required.contains(pos)||state.isBlank()||pins.putIfAbsent(pos,state)!=null)throw new IllegalArgumentException("Duplicate, missing or foreign source-column pin");
        }
        if(!pins.keySet().equals(required))throw new IllegalArgumentException("Source-column pins do not cover its exact boundary");
        for(int y=bounds.minY();y<=bounds.maxY();y++)for(int x=bounds.minX();x<=bounds.maxX();x++){
            var p=new BlockPos(x,y,bounds.minZ());if(level(c.level.getBlockState(p))==0)originalSources.add(p);
        }
    }
    /** Scope the existing hostile admission check only after re-proving the entire source chamber. */
    static boolean shieldedWorkspace(Minecraft c,JsonObject request){
        try{
            if(!"bucket_place".equals(ProjectionLoadPolicy.text(request,"op",64))||!requested(request)
                    ||c.player==null||c.level==null)return false;
            var target=point(request.get("pos"));var guard=new ProjectedSourceColumnGuard(c,request,target);
            guard.require(c,level(c.level.getBlockState(target))!=0);
            var p=c.player;var body=p.getBoundingBox();var b=guard.bounds;
            boolean horizontal=body.minX>=b.minX()&&body.maxX<=b.maxX()+1.0
                &&body.minZ>=b.minZ()&&body.maxZ<=b.minZ()+1.0;
            long now=System.currentTimeMillis(),hurt=dev.twob2tkit.KitClient.config().lastAttackTimeEpochMillis;
            boolean quiet=hurt>=0&&hurt<=now&&(hurt==0||now-hurt>=5000);
            boolean projectileFree=c.level.getEntities(p,body.inflate(24),e->e instanceof Projectile projectile
                &&e.isAlive()&&projectile.getOwner()!=p&&e.getDeltaMovement().lengthSqr()>.0001).isEmpty();
            var work=new SourceColumnThreatPolicy.Workspace(true,horizontal,body.minY>=b.minY(),
                body.minY>=b.minY()&&body.maxY<=b.maxY()+1.0,quiet,projectileFree);
            var threats=new ArrayList<SourceColumnThreatPolicy.Threat>();
            for(var e:c.level.getEntities(p,body.inflate(16),e->e instanceof net.minecraft.world.entity.monster.Enemy&&e.isAlive())){
                String type=BuiltInRegistries.ENTITY_TYPE.getKey(e.getType()).toString();
                boolean supported=type.equals("minecraft:zombie")||type.equals("minecraft:skeleton")||type.equals("minecraft:slime");
                boolean current=e.level()==c.level&&c.level.getEntity(e.getId())==e&&loaded(c,e.blockPosition());
                boolean visible=p.hasLineOfSight(e);var enemy=e.getBoundingBox();
                if(e instanceof Creeper creeper){
                    double dx=Math.max(0,Math.max(body.minX-enemy.maxX,enemy.minX-body.maxX));
                    double dy=Math.max(0,Math.max(body.minY-enemy.maxY,enemy.minY-body.maxY));
                    double dz=Math.max(0,Math.max(body.minZ-enemy.maxZ,enemy.minZ-body.maxZ));
                    if(SourceColumnThreatPolicy.remoteCreeper(work.verticallyEnclosed(),current,!creeper.isPowered(),visible,
                            creeper.isIgnited()||creeper.getSwellDir()>0||creeper.getSwelling(1)>0,body.minY>=enemy.maxY,dx*dx+dy*dy+dz*dz))continue;
                }
                threats.add(new SourceColumnThreatPolicy.Threat(current,supported,type.equals("minecraft:skeleton"),
                    visible,enemy.maxY<=b.minY(),body.minY-enemy.maxY));
            }
            return SourceColumnThreatPolicy.permit(work,threats);
        }catch(RuntimeException unproved){return false;}
    }
    private static int level(BlockState s){return s.isAir()?-1:s.is(Blocks.WATER)?s.getValue(LiquidBlock.LEVEL):-2;}
    private static boolean loaded(Minecraft c,BlockPos p){
        var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
        return !c.level.isOutsideBuildHeight(p)&&c.level.getWorldBorder().isWithinBounds(p)&&LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    private static boolean upDropper(BlockState s){return s.is(Blocks.DROPPER)&&s.getValue(DispenserBlock.FACING)==Direction.UP;}
    private static boolean dryStair(BlockState s){return s.is(Blocks.COBBLESTONE_STAIRS)&&s.getValue(StairBlock.FACING)==Direction.SOUTH
        &&s.getValue(StairBlock.HALF)==Half.BOTTOM&&s.getValue(StairBlock.SHAPE)==StairsShape.STRAIGHT&&!s.getValue(StairBlock.WATERLOGGED);}
    void require(Minecraft c,boolean before){
        var selection=LitematicaAccess.lockedBuildSelection();var model=LitematicaAccess.schematicWorld();
        if(model==null||!selection.key().equals(placement)||!LitematicaAccess.loadingReason(selection).isEmpty()
                ||c.level.environmentAttributes().getValue(net.minecraft.world.attribute.EnvironmentAttributes.WATER_EVAPORATES,target))
            throw new IllegalStateException("Source-column projection or environment changed");
        for(var p:BlockPos.betweenClosed(new BlockPos(bounds.minX()-1,bounds.minY()-1,bounds.minZ()-1),new BlockPos(bounds.maxX()+1,bounds.maxY()+1,bounds.minZ()+1)))
            if(!loaded(c,p)||!selection.contains(p)||!LitematicaAccess.inVisibleLayer(p))throw new IllegalStateException("Whole source-column envelope must be visible and server-loaded");
        int floors=0,walls=0;
        for(var entry:pins.entrySet()){
            var p=entry.getKey();var actual=c.level.getBlockState(p);var goal=model.getBlockState(p);boolean floor=p.getY()<bounds.minY();
            if(!ProjectedSourceColumnPolicy.samePinned(actual.toString(),entry.getValue(),floor)||!actual.getFluidState().isEmpty())throw new IllegalStateException("Pinned source-column seal changed");
            if(floor){
                if(!upDropper(actual)||!upDropper(goal)||!actual.isCollisionShapeFullBlock(c.level,p))throw new IllegalStateException("All three original UP droppers must seal the floor first");
                floors++;
            }else{
                Direction inward=p.getX()<bounds.minX()?Direction.EAST:p.getX()>bounds.maxX()?Direction.WEST:p.getZ()<bounds.minZ()?Direction.SOUTH:Direction.NORTH;
                boolean full=actual.isCollisionShapeFullBlock(c.level,p)&&!(actual.getBlock() instanceof LiquidBlockContainer);
                boolean stair=actual.equals(goal)&&dryStair(actual)&&inward==Direction.SOUTH;
                if(c.level.getBlockEntity(p)!=null||!(full||stair)||!Block.isFaceFull(actual.getCollisionShape(c.level,p),inward)
                        ||!(goal.isCollisionShapeFullBlock(model,p)||dryStair(goal)&&inward==Direction.SOUTH))throw new IllegalStateException("Source-column wall is not a proven dry inward barrier");
                walls++;
            }
        }
        var cells=new ArrayList<ProjectedSourceColumnPolicy.Cell>();
        for(int y=bounds.minY();y<=bounds.maxY();y++)for(int x=bounds.minX();x<=bounds.maxX();x++){
            var p=new BlockPos(x,y,bounds.minZ());cells.add(new ProjectedSourceColumnPolicy.Cell(level(model.getBlockState(p)),level(c.level.getBlockState(p)),originalSources.contains(p)));
            if(c.level.getBlockEntity(p)!=null)throw new IllegalStateException("Source chamber contains a block entity");
        }
        boolean topDry=true;
        for(int x=bounds.minX();x<=bounds.maxX();x++){
            var p=new BlockPos(x,bounds.maxY()+1,bounds.minZ());
            topDry&=c.level.getBlockState(p).isAir()&&level(model.getBlockState(p))==bounds.maxX()-x;
        }
        var volume=new AABB(bounds.minX(),bounds.minY(),bounds.minZ(),bounds.maxX()+1,bounds.maxY()+1,bounds.minZ()+1);
        boolean other=!c.level.getEntities(c.player,volume,e->e instanceof LivingEntity&&e.isAlive()).isEmpty();
        var p=c.player;boolean ready=p!=null&&ProjectedSourceColumnPolicy.actorReady(p.getHealth(),p.getFoodData().getFoodLevel(),p.getAirSupply(),p.getMaxAirSupply(),p.isInLava(),!p.isDeadOrDying());
        int index=(target.getY()-bounds.minY())*3+target.getX()-bounds.minX();
        String error=ProjectedSourceColumnPolicy.rejection(cells,index,before,floors,walls,topDry,ready,other);
        if(error!=null)throw new IllegalStateException(error);
    }
}
