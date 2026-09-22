package dev.twob2tkit.combat;
import dev.twob2tkit.KitConfig;
import net.minecraft.client.Minecraft;
/** Server death position has no timestamp; never invent a death time or reuse another dimension's record. */
public final class ServerDeathSync {
 private ServerDeathSync(){}
 public static String scope(Minecraft c){
  if(c.player==null)return "";
  String world=c.getCurrentServer()==null?"singleplayer:"+(c.getSingleplayerServer()==null?"":c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize()):c.getCurrentServer().ip.toLowerCase(java.util.Locale.ROOT).replaceFirst(":25565$","");
  return world+"|"+c.player.getUUID();
 }
 static boolean sameBlock(String oldDimension,double x,double y,double z,String dimension,int bx,int by,int bz){return oldDimension.equals(dimension)&&Math.floor(x)==bx&&Math.floor(y)==by&&Math.floor(z)==bz;}
 public static boolean sync(Minecraft c,KitConfig config){
  if(c.player==null||c.level==null||c.player.isDeadOrDying())return false;
  var optional=c.player.getLastDeathLocation();if(optional.isEmpty())return false;
  var marker=optional.get();var p=marker.pos();String dimension=marker.dimension().identifier().toString(),scope=scope(c);
  String key=scope+"|"+dimension+"|"+p.getX()+","+p.getY()+","+p.getZ();
  if(key.equals(config.deathIgnoredServerMarker)||key.equals(config.deathLastServerMarker))return false;
  boolean matches=config.hasDeathPoint&&(config.deathScope.isEmpty()||config.deathScope.equals(scope))&&sameBlock(config.deathDimension,config.deathX,config.deathY,config.deathZ,dimension,p.getX(),p.getY(),p.getZ());
  if(!matches&&config.deathSource.equals("client")&&scope.equals(config.deathScope)&&System.currentTimeMillis()-config.deathTimeEpochMillis<10000)return false;
  config.deathLastServerMarker=key;config.deathObservedEpochMillis=System.currentTimeMillis();
  if(!matches){
   config.hasDeathPoint=true;config.deathX=p.getX();config.deathY=p.getY();config.deathZ=p.getZ();config.deathDimension=dimension;
   config.deathTimeEpochMillis=0;config.deathKiller="";config.deathMessage="服务器最近死亡位置";config.deathActivity="服务器同步";config.deathSource="server";
  }
  config.deathScope=scope;config.save();return true;
 }
 public static boolean currentScope(Minecraft c,KitConfig config){return config.deathScope.isEmpty()||config.deathScope.equals(scope(c));}
}
