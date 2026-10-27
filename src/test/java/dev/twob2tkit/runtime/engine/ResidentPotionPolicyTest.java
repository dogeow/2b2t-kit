package dev.twob2tkit.runtime.engine;
import com.google.gson.JsonParser;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;
class ResidentPotionPolicyTest {
 @Test void harmful_unknown_and_mixed_effects_cannot_be_therapeutic(){
  for(String value:new String[]{"{}","{\"potion\":\"minecraft:poison\"}","{\"potion\":\"minecraft:healing\",\"custom_effects\":[]}","{\"potion\":\"mod:healing\"}"})assertFalse(ResidentPotionPolicy.therapeutic(JsonParser.parseString(value).getAsJsonObject()));
  assertTrue(ResidentPotionPolicy.therapeutic(JsonParser.parseString("{\"potion\":\"minecraft:regeneration\"}").getAsJsonObject()));
 }
 @Test void stale_future_and_excessive_requests_are_rejected(){
  assertTrue(ResidentPotionPolicy.fresh(20000,19500,25000,19900));
  assertFalse(ResidentPotionPolicy.fresh(20000,21000,25000,19900));assertFalse(ResidentPotionPolicy.fresh(20000,19500,19000,19900));
  assertFalse(ResidentPotionPolicy.fresh(20000,19500,35000,19900));assertFalse(ResidentPotionPolicy.fresh(20000,19500,25000,18000));
 }
 @Test void only_same_living_injured_adult_in_range_is_accepted(){
  assertTrue(ResidentPotionPolicy.patient(11.39f,11.39f,true,true,.01,2));
  assertFalse(ResidentPotionPolicy.patient(11.39f,10,true,true,.01,2));assertFalse(ResidentPotionPolicy.patient(20,20,true,true,.01,2));
  assertFalse(ResidentPotionPolicy.patient(11.39f,11.39f,false,true,.01,2));assertFalse(ResidentPotionPolicy.patient(11.39f,11.39f,true,false,.01,2));
  assertFalse(ResidentPotionPolicy.patient(11.39f,11.39f,true,true,.3,2));assertFalse(ResidentPotionPolicy.patient(11.39f,11.39f,true,true,.01,4));
 }
}
