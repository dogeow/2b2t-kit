package dev.twob2tkit.runtime.engine;

import java.util.List;

/** Choose a finite gaze away from witnessed eye positions; no target or combat state changes. */
final class GuardEndermanGazePolicy {
    private GuardEndermanGazePolicy() {}
    static double[] direction(double[] eye,List<double[]> targets) {
        if(!finite(eye)||targets==null||targets.isEmpty())return null;
        var vectors=new java.util.ArrayList<double[]>();
        for(var target:targets){
            if(!finite(target))return null;
            double x=target[0]-eye[0],y=target[1]-eye[1],z=target[2]-eye[2];
            double length=Math.hypot(Math.hypot(x,y),z);
            if(!Double.isFinite(length)||length<1e-5)return null;
            vectors.add(new double[]{x/length,y/length,z/length});
        }
        double best=Double.POSITIVE_INFINITY;double[] result=null;
        for(int x=-1;x<=1;x++)for(int y=-1;y<=1;y++)for(int z=-1;z<=1;z++){
            double length=Math.sqrt(x*x+y*y+z*z);if(length==0)continue;
            double worst=-1;
            for(var v:vectors)worst=Math.max(worst,(x*v[0]+y*v[1]+z*v[2])/length);
            if(worst<best-1e-12){best=worst;result=new double[]{x/length,y/length,z/length};}
        }
        return result;
    }
    private static boolean finite(double[] v){
        return v!=null&&v.length==3&&Double.isFinite(v[0])&&Double.isFinite(v[1])&&Double.isFinite(v[2]);
    }
}
