package dev.twob2tkit.runtime.engine;
import com.google.gson.JsonObject;
/** A fresh, explicit idle scope is required; an active construction/controller is never preempted. */
final class IdleThermalPolicy {
 private IdleThermalPolicy(){}
 static boolean yes(JsonObject j,String k){if(!j.has(k)||j.get(k).isJsonNull())return false;if(!j.get(k).isJsonPrimitive()||!j.getAsJsonPrimitive(k).isBoolean())throw new IllegalArgumentException("Boolean activity flag required");return j.get(k).getAsBoolean();}
 static boolean active(JsonObject j,String k){return j.has(k)&&j.get(k).isJsonObject()&&yes(j.getAsJsonObject(k),"active");}
 static String text(JsonObject j,String k){return j.has(k)&&j.get(k).isJsonPrimitive()&&j.getAsJsonPrimitive(k).isString()?j.get(k).getAsString():"";}
 static String server(String s){return s.toLowerCase(java.util.Locale.ROOT).replaceFirst(":25565$","");}
 static boolean idle(JsonObject s,long now,String server,String dimension,boolean requestPending){
  try{
   long age=now-s.get("time").getAsLong();
   if(!s.has("minor_thermal_work_protocol")||s.get("minor_thermal_work_protocol").getAsInt()!=1)return false;
   if(age< -1000||age>1500||requestPending||!yes(s,"connected")||!yes(s,"guard_armed")||!yes(s,"guard_pve_only")
      ||yes(s,"manual_movement")||!text(s,"screen").isEmpty()||!server(server).equals(server(text(s,"server")))
      ||!dimension.equals(text(s,"dimension"))||text(s,"world_session").isEmpty()||active(s,"safety_hold"))return false;
   for(String k:new String[]{"navigating","printing","borer_active","chopping","native_material_busy","air_return_active","fisher_active","planter_active","feeder_active"})if(yes(s,k))return false;
   String phase=text(s,"phase"),op=text(s,"op");
   if(phase.equals("running")&&!java.util.Set.of("snapshot","scan","scan_trees","projection_model","projection_audit","projection_list","map_audit").contains(op))return false;
   if(active(s,"build_job")||active(s,"projection_batch"))return false;
   var p=s.has("professional_printer")&&s.get("professional_printer").isJsonObject()?s.getAsJsonObject("professional_printer"):new JsonObject();
   if(yes(p,"owned")||yes(p,"printing_while_travelling")||yes(p,"enabled"))return false;
   if(s.has("supervision_lease")&&!s.get("supervision_lease").isJsonNull()){
    var lease=s.getAsJsonObject("supervision_lease");
    if(!text(lease,"kind").equals("parking")&&!yes(lease,"finish_waiting"))return false;
   }
   return true;
  }catch(RuntimeException invalid){return false;}
 }
 static boolean readOnly(String op){return java.util.Set.of("snapshot","scan","scan_trees","scan_snow_biomes","snow_seed_candidates","projection_model","projection_audit","projection_list","map_audit","decision_screenshot").contains(op);}
 static boolean pendingMutation(JsonObject r,JsonObject status,long now){
  try{return !readOnly(text(r,"op"))&&!text(r,"id").equals(text(status,"last_request"))
    &&text(r,"world_session").equals(text(status,"world_session"))&&r.has("expires_at")&&r.get("expires_at").getAsLong()>now;
  }catch(RuntimeException invalid){return true;}
 }
 static double rise(double feet,java.util.function.DoublePredicate clear){
  if(!Double.isFinite(feet))return Double.NaN;
  for(double delta:new double[]{3,2.5,2,1.5,1,.5})if(clear.test(delta))return feet+delta;
  return Double.NaN;
 }
}
