package dev.twob2tkit.runtime.engine;
import com.google.gson.JsonObject;
final class ResidentPotionPolicy {
 static boolean therapeutic(JsonObject contents){
  return contents!=null&&contents.size()==1&&contents.has("potion")&&contents.get("potion").isJsonPrimitive()
   &&java.util.Set.of("minecraft:healing","minecraft:strong_healing","minecraft:regeneration","minecraft:long_regeneration","minecraft:strong_regeneration").contains(contents.get("potion").getAsString());
 }
 static boolean fresh(long now,long issued,long expires,long status){return issued<=now&&now-issued<=10000&&now<=expires&&expires>=issued&&expires-issued<=10000&&status<=now&&now-status<=1000;}
 static boolean patient(float expected,float actual,boolean adult,boolean alive,double moved,double range){
  return Float.isFinite(expected)&&Float.isFinite(actual)&&expected>0&&expected<20&&actual>0&&actual<20&&Math.abs(expected-actual)<.01&&adult&&alive&&Double.isFinite(moved)&&moved<.2&&Double.isFinite(range)&&range<3.5;
 }
}
