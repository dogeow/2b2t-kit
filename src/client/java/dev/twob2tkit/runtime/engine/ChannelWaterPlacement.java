package dev.twob2tkit.runtime.engine;

import com.google.gson.*;
import java.nio.file.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.*;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.Entity;
import net.minecraft.world.level.ClipContext;
import net.minecraft.world.level.block.*;
import net.minecraft.world.level.block.state.properties.*;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.material.Fluids;
import net.minecraft.world.phys.*;
import dev.twob2tkit.runtime.api.RotationAim;

/** One ordinary bucket use in a witnessed two-wide east-flowing farm channel. No completion credit. */
final class ChannelWaterPlacement {
 private String last="";
 private static String text(JsonObject o,String k){return o!=null&&o.has(k)&&!o.get(k).isJsonNull()?o.get(k).getAsString():"";}
 private static boolean yes(JsonObject o,String k){return o!=null&&o.has(k)&&!o.get(k).isJsonNull()&&o.get(k).getAsBoolean();}
 private static int integer(JsonObject o,String k){return o.get(k).getAsBigDecimal().intValueExact();}
 private static BlockPos point(JsonObject o,String k){var a=o.getAsJsonArray(k);if(a==null||a.size()!=3)throw new IllegalArgumentException("Exact channel XYZ required");return new BlockPos(a.get(0).getAsBigDecimal().intValueExact(),a.get(1).getAsBigDecimal().intValueExact(),a.get(2).getAsBigDecimal().intValueExact());}
 private static boolean barrier(Minecraft c,BlockPos p){var s=c.level.getBlockState(p);return s.getFluidState().isEmpty()&&c.level.getBlockEntity(p)==null&&!(s.getBlock() instanceof FallingBlock)&&!(s.getBlock() instanceof LiquidBlockContainer)&&s.isCollisionShapeFullBlock(c.level,p);}
 private static boolean waterOrAir(Minecraft c,BlockPos p){var s=c.level.getBlockState(p);return s.isAir()||s.is(Blocks.WATER);}
 private static boolean geometry(Minecraft c,BlockPos origin,int length){
  for(int x=-1;x<=length;x++)for(int z=-1;z<=2;z++)for(int y=-1;y<=1;y++){
   var p=origin.offset(x,y,z);var chunk=c.level.getChunkSource().getChunk(p.getX()>>4,p.getZ()>>4,ChunkStatus.FULL,false);
   if(!LoadedServerChunkEvidence.isServerChunk(c.level,chunk))return false;
  }
  int floors=0,hoppers=0,sides=0,outlets=0;
  for(int x=0;x<length;x++){
   for(int z=0;z<2;z++){
    var p=origin.offset(x,0,z);if(!waterOrAir(c,p))return false;
    if(x<length-1){if(barrier(c,p.below()))floors++;}
    else{
     var floor=c.level.getBlockState(p.below());var chest=c.level.getBlockState(p.east().below());
     if(floor.is(Blocks.HOPPER)&&floor.getValue(HopperBlock.FACING)==Direction.EAST&&floor.getValue(HopperBlock.ENABLED)
       &&chest.is(Blocks.CHEST)&&chest.getValue(ChestBlock.FACING)==Direction.EAST&&!chest.getValue(ChestBlock.WATERLOGGED)
       &&chest.getValue(ChestBlock.TYPE)==(z==0?ChestType.LEFT:ChestType.RIGHT))hoppers++;
     var stop=c.level.getBlockState(p.east());if(stop.is(Blocks.COBBLESTONE_SLAB)&&stop.getValue(SlabBlock.TYPE)==SlabType.BOTTOM&&!stop.getValue(SlabBlock.WATERLOGGED))outlets++;
    }
   }
   if(barrier(c,origin.offset(x,0,-1)))sides++;if(barrier(c,origin.offset(x,0,2)))sides++;
  }
  for(int z=0;z<2;z++)if(barrier(c,origin.offset(-1,0,z)))sides++;
  return ChannelWaterPlacementPolicy.geometry(length,2,floors,hoppers,sides,outlets);
 }
 void tick(Minecraft c,boolean enabled){
  if(!enabled||c.player==null||c.level==null)return;
  Path root=c.gameDirectory.toPath().resolve("config/twob2tkit/automation"),input=root.resolve("channel-water.json");if(!Files.isRegularFile(input))return;
  String id="";Path claim=null;
  try{
   if(Files.size(input)>8192)throw new IllegalArgumentException("Oversized channel request");var r=JsonParser.parseString(Files.readString(input)).getAsJsonObject();id=text(r,"id");if(id.equals(last))return;
   if(!id.matches("[A-Za-z0-9_-]{1,96}")||integer(r,"protocol")!=1)throw new IllegalArgumentException("Channel request protocol invalid");
   var h=JsonParser.parseString(Files.readString(root.resolve("status.json"))).getAsJsonObject();var lease=h.getAsJsonObject("supervision_lease");long now=System.currentTimeMillis();
   boolean owner=lease!=null&&text(lease,"kind").equals("materials")&&text(r,"world_session").equals(text(h,"world_session"))&&text(r,"world_session").equals(text(lease,"world_session"))
     &&text(r,"lease_id").equals(text(lease,"id"))&&text(r,"task_session").equals(text(lease,"job_session"))&&text(r,"player_uuid").equals(c.player.getUUID().toString())
     &&r.get("control_revision").getAsLong()==h.get("control_revision").getAsLong()&&yes(h,"guard_armed")&&yes(h,"guard_pve_only")&&!yes(h,"guard_busy")&&!yes(h,"manual_movement")
     &&!yes(h,"health_recovery_hold")&&!yes(h.getAsJsonObject("safety_hold"),"active")&&!yes(h.getAsJsonObject("build_job"),"active")&&!yes(h.getAsJsonObject("professional_printer"),"owned")
     &&text(h,"phase").equals("done")&&EmptyBoatRecoveryPolicy.fresh(now,r.get("issued_at").getAsLong(),r.get("expires_at").getAsLong(),h.get("time").getAsLong());
   if(!owner||!text(h,"dimension").equals("minecraft:overworld")||c.gui.screen()!=null||c.player.containerMenu!=c.player.inventoryMenu||!c.player.containerMenu.getCarried().isEmpty()||c.player.getHealth()!=20||c.player.getFoodData().getFoodLevel()<18
     ||c.player.isInWater()||c.player.isInLava()||c.player.isOnFire()||c.player.isUsingItem()||c.player.hasInfiniteMaterials()||c.options.keyUse.isDown()||c.options.keyAttack.isDown()
     ||c.options.keyUp.isDown()||c.options.keyDown.isDown()||c.options.keyLeft.isDown()||c.options.keyRight.isDown()||c.options.keyJump.isDown()||c.options.keyShift.isDown())throw new IllegalStateException("Current healthy idle channel owner unavailable");
   var origin=point(r,"channel_origin");int length=integer(r,"length"),row=integer(r,"row");if(!ChannelWaterPlacementPolicy.shape(length,2,row))throw new IllegalArgumentException("Only bounded two-wide east-flowing channels are supported");var target=origin.offset(0,0,row);var support=target.below();
   var state=c.level.getBlockState(target);if(!state.toString().equals(text(r,"expected_state"))||!waterOrAir(c,target)||state.is(Blocks.WATER)&&state.getFluidState().isSource())throw new IllegalStateException("Exact unfilled channel source changed");
   var hand=c.player.getMainHandItem();if(!hand.is(net.minecraft.world.item.Items.WATER_BUCKET)||hand.getCount()!=1||c.player.getCooldowns().isOnCooldown(hand)||!geometry(c,origin,length))throw new IllegalStateException("Bucket or witnessed channel boundaries changed");
   if(c.player.getY()<target.getY()+1.8||!c.level.noCollision(c.player,c.player.getBoundingBox())||!c.level.getEntities(c.player,new AABB(origin.getX()-1,origin.getY(),origin.getZ()-1,origin.getX()+length+1,origin.getY()+1,origin.getZ()+3),Entity::isAlive).isEmpty())throw new IllegalStateException("Channel body or entity clearance changed");
   Vec3 aim=new Vec3(support.getX()+.5,support.getY()+.999,support.getZ()+.5);var eye=c.player.getEyePosition();var hit=c.level.clip(new ClipContext(eye,aim,ClipContext.Block.OUTLINE,ClipContext.Fluid.NONE,c.player));
   if(eye.distanceTo(aim)>c.player.blockInteractionRange()||!hit.getBlockPos().equals(support)||hit.getDirection()!=Direction.UP||!c.level.mayInteract(c.player,support)||!c.player.mayUseItemAt(target,Direction.UP,hand))throw new IllegalStateException("Normal channel bucket ray or permissions rejected");
   var look=RotationAim.lookAt(c.player,aim);c.player.setYRot(look.yaw());c.player.setXRot(look.pitch());
   String scope=text(h,"server")+"/"+text(h,"dimension");String key=Integer.toHexString(scope.hashCode())+"-"+target.getX()+"-"+target.getY()+"-"+target.getZ();claim=root.resolve("channel-water-claim-"+key+".json");
   if(Files.exists(claim))throw new IllegalStateException("Original channel use retained; no replay");
   var record=r.deepCopy();record.addProperty("use_may_have_been_sent",true);record.addProperty("claimed_at",now);Files.writeString(claim,record.toString(),StandardOpenOption.CREATE_NEW);last=id;
   if(!c.gameMode.useItem(c.player,InteractionHand.MAIN_HAND).consumesAction())throw new IllegalStateException("Normal bucket use was not accepted; outcome retained");
   publish(root,id,"use_sent","One normal bucket use sent; independent world/inventory confirmation required",now);
  }catch(Exception e){last=id;publish(root,id,claim!=null&&Files.exists(claim)?"retained_attempt":"rejected_preflight",e.getMessage(),System.currentTimeMillis());}
 }
 private static void publish(Path root,String id,String phase,String detail,long now){try{var r=new JsonObject();r.addProperty("protocol",1);r.addProperty("runtime_version",EngineBuildVersion.VALUE);r.addProperty("id",id);r.addProperty("phase",phase);r.addProperty("detail",detail);r.addProperty("time",now);r.addProperty("water_credit",0);Path tmp=root.resolve("channel-water-state.json.writing");Files.writeString(tmp,r.toString());Files.move(tmp,root.resolve("channel-water-state.json"),StandardCopyOption.ATOMIC_MOVE,StandardCopyOption.REPLACE_EXISTING);}catch(Exception ignored){}}
}
