package dev.twob2tkit.runtime.engine;
import com.google.gson.*;
import java.nio.file.*;
import java.util.*;
import net.minecraft.client.Minecraft;
import net.minecraft.world.entity.LivingEntity;
import net.minecraft.world.entity.monster.Enemy;

/** Keep unresolved UUIDs across an engine reload. Missing observations never become kills. */
final class BorerCombatContinuation {
 private Path path;
 private JsonObject cached;
 private final Set<UUID> missing=new LinkedHashSet<>();
 private boolean restored;
 private int nextWrite;
 BorerCombatContinuation(){
  var c=Minecraft.getInstance();if(c!=null)bind(c);
 }
 private void bind(Minecraft c){
  path=c.gameDirectory.toPath().resolve("config/twob2tkit/runtime/combat-continuation.json");
  try{if(Files.exists(path)&&Files.size(path)<16384)cached=JsonParser.parseString(Files.readString(path)).getAsJsonObject();}catch(Exception ignored){}
 }
 static boolean matches(JsonObject j,long now,String player,String server,String dimension){
  try{return now-j.get("time").getAsLong()>=0&&now-j.get("time").getAsLong()<300000
   &&j.get("player").getAsString().equals(player)&&j.get("server").getAsString().equals(server)
   &&j.get("dimension").getAsString().equals(dimension)&&j.getAsJsonArray("targets").size()<=8;
  }catch(Exception e){return false;}
 }
 boolean restore(Minecraft c,BorerCombatSession<LivingEntity> session){
  if(path==null)bind(c);
  if(!restored){
   restored=true;
   if(cached!=null&&matches(cached,System.currentTimeMillis(),c.player.getUUID().toString(),server(c),c.level.dimension().identifier().toString()))
    try{for(var v:cached.getAsJsonArray("targets"))missing.add(UUID.fromString(v.getAsString()));}catch(Exception e){missing.clear();}
   cached=null;
  }
  for(var e:c.level.entitiesForRendering())if(e instanceof LivingEntity living&&e instanceof Enemy&&e.distanceToSqr(c.player)<=48*48&&missing.remove(e.getUUID()))
   session.observe(e.getUUID(),living,true,living.isDeadOrDying(),c.player.hasLineOfSight(e),living.getHealth());
  return !missing.isEmpty();
 }
 void save(Minecraft c,BorerCombatSession<LivingEntity> session){
  if(c.player.tickCount<nextWrite)return;nextWrite=c.player.tickCount+40;
  var ids=new LinkedHashSet<>(missing);for(var e:session.targets())ids.add(e.getUUID());
  try{
   if(ids.isEmpty()){Files.deleteIfExists(path);return;}
   var j=new JsonObject();j.addProperty("time",System.currentTimeMillis());j.addProperty("player",c.player.getUUID().toString());j.addProperty("server",server(c));j.addProperty("dimension",c.level.dimension().identifier().toString());
   var list=new JsonArray();for(var id:ids)list.add(id.toString());j.add("targets",list);
   Files.createDirectories(path.getParent());var tmp=path.resolveSibling("combat-continuation.tmp");Files.writeString(tmp,j.toString());Files.move(tmp,path,StandardCopyOption.REPLACE_EXISTING,StandardCopyOption.ATOMIC_MOVE);
  }catch(Exception ignored){}
 }
 void clear(){cached=null;missing.clear();restored=true;if(path!=null)try{Files.deleteIfExists(path);}catch(Exception ignored){}}
 private static String server(Minecraft c){return c.getCurrentServer()==null?"singleplayer":c.getCurrentServer().ip;}
}
