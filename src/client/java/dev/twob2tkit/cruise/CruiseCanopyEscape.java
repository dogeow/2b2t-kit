package dev.twob2tkit.cruise;

import java.util.*;
import java.util.function.BiPredicate;
import java.util.function.Predicate;

/** Short horizontal escape to a verified clear ascent column. Never digs blocks. */
public final class CruiseCanopyEscape {
    public record Offset(int x,int z){}
    private CruiseCanopyEscape(){}
    /** Meteor Velocity may multiply speed by 15 while sprinting; stay below the remaining gap. */
    public static double speed(double gap){
        if(!Double.isFinite(gap)||gap<0)throw new IllegalArgumentException("Finite canopy waypoint gap required");
        return Math.min(.02,gap/25);
    }
    public static List<Offset> find(int radius,BiPredicate<Offset,Offset> stepClear,Predicate<Offset> canRise){
        if(radius<1||radius>8)throw new IllegalArgumentException("Canopy escape radius must be 1..8");
        var start=new Offset(0,0);var queue=new ArrayDeque<Offset>();queue.add(start);
        var parents=new HashMap<Offset,Offset>();parents.put(start,null);
        int[][] directions={{0,-1},{1,0},{0,1},{-1,0}};
        while(!queue.isEmpty()){
            var p=queue.remove();
            if(canRise.test(p)){
                var path=new ArrayList<Offset>();
                for(var q=p;parents.get(q)!=null;q=parents.get(q))path.add(q);
                Collections.reverse(path);return List.copyOf(path);
            }
            for(var d:directions){
                var q=new Offset(p.x+d[0],p.z+d[1]);
                if(Math.abs(q.x)>radius||Math.abs(q.z)>radius||parents.containsKey(q)||!stepClear.test(p,q))continue;
                parents.put(q,p);queue.add(q);
            }
        }
        return List.of();
    }
}
