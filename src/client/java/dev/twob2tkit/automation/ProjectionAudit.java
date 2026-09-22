package dev.twob2tkit.automation;
import com.google.gson.*;
import dev.twob2tkit.builder.LitematicaAccess;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.world.level.block.Blocks;
import java.util.*;
/** Read-only field-level differences. Existing blocks and block entities are reported, never removed. */
public final class ProjectionAudit {
 private ProjectionAudit(){}
 static String kind(String expected,String actual,boolean replaceable){return expected.equals(actual)?"state_only":replaceable?"missing":"occupied";}
 public static JsonObject scan(Minecraft c){
  var pick=LitematicaAccess.buildSelection();String loading=LitematicaAccess.loadingReason(pick);if(!loading.isEmpty())throw new IllegalStateException(loading);
  var world=LitematicaAccess.schematicWorld();long volume=(long)(pick.max().getX()-pick.min().getX()+1)*(pick.max().getY()-pick.min().getY()+1)*(pick.max().getZ()-pick.min().getZ()+1);
  if(volume>100000)throw new IllegalArgumentException("Projection audit volume exceeds the bounded scan size");
  var selectedCells=new HashSet<BlockPos>();var desiredAir=new HashSet<BlockPos>();var airConflicts=new LinkedHashMap<BlockPos,JsonObject>();var banners=new JsonArray();
  int matched=0,total=0;var rows=new JsonArray();var kinds=new TreeMap<String,Integer>();var wantedItems=new TreeMap<String,Integer>();var actualBlocks=new TreeMap<String,Integer>();
  for(var p:BlockPos.betweenClosed(pick.min(),pick.max())){
   if(!pick.contains(p)||!LitematicaAccess.inVisibleLayer(p))continue;
   if(!c.level.getChunkSource().hasChunk(p.getX()>>4,p.getZ()>>4))throw new IllegalStateException("Projection chunk is not loaded");
   var expected=world.getBlockState(p);if(expected.is(Blocks.STRUCTURE_VOID))continue;selectedCells.add(p.immutable());
   var actual=c.level.getBlockState(p);var blockEntity=c.level.getBlockEntity(p);
   if(blockEntity instanceof net.minecraft.world.level.block.entity.BannerBlockEntity banner)banners.add(ProjectionDecorations.banner(banner));
   if(expected.isAir()){
    desiredAir.add(p.immutable());
    if(!actual.isAir())airConflicts.put(p.immutable(),row(c,p,expected.toString(),"enclosed_air_candidate"));
    continue;
   }
   total++;if(expected.equals(actual)){matched++;continue;}
   String expectedId=BuiltInRegistries.BLOCK.getKey(expected.getBlock()).toString(),actualId=BuiltInRegistries.BLOCK.getKey(actual.getBlock()).toString();
   String type=kind(expectedId,actualId,actual.canBeReplaced()||actual.isAir());kinds.merge(type,1,Integer::sum);actualBlocks.merge(actualId,1,Integer::sum);
   rows.add(row(c,p,expected.toString(),type));
   String wanted=BuiltInRegistries.ITEM.getKey(expected.getBlock().asItem()).toString();if(!type.equals("state_only")&&!wanted.equals("minecraft:air")&&!expected.toString().contains("half=upper")&&!expected.toString().contains("part=head"))wantedItems.merge(wanted,1,Integer::sum);
  }
  var enclosed=ProjectionVoidPolicy.enclosed(selectedCells,desiredAir);var interiorRows=new JsonArray();
  airConflicts.forEach((pos,row)->{if(enclosed.contains(pos))interiorRows.add(row);});
  var out=new JsonObject();out.addProperty("audit_schema",2);out.addProperty("observed_at",System.currentTimeMillis());
  out.addProperty("server",c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip);out.addProperty("dimension",c.level.dimension().identifier().toString());
  out.addProperty("loaded_chunks_verified",true);out.addProperty("entity_coverage","client_loaded_entities_only");
  out.addProperty("enclosed_air_cells",enclosed.size());out.add("enclosed_air_conflicts",interiorRows);out.addProperty("exterior_air_conflicts_excluded",airConflicts.size()-interiorRows.size());
  out.add("decorations",ProjectionDecorations.entities(c,pick.min(),pick.max()));out.add("banners",banners);
  out.addProperty("name",pick.name());out.addProperty("placement_key",pick.key());out.addProperty("matched",matched);out.addProperty("total",total);out.add("mismatches",rows);out.add("kinds",new Gson().toJsonTree(kinds));out.add("replacement_items",new Gson().toJsonTree(wantedItems));out.add("actual_mismatch_blocks",new Gson().toJsonTree(actualBlocks));return out;
 }
 private static JsonObject row(Minecraft c,BlockPos p,String expected,String kind){
  var r=new JsonObject();r.add("pos",new Gson().toJsonTree(new int[]{p.getX(),p.getY(),p.getZ()}));r.addProperty("expected",expected);r.addProperty("actual",c.level.getBlockState(p).toString());r.addProperty("kind",kind);
  r.addProperty("block_entity",c.level.getBlockEntity(p)!=null);r.addProperty("fluid",!c.level.getFluidState(p).isEmpty());
  boolean adjacentFluid=false;for(var d:net.minecraft.core.Direction.values()){
   if(!c.level.hasChunkAt(p.relative(d))){r.addProperty("neighbors_loaded",false);return r;}
   adjacentFluid|=!c.level.getFluidState(p.relative(d)).isEmpty();
  }
  r.addProperty("neighbors_loaded",true);r.addProperty("adjacent_fluid",adjacentFluid);return r;
 }
}
