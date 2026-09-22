package dev.twob2tkit.automation;
import com.google.gson.*;
import net.minecraft.client.Minecraft;
import net.minecraft.core.BlockPos;
import net.minecraft.core.registries.BuiltInRegistries;
import net.minecraft.tags.BlockTags;
import net.minecraft.world.level.levelgen.Heightmap;
import net.minecraft.world.level.block.state.properties.BlockStateProperties;
import java.util.*;
/** Compact, read-only survey of loaded surface trees. Never loads chunks or changes terrain. */
public final class TreeSurvey {
 private TreeSurvey(){}
 public static boolean supported(String id){return Set.of("minecraft:oak_log","minecraft:spruce_log","minecraft:birch_log","minecraft:jungle_log","minecraft:acacia_log","minecraft:dark_oak_log","minecraft:mangrove_log","minecraft:cherry_log","minecraft:pale_oak_log").contains(id==null?"":id);}
 public static JsonObject scan(Minecraft c,JsonObject request){
  String wanted=request.get("item").getAsString();if(!supported(wanted))throw new IllegalArgumentException("Expected a natural log species");
  int radius=request.has("radius")?request.get("radius").getAsInt():64;if(radius<8||radius>96)throw new IllegalArgumentException("Tree radius must be 8..96");
  var origin=c.player.blockPosition();var roots=new ArrayList<JsonObject>();var biomes=new TreeMap<String,Integer>();int columns=0,missing=0,maxSurface=c.level.getMinY();
  for(int dx=-radius;dx<=radius;dx++)for(int dz=-radius;dz<=radius;dz++){
   int x=origin.getX()+dx,z=origin.getZ()+dz;var column=new BlockPos(x,origin.getY(),z);
   if(!c.level.getChunkSource().hasChunk(x>>4,z>>4)){missing++;continue;}columns++;
   int top=c.level.getHeight(Heightmap.Types.MOTION_BLOCKING,x,z);maxSurface=Math.max(maxSurface,top);
   if((dx&15)==0&&(dz&15)==0){String biome=c.level.getBiome(new BlockPos(x,top,z)).unwrapKey().map(k->k.identifier().toString()).orElse("unknown");biomes.merge(biome,1,Integer::sum);}
   for(int y=top-1;y>=Math.max(c.level.getMinY(),top-48);y--){
    var p=new BlockPos(x,y,z);var state=c.level.getBlockState(p);
    if(!BuiltInRegistries.BLOCK.getKey(state.getBlock()).toString().equals(wanted)||!c.level.getBlockState(p.below()).is(BlockTags.DIRT))continue;
    int leaves=naturalLeaves(c,p,wanted.replace("_log","_leaves"));if(leaves<4)continue;
    var r=new JsonObject();var a=new JsonArray();a.add(x);a.add(y);a.add(z);r.add("pos",a);r.addProperty("natural_leaves",leaves);r.addProperty("top",top);roots.add(r);
   }
  }
  roots.sort(Comparator.comparingDouble(r->{var p=r.getAsJsonArray("pos");return Math.pow(p.get(0).getAsDouble()-origin.getX(),2)+Math.pow(p.get(2).getAsDouble()-origin.getZ(),2);}));
  var out=new JsonObject();var list=new JsonArray();roots.stream().limit(128).forEach(list::add);out.add("trees",list);out.add("biomes",new Gson().toJsonTree(biomes));out.addProperty("loaded_columns",columns);out.addProperty("unloaded_columns",missing);out.addProperty("highest_surface",maxSurface);return out;
 }
 private static int naturalLeaves(Minecraft c,BlockPos root,String leafId){
  int found=0;
  for(int dy=2;dy<=32;dy++)for(int dx=-3;dx<=3;dx++)for(int dz=-3;dz<=3;dz++){
   var p=root.offset(dx,dy,dz);if(!c.level.getChunkSource().hasChunk(p.getX()>>4,p.getZ()>>4))continue;var s=c.level.getBlockState(p);
   if(BuiltInRegistries.BLOCK.getKey(s.getBlock()).toString().equals(leafId)&&s.hasProperty(BlockStateProperties.PERSISTENT)&&!s.getValue(BlockStateProperties.PERSISTENT)&&++found>=4)return found;
  }return found;
 }
}
