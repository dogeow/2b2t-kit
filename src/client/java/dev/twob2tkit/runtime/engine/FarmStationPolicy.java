package dev.twob2tkit.runtime.engine;
final class FarmStationPolicy {
 static boolean scope(String server,String requested,boolean nether,boolean survival,long now,long expires,long stateAge,boolean sameWorld,boolean sameInput,boolean ownedRevision,double health,int food,boolean manual,boolean screen,boolean locked,boolean autoLog){return "simpcraft.com".equals(server)&&server.equals(requested)&&nether&&survival&&expires>=now&&expires-now<=1800000&&stateAge>=0&&stateAge<2500&&sameWorld&&sameInput&&ownedRevision&&Double.isFinite(health)&&health>=19&&food>=18&&!manual&&!screen&&!locked&&autoLog;}
 static boolean station(double x,double y,double z,double sx,double sy,double sz,boolean grounded,boolean flying){return Double.isFinite(x+y+z+sx+sy+sz)&&Math.abs(x-sx)<.4&&Math.abs(y-sy)<.15&&Math.abs(z-sz)<.4&&grounded&&!flying;}
 static boolean lure(boolean stationed,boolean nearby,boolean otherPlayer,boolean visible,double distance,int arrows,int spent,int budget){return stationed&&!nearby&&!otherPlayer&&visible&&Double.isFinite(distance)&&distance>=8&&distance<=48&&arrows>0&&spent<Math.min(4,budget)&&budget>0;}
 static boolean incoming(boolean own,double vx,double vy,double vz,double dx,double dy,double dz){return !own&&Double.isFinite(vx+vy+vz+dx+dy+dz)&&vx*dx+vy*dy+vz*dz>0;}
 static boolean released(int peak,boolean using){return released(peak,using,peak);}
 static boolean released(int peak,boolean using,int current){return peak>=18&&(!using||current+5<peak);}
 private FarmStationPolicy(){}
}
