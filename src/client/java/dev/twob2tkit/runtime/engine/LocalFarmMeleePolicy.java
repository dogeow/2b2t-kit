package dev.twob2tkit.runtime.engine;
/** Explicit single-player loopback lab opt-in; never changes remote-server combat policy. */
final class LocalFarmMeleePolicy {
 static boolean attackDue(long now,int tick,long previousMs,int previousTick,float charge){return now-previousMs>=1500&&tick-previousTick>=30&&Float.isFinite(charge)&&charge>=.95f;}
 static boolean capturedTarget(String type,boolean alive,boolean passenger,boolean named){return "minecraft:zombified_piglin".equals(type)&&alive&&passenger&&!named;}
 static boolean playerAtStation(double x,double y,double z){return Double.isFinite(x+y+z)&&Math.abs(x-.5)<.3&&Math.abs(y-240.5)<.12&&Math.abs(z-.5)<.3;}
 static boolean targetAtStation(double x,double y,double z){return Double.isFinite(x+y+z)&&x>=.24&&x<=.76&&z>=.24&&z<=.76&&y>=243.9&&y<=244.2;}
 static boolean offerAllowed(String request,String blocked){return request!=null&&!request.isBlank()&&!request.equals(blocked);}
 static boolean allowed(String server,boolean scoped,boolean survival,double health,int food,boolean grounded,boolean flying,boolean manual,boolean screen,boolean sword,boolean fireAspect,boolean pose,boolean target){
  return "127.0.0.1:25579".equals(server)&&scoped&&survival&&Double.isFinite(health)&&health>=19&&food>=8&&grounded&&!flying&&!manual&&!screen&&sword&&!fireAspect&&pose&&target;
 }
}
