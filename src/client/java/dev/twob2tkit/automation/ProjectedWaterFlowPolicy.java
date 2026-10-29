package dev.twob2tkit.automation;

import java.util.ArrayDeque;
import java.util.HashMap;

/** Conservative potential changes from one caged source; existing sources are not replaced. */
final class ProjectedWaterFlowPolicy {
    record Cell(int x,int y,int z){Cell offset(int x,int y,int z){return new Cell(this.x+x,this.y+y,this.z+z);}}
    record Bounds(Cell min,Cell max){
        boolean contains(Cell p){return p.x>=min.x&&p.x<=max.x&&p.y>=min.y&&p.y<=max.y&&p.z>=min.z&&p.z<=max.z;}
        boolean valid(){long x=(long)max.x-min.x+1,y=(long)max.y-min.y+1,z=(long)max.z-min.z+1;
            return x>=3&&x<=33&&z>=3&&z<=33&&y>=3&&y<=192&&x*y*z<=50000;}
    }
    enum Kind { AIR, FLOWING, SOURCE, BARRIER, UNSAFE, UNLOADED }
    interface World {Kind kind(Cell p);boolean living(Cell p);}
    record Step(Cell cell,int distance){}
    private ProjectedWaterFlowPolicy(){}
    static String rejection(World world,Bounds bounds,Cell source){
        if(bounds==null||!bounds.valid()||!bounds.contains(source))return "Invalid projected water bounds";
        var queue=new ArrayDeque<Step>();queue.add(new Step(source,0));var visited=new HashMap<Cell,Integer>();
        while(!queue.isEmpty()){
            var step=queue.removeFirst();var p=step.cell;
            if(!bounds.contains(p))return "Projected water may escape declared bounds";
            var kind=world.kind(p);
            if(kind==Kind.UNLOADED)return "Projected water needs server-loaded downstream cells";
            if(!p.equals(source)&&(kind==Kind.BARRIER||kind==Kind.SOURCE))continue;
            if(kind==Kind.UNSAFE||kind==Kind.BARRIER)return "Projected water may alter protected blocks";
            if(world.living(p))return "Living entity in projected water path";
            if(visited.getOrDefault(p,99)<=step.distance)continue;
            visited.put(p,step.distance);
            var below=p.offset(0,-1,0);
            if(!bounds.contains(below))return "Projected water may escape below declared bounds";
            var lower=world.kind(below);
            if(lower==Kind.UNLOADED)return "Projected water needs server-loaded downstream cells";
            if(lower==Kind.UNSAFE)return "Projected water may alter protected blocks below";
            // Air and weaker flowing water admit falling water. Horizontal flow
            // is only possible where downward flow is blocked. Falling resets
            // lateral reach, so every lower landing is checked independently.
            if(lower==Kind.AIR||lower==Kind.FLOWING){queue.add(new Step(below,0));continue;}
            if(step.distance>=7)continue;
            for(int[] d:new int[][]{{1,0},{-1,0},{0,1},{0,-1}})
                queue.add(new Step(p.offset(d[0],0,d[1]),step.distance+1));
        }
        return null;
    }
}
