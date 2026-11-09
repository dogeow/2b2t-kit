package dev.twob2tkit.runtime.engine;

import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.block.LeavesBlock;
import net.minecraft.world.level.block.state.BlockState;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.phys.Vec3;
import dev.twob2tkit.runtime.api.RotationAim;

/** Normal instant shearing pipelined across a bounded, stationary material batch.
 * Vanilla owns predictions and server corrections. No packet or local block fabrication.
 */
public final class LeafShearBatch {
    private static LeafShearBatch running;
    private static String last="";
    private final JsonObject request;
    private final List<BlockPos> targets=new ArrayList<>(),sent=new ArrayList<>();
    private final Map<BlockPos,String> items=new HashMap<>();
    private final ArrayDeque<BlockPos> deferred=new ArrayDeque<>();
    private final BorerMiningConfirmation confirmation=new BorerMiningConfirmation();
    private final Path root,claim;
    private final Vec3 station;
    private int index,ticks,lastSent=-1,stable;
    private BlockPos mining;
    private Direction miningFace;
    private int miningTicks;
    private String stopped="",phase="running";
    private static String text(JsonObject j,String k){return j!=null&&j.has(k)&&!j.get(k).isJsonNull()?j.get(k).getAsString():"";}
    private static boolean yes(JsonObject j,String k){return j!=null&&j.has(k)&&!j.get(k).isJsonNull()&&j.get(k).getAsBoolean();}
    private static BlockPos point(JsonArray a){
        if(a==null||a.size()!=3)throw new IllegalArgumentException("Integer leaf XYZ required");
        int[] p=new int[3];for(int i=0;i<3;i++)p[i]=a.get(i).getAsBigDecimal().intValueExact();
        return new BlockPos(p[0],p[1],p[2]);
    }
    private static boolean natural(BlockState s){return s.is(BlockTags.LEAVES)&&s.hasProperty(LeavesBlock.PERSISTENT)&&!s.getValue(LeavesBlock.PERSISTENT)&&s.getFluidState().isEmpty();}
    private static String blockId(BlockState s){return BuiltInRegistries.BLOCK.getKey(s.getBlock()).toString();}
    private static void write(Path file,JsonObject value)throws Exception{
        Path temp=file.resolveSibling(file.getFileName()+".writing");Files.writeString(temp,value.toString());
        Files.move(temp,file,StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);
    }
    private LeafShearBatch(Minecraft c,Path root,JsonObject r)throws Exception{
        this.root=root;request=r.deepCopy();station=c.player.position();
        String id=text(r,"id");if(!id.matches("[A-Za-z0-9_-]{1,96}")||r.get("protocol").getAsInt()!=1)throw new IllegalArgumentException("Invalid leaf burst identity");
        var list=r.getAsJsonArray("targets");if(list==null||list.isEmpty()||list.size()>32)throw new IllegalArgumentException("1..32 leaf targets required");
        var unique=new HashSet<BlockPos>();
        for(var e:list){var row=e.getAsJsonObject();var p=point(row.getAsJsonArray("pos"));if(!unique.add(p)||Math.abs(p.getY()-c.player.getY())>6||c.player.position().distanceTo(Vec3.atCenterOf(p))>6)throw new IllegalArgumentException("Duplicate or distant leaf target");targets.add(p);items.put(p,text(row,"item"));}
        Path claims=root.resolve("leaf-shear-claims");Files.createDirectories(claims);claim=claims.resolve(id+".json");
        Files.writeString(claim,r.toString(),StandardOpenOption.CREATE_NEW,StandardOpenOption.WRITE);
    }
    private boolean scope(Minecraft c,JsonObject state,long now){
        var lease=state.has("supervision_lease")&&!state.get("supervision_lease").isJsonNull()?state.getAsJsonObject("supervision_lease"):null;
        String server=c.getCurrentServer()==null?"":c.getCurrentServer().ip;
        long expiry=request.get("expires_at").getAsLong();
        return now-state.get("time").getAsLong()>=0&&now-state.get("time").getAsLong()<2000&&expiry>=now&&expiry-now<=15000
            &&text(request,"server").equals(server)&&text(request,"dimension").equals(c.level.dimension().identifier().toString())
            &&text(request,"player_uuid").equals(c.player.getUUID().toString())&&lease!=null&&text(lease,"kind").equals("materials")
            &&request.get("input_serial").getAsLong()==state.getAsJsonObject("game_interaction").get("interaction_serial").getAsLong()
            &&text(request,"world_session").equals(text(state,"world_session"))&&text(request,"world_session").equals(text(lease,"world_session"))
            &&text(request,"lease_id").equals(text(lease,"id"))&&text(request,"task_session").equals(text(lease,"job_session"))
            &&request.get("expected_revision").getAsLong()==state.get("control_revision").getAsLong()
            &&lease.get("revision").getAsLong()==state.get("control_revision").getAsLong()
            &&yes(state,"guard_armed")&&yes(state,"guard_pve_only")&&!yes(state,"guard_busy")&&!yes(state,"manual_movement")
            &&!yes(state.getAsJsonObject("safety_hold"),"active")&&!yes(state,"health_recovery_hold")
            &&!yes(state,"navigating")&&!yes(state,"native_material_busy")
            &&(!state.has("pending_scan")||state.get("pending_scan").isJsonNull())
            &&c.gui.screen()==null&&c.player.containerMenu==c.player.inventoryMenu&&c.player.containerMenu.getCarried().isEmpty()
            &&!c.options.keyUp.isDown()&&!c.options.keyDown.isDown()&&!c.options.keyLeft.isDown()&&!c.options.keyRight.isDown()&&!c.options.keyJump.isDown()
            &&c.player.position().distanceTo(station)<.45&&c.player.getHealth()>=19&&c.player.getFoodData().getFoodLevel()>=18
            &&!c.player.isUnderWater()&&!c.player.isInLava()&&!c.player.isOnFire()&&!c.player.isUsingItem();
    }
    private boolean loaded(Minecraft c,BlockPos p){
        var chunk=c.level.getChunkSource().getChunk(Math.floorDiv(p.getX(),16),Math.floorDiv(p.getZ(),16),ChunkStatus.FULL,false);
        return LoadedServerChunkEvidence.isServerChunk(c.level,chunk);
    }
    private void sendNext(Minecraft c)throws Exception{
        var held=c.player.getMainHandItem();
        if(!held.is(Items.SHEARS)||held.getMaxDamage()-held.getDamageValue()<2){stopped="shears_changed_or_exhausted";index=targets.size();deferred.clear();return;}
        boolean firstPass=index<targets.size();
        BlockPos p=firstPass?targets.get(index++):deferred.removeFirst();
        if(!loaded(c,p)||confirmation.pending(c.level,p)){
            if(firstPass)deferred.addLast(p);
            return;
        }
        var state=c.level.getBlockState(p);
        if(!natural(state)||!blockId(state).equals(items.get(p)))return;
        if(p.equals(c.player.blockPosition().below()))return;
        for(Direction d:Direction.values())if(!c.level.getFluidState(p.relative(d)).isEmpty())return;
        var eye=c.player.getEyePosition();var aim=Vec3.atCenterOf(p);
        if(eye.distanceTo(aim)>c.player.blockInteractionRange()-.3)return;
        var hit=c.level.clip(new ClipContext(eye,aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
        if(!hit.getBlockPos().equals(p)||state.getDestroyProgress(c.player,c.level,p)<=0)return;
        // The durable attempt precedes the normal interaction. A crash never
        // authorizes replay of this request identity.
        sent.add(p);var intent=request.deepCopy();var attempted=new JsonArray();for(var q:sent)attempted.add(new Gson().toJsonTree(new int[]{q.getX(),q.getY(),q.getZ()}));intent.add("attempted",attempted);write(claim,intent);
        RotationAim.apply(c.player,RotationAim.lookAt(c.player,aim));
        confirmation.startObservedBreak(c,p,hit.getDirection());c.player.swing(InteractionHand.MAIN_HAND);lastSent=ticks;
        if(!c.level.getBlockState(p).isAir()){mining=p;miningFace=hit.getDirection();miningTicks=0;}
    }
    private void continueLeaf(Minecraft c){
        if(c.level.getBlockState(mining).isAir()){mining=null;lastSent=ticks;return;}
        var held=c.player.getMainHandItem();
        if(!natural(c.level.getBlockState(mining))||!held.is(Items.SHEARS)||held.getMaxDamage()-held.getDamageValue()<2||++miningTicks>8){
            c.gameMode.stopDestroyBlock();mining=null;lastSent=ticks;return;
        }
        RotationAim.apply(c.player,RotationAim.lookAt(c.player,Vec3.atCenterOf(mining)));
        c.gameMode.continueDestroyBlock(mining,miningFace);c.player.swing(InteractionHand.MAIN_HAND);
        if(c.level.getBlockState(mining).isAir()){mining=null;lastSent=ticks;}
    }
    private void poll(Minecraft c,boolean enabled,boolean borerActive)throws Exception{
        ticks++;var state=JsonParser.parseString(Files.readString(root.resolve("status.json"))).getAsJsonObject();
        if(!enabled||borerActive||!scope(c,state,System.currentTimeMillis())){stopped="control_or_survival_changed";index=targets.size();deferred.clear();mining=null;}
        if(stopped.isEmpty()){
            if(mining!=null)continueLeaf(c);
            else if((index<targets.size()||!deferred.isEmpty())&&ticks%2==0)sendNext(c);
        }
        if(index>=targets.size()&&deferred.isEmpty()&&mining==null){
            boolean pending=sent.stream().anyMatch(p->confirmation.pending(c.level,p));
            stable=!pending?stable+1:0;
            if(stable>=1){phase=stopped.isEmpty()?"done":"stopped";publish(c,true);last=text(request,"id");running=null;return;}
            if(ticks>160){phase="waiting";stopped="vanilla_predictions_unsettled";publish(c,true);last=text(request,"id");running=null;return;}
        }
        if(ticks%4==0)publish(c,false);
    }
    private void publish(Minecraft c,boolean terminal)throws Exception{
        var out=new JsonObject();out.addProperty("protocol",1);out.addProperty("id",text(request,"id"));out.addProperty("phase",phase);out.addProperty("time",System.currentTimeMillis());
        for(String key:new String[]{"world_session","task_session","lease_id","expected_revision"})out.add(key,request.get(key));
        out.addProperty("execution","native_continuous_shears_v1");out.addProperty("attempted",sent.size());out.addProperty("reason",stopped);out.addProperty("ticks",ticks);
        out.addProperty("confirmation","vanilla_prediction_retired_and_live_block_observation");
        var removed=new JsonArray();var remaining=new JsonArray();var pending=new JsonArray();
        var host=JsonParser.parseString(Files.readString(root.resolve("status.json"))).getAsJsonObject();
        boolean same=text(host,"world_session").equals(text(request,"world_session"));
        for(var p:targets){var row=new JsonObject();row.add("pos",new Gson().toJsonTree(new int[]{p.getX(),p.getY(),p.getZ()}));row.addProperty("item",items.get(p));
            boolean waits=!same||!loaded(c,p)||confirmation.pending(c.level,p);row.addProperty("state",c.level.getBlockState(p).toString());
            if(waits)pending.add(row);else if(sent.contains(p)&&c.level.getBlockState(p).isAir())removed.add(row);else if(natural(c.level.getBlockState(p)))remaining.add(row);
        }
        out.add("removed",removed);out.add("remaining",remaining);out.add("pending",pending);out.addProperty("goal_credit",0);
        write(root.resolve("leaf-shear-state.json"),out);
        if(terminal)write(root.resolve("leaf-shear-claims").resolve(text(request,"id")+"-result.json"),out);
    }
    public static void tick(Minecraft c,boolean enabled,boolean borerActive){
        if(c.player==null||c.level==null||c.gameMode==null){running=null;return;}
        Path root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation");
        try{
            if(running!=null){running.poll(c,enabled,borerActive);return;}
            Path input=root.resolve("leaf-shear-request.json");if(!enabled||borerActive||!Files.isRegularFile(input)||Files.size(input)>16384)return;
            var r=JsonParser.parseString(Files.readString(input)).getAsJsonObject();String id=text(r,"id");if(id.equals(last))return;
            // Existing claims are never dispatched again after reload/reconnect.
            if(!id.matches("[A-Za-z0-9_-]{1,96}")||Files.exists(root.resolve("leaf-shear-claims").resolve(id+".json"))){last=id;return;}
            var candidate=new LeafShearBatch(c,root,r);running=candidate;candidate.poll(c,enabled,borerActive);
        }catch(Exception failure){
            if(running!=null){running.stopped="exception_"+failure.getClass().getSimpleName();running.phase="waiting";try{running.publish(c,true);}catch(Exception ignored){}last=text(running.request,"id");running=null;}
        }
    }
}
