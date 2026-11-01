package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class ConstructionThermalBucketPolicyTest {
 @Test void constructionHeatAllowsSmallLossButNeverGenericBucketOrCombat(){
  assertTrue(ConstructionThermalBucketPolicy.allow(true,true,true,19.84448,false));
  assertFalse(ConstructionThermalBucketPolicy.allow(false,true,true,20,false));
  assertFalse(ConstructionThermalBucketPolicy.allow(true,false,true,20,false));
  assertFalse(ConstructionThermalBucketPolicy.allow(true,true,false,20,false));
  assertFalse(ConstructionThermalBucketPolicy.allow(true,true,true,20,true));
  for(double hp:new double[]{18.99,0,Double.NaN,Double.POSITIVE_INFINITY})
   assertFalse(ConstructionThermalBucketPolicy.allow(true,true,true,hp,false));
 }
 @Test void realMobAttackSurvivesLaterFireAndFutureTimestampFailsClosed(){
  assertTrue(ConstructionThermalBucketPolicy.recentMobAttack(true,1000,900));
  assertTrue(ConstructionThermalBucketPolicy.recentMobAttack(true,1000,1001));
  assertFalse(ConstructionThermalBucketPolicy.recentMobAttack(true,1000,899));
  assertFalse(ConstructionThermalBucketPolicy.recentMobAttack(false,1000,1000));
 }
 @Test void optionsDefaultOffRequireBooleanAndOriginalSourceMode(){
  var r=new JsonObject();assertFalse(ProjectedModelWaterGuard.option(r,"model_water_minor_thermal"));
  r.addProperty("model_water_minor_thermal",true);
  assertThrows(IllegalArgumentException.class,()->ProjectedModelWaterGuard.option(r,"model_water_minor_thermal"));
  r.addProperty("projected_model_water_source",true);assertTrue(ProjectedModelWaterGuard.option(r,"model_water_minor_thermal"));
  r.addProperty("model_water_minor_thermal","true");assertThrows(IllegalArgumentException.class,()->ProjectedModelWaterGuard.option(r,"model_water_minor_thermal"));
  r.addProperty("model_water_remote_calm_creeper",1);assertThrows(IllegalArgumentException.class,()->ProjectedModelWaterGuard.option(r,"model_water_remote_calm_creeper"));
 }
 @Test void remoteCreeperProofStillRejectsChargedVisibleIgnitingNearAndUnloaded(){
  assertTrue(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,true,false,false,true,100,64));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(false,true,false,false,true,100,64));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,false,false,false,true,100,64));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,true,true,false,true,100,64));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,true,false,true,true,100,64));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,true,false,false,false,100,64));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,true,false,false,true,64,64));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,true,false,false,true,100,49));
  assertFalse(ProjectedFlowCorrectionGuard.remoteCalmCreeper(true,true,false,false,true,Double.NaN,64));
 }
 @Test void nearbyZombieRemainsBlockedEvenWithConstructionOptions(){
  assertFalse(ModelWaterThreatPolicy.permit("minecraft:zombie",true,false,16,false));
  assertFalse(ProjectedFlowCorrectionGuard.separatedThreat("minecraft:zombie",true,false,16,2));
 }
}
