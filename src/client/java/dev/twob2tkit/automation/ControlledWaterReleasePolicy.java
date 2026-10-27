package dev.twob2tkit.automation;

import java.util.ArrayDeque;
import java.util.HashSet;

/** Conservative, downward-only flood containment for one explicit retainer removal. */
final class ControlledWaterReleasePolicy {
    record Cell(int x,int y,int z) {
        Cell offset(int dx,int dy,int dz){return new Cell(x+dx,y+dy,z+dz);}
    }
    record Bounds(Cell min,Cell max) {
        boolean contains(Cell p){return p.x>=min.x&&p.x<=max.x&&p.y>=min.y&&p.y<=max.y&&p.z>=min.z&&p.z<=max.z;}
        boolean interior(Cell p){return p.x>min.x&&p.x<max.x&&p.y>min.y&&p.y<max.y&&p.z>min.z&&p.z<max.z;}
        boolean bounded(){
            long x=(long)max.x-min.x+1,y=(long)max.y-min.y+1,z=(long)max.z-min.z+1;
            return x>=3&&x<=32&&y>=3&&y<=16&&z>=3&&z<=32&&x*y*z<=4096;
        }
    }
    interface World {
        boolean loaded(Cell p);
        boolean barrier(Cell p);
        boolean air(Cell p);
        boolean water(Cell p);
        boolean otherFluid(Cell p);
        boolean container(Cell p);
        boolean living(Cell p);
    }
    private static final int[][] SIDES={{1,0,0},{-1,0,0},{0,0,1},{0,0,-1}};
    private ControlledWaterReleasePolicy(){}

    static String rejection(World world,Bounds bounds,Cell target,boolean ownedDryHealthy,boolean targetAllowed){
        if(!ownedDryHealthy)return "Controlled water release requires the current healthy dry material owner above the retainer";
        if(!targetAllowed)return "Controlled water release requires the exact dry cobblestone retainer";
        if(bounds==null||!bounds.bounded()||!bounds.interior(target))return "Controlled water release needs a bounded local enclosure";
        var queue=new ArrayDeque<Cell>();queue.add(target);boolean nextToWater=false;
        for(int[] d:SIDES){
            Cell p=target.offset(d[0],0,d[2]);
            if(world.otherFluid(p))return "Only plain water may touch a controlled retainer";
            if(world.water(p)){nextToWater=true;queue.add(p);}
        }
        Cell above=target.offset(0,1,0),below=target.offset(0,-1,0);
        if(world.otherFluid(above)||world.otherFluid(below))return "Only plain water may touch a controlled retainer";
        if(world.water(above)){nextToWater=true;queue.add(above);}
        if(!nextToWater)return "Controlled release needs adjacent plain water";
        var visited=new HashSet<Cell>();
        while(!queue.isEmpty()){
            Cell p=queue.removeFirst();if(!visited.add(p))continue;
            if(!bounds.contains(p))return "Released water could escape the declared enclosure";
            if(!world.loaded(p))return "Controlled release requires loaded server chunks throughout the enclosure";
            if(world.container(p))return "Containers remain protected from controlled water release";
            if(world.otherFluid(p))return "Controlled release cannot mix other fluids";
            if(!p.equals(target)&&world.barrier(p))continue;
            if(!p.equals(target)&&!world.air(p)&&!world.water(p))return "Controlled release cannot replace decorations or waterlog blocks";
            if(world.living(p))return "A living entity is inside the potential water path";
            queue.add(p.offset(0,-1,0));
            for(int[] d:SIDES)queue.add(p.offset(d[0],0,d[2]));
        }
        return null;
    }
}
