package dev.twob2tkit.runtime.engine;
import com.google.gson.*;import org.junit.jupiter.api.Test;import static org.junit.jupiter.api.Assertions.*;
class IdleThermalPolicyTest {
 JsonObject idle(){return JsonParser.parseString("{\"time\":10000,\"minor_thermal_work_protocol\":1,\"connected\":true,\"guard_armed\":true,\"guard_pve_only\":true,\"manual_movement\":false,\"screen\":\"\",\"server\":\"simpcraft.com:25565\",\"dimension\":\"minecraft:overworld\",\"world_session\":\"w\"}").getAsJsonObject();}
 boolean allowed(JsonObject s){return IdleThermalPolicy.idle(s,10500,"simpcraft.com","minecraft:overworld",false);}
 @Test void healthyIdleIsEligibleWithoutNeedingFood(){assertTrue(allowed(idle()));}
 @Test void activeMaterialControllerIsNotIdle(){var s=idle();s.add("supervision_lease",JsonParser.parseString("{\"kind\":\"materials\"}"));assertFalse(allowed(s));}
 @Test void endedTaskOrParkingCanRecoverWhileWaiting(){for(String lease:new String[]{"{\"kind\":\"materials\",\"finish_waiting\":true}","{\"kind\":\"parking\"}"}){var s=idle();s.add("supervision_lease",JsonParser.parseString(lease));assertTrue(allowed(s));}}
 @Test void constructionJobsAndOwnedPrinterSuppressIdleRise(){for(String key:new String[]{"build_job","projection_batch"}){var s=idle();s.add(key,JsonParser.parseString("{\"active\":true}"));assertFalse(allowed(s));}var s=idle();s.add("professional_printer",JsonParser.parseString("{\"owned\":true}"));assertFalse(allowed(s));}
 @Test void externalPrinterModeIsAlsoConstructionIntent(){var s=idle();s.add("professional_printer",JsonParser.parseString("{\"enabled\":true,\"owned\":false,\"ready_for_travel\":false}"));assertFalse(allowed(s));}
 @Test void navigationMiningAndOtherLiveActivitiesSuppressRise(){for(String key:new String[]{"navigating","printing","borer_active","chopping","native_material_busy","air_return_active","fisher_active","planter_active","feeder_active"}){var s=idle();s.addProperty(key,true);assertFalse(allowed(s),key);}}
 @Test void physicalHandoffInterfaceAndHealthLockWin(){for(String key:new String[]{"manual_movement"}){var s=idle();s.addProperty(key,true);assertFalse(allowed(s));}var s=idle();s.addProperty("screen","ChatScreen");assertFalse(allowed(s));s=idle();s.add("safety_hold",JsonParser.parseString("{\"active\":true}"));assertFalse(allowed(s));}
 @Test void staleForeignAndUnrecognizedSnapshotsDoNotTakeControl(){var s=idle();s.addProperty("time",8000);assertFalse(allowed(s));s=idle();s.addProperty("server","other");assertFalse(allowed(s));s=idle();s.addProperty("dimension","minecraft:the_nether");assertFalse(allowed(s));s=idle();s.remove("minor_thermal_work_protocol");assertFalse(allowed(s));s=idle();s.addProperty("navigating","false");assertFalse(allowed(s));}
 @Test void unleasedPlacementIsProtectedWhileReadOnlyScanDoesNotOwnMovement(){var s=idle();s.addProperty("phase","running");s.addProperty("op","interact");assertFalse(allowed(s));s.addProperty("op","scan");assertTrue(allowed(s));}
 @Test void pendingMutationPreventsStealingNewController(){assertFalse(IdleThermalPolicy.idle(idle(),10500,"simpcraft.com","minecraft:overworld",true));}
 @Test void queuedReadOnlyQueryDoesNotInterruptAnOngoingIdleAscent(){var s=idle();s.addProperty("last_request","old");for(String op:new String[]{"scan","snapshot","projection_model","projection_audit","scan_snow_biomes","decision_screenshot"}){var r=new JsonObject();r.addProperty("op",op);r.addProperty("id","new");r.addProperty("world_session","w");r.addProperty("expires_at",12000);assertFalse(IdleThermalPolicy.pendingMutation(r,s,10500),op);}}
 @Test void onlyFreshSameWorldUnacknowledgedMutationPreempts(){var s=idle();s.addProperty("last_request","old");var r=JsonParser.parseString("{\"id\":\"new\",\"op\":\"interact\",\"world_session\":\"w\",\"expires_at\":12000}").getAsJsonObject();assertTrue(IdleThermalPolicy.pendingMutation(r,s,10500));r.addProperty("world_session","other");assertFalse(IdleThermalPolicy.pendingMutation(r,s,10500));r.addProperty("world_session","w");r.addProperty("expires_at",10000);assertFalse(IdleThermalPolicy.pendingMutation(r,s,10500));r.addProperty("expires_at",12000);r.addProperty("id","old");assertFalse(IdleThermalPolicy.pendingMutation(r,s,10500));}
 @Test void ascentChoosesHighestLoadedClearStepWithoutForcingCeiling(){assertEquals(13,IdleThermalPolicy.rise(10,d->true));assertEquals(12,IdleThermalPolicy.rise(10,d->d<=2));assertTrue(Double.isNaN(IdleThermalPolicy.rise(10,d->false)));assertTrue(Double.isNaN(IdleThermalPolicy.rise(Double.NaN,d->true)));}
 @Test void candidateReallyInvokesIdleRecoveryAndReleasesItOnStop()throws Exception{var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("DefaultTunnelBorerEngine.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}boolean tick=false,stop=false;for(var m:node.methods)for(var i:m.instructions)if(i instanceof org.objectweb.asm.tree.MethodInsnNode c&&c.owner.endsWith("IdleThermalAscent")){tick|=m.name.equals("tickStandaloneGuard")&&c.name.equals("tick");stop|=m.name.equals("stop")&&c.name.equals("cancel");}assertTrue(tick&&stop);}
 @Test void recoveryNeverTeleportsOrAcknowledgesSafetyLocks()throws Exception{var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("IdleThermalAscent.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}for(var m:node.methods)for(var i:m.instructions)if(i instanceof org.objectweb.asm.tree.MethodInsnNode c){assertFalse(java.util.Set.of("setPos","teleportTo","setDeltaMovement","disconnect","confirmRecovery").contains(c.name),c.name);}}
 @Test void burningIdleRecoveryStopsBelowCollisionFreePowderSnow(){
  double feet=61.6;
  // Observed machine geometry: powder snow at65, solid ceiling at66, standing body1.8 high.
  // Powder snow has no ordinary standing collision but the26.2 server destroys it for a burning player.
  assertEquals(64.1,IdleThermalPolicy.rise(feet,d->feet+d+1.8<=66),.000001);
  assertEquals(63.1,IdleThermalPolicy.rise(feet,d->feet+d+1.8<=66
      &&(feet+d+1.8<=65||IdleThermalPolicy.safeAscentMaterial("minecraft:powder_snow",false))),.000001);
 }
 @Test void recoveryCannotForceItsSmallestStepThroughPowderSnow(){
  double feet=63;
  assertTrue(Double.isNaN(IdleThermalPolicy.rise(feet,d->feet+d+1.8<=65
      ||IdleThermalPolicy.safeAscentMaterial("minecraft:powder_snow",false))));
 }
 @Test void ordinarySnowAndLeavingCurrentFireKeepPriorMaterialBehavior(){
  assertTrue(IdleThermalPolicy.safeAscentMaterial("minecraft:air",false));
  assertTrue(IdleThermalPolicy.safeAscentMaterial("minecraft:snow",false));
  assertTrue(IdleThermalPolicy.safeAscentMaterial("minecraft:fire",false));
  assertFalse(IdleThermalPolicy.safeAscentMaterial("minecraft:air",true));
  assertFalse(IdleThermalPolicy.safeAscentMaterial(null,false));
 }
 @Test void actualAscentUsesMaterialEvidenceAlongsideLoadedCollisionChecks()throws Exception{
  var node=new org.objectweb.asm.tree.ClassNode();try(var in=getClass().getResourceAsStream("IdleThermalAscent.class")){assertNotNull(in);new org.objectweb.asm.ClassReader(in).accept(node,0);}
  var calls=new java.util.HashSet<String>();for(var m:node.methods)if(m.name.equals("clear"))for(var i:m.instructions)if(i instanceof org.objectweb.asm.tree.MethodInsnNode call)calls.add(call.name);
  assertTrue(calls.containsAll(java.util.Set.of("safeAscentMaterial","noCollision","isServerChunk","getFluidState")));
 }
}
