package dev.twob2tkit.automation;

import java.util.*;
import java.util.function.Predicate;

/** Main-thread, in-memory allowlist. Missing request files never delete an installed mask. */
public final class ProjectionBatchScope<P> {
    public static final int PROTOCOL=1, MAX_POSITIONS=2048;
    public record Owner(String lease,String task,String world,String projection) {
        public Owner {
            if(lease==null||lease.isBlank()||task==null||task.isBlank()||world==null||world.isBlank()||projection==null||projection.isBlank())
                throw new IllegalArgumentException("Projection batch requires a complete material owner");
        }
    }
    private Owner owner;
    private Set<P> positions=Set.of();
    private Integer minFeetY;
    public Integer minFeetY(){return minFeetY;}
    public boolean allowsFeet(double feet){return !active()||minFeetY==null||Double.isFinite(feet)&&feet>=minFeetY-.1;}
    public boolean allowsStation(int y){return !active()||minFeetY==null||y>=minFeetY;}
    public boolean active(){return owner!=null;}
    public int count(){return positions.size();}
    Set<P> positions(){return positions;} // Already immutable; completion cannot rewrite the mask.
    public Owner owner(){return owner;}
    public boolean current(Owner current){return owner!=null&&owner.equals(current);}
    public boolean allows(Owner current,P position){return owner==null||owner.equals(current)&&positions.contains(position);}
    public void set(Owner current,List<P> requested,Predicate<P> expectedNonAir){set(current,requested,expectedNonAir,null);}
    public void set(Owner current,List<P> requested,Predicate<P> expectedNonAir,Integer minimumFeetY){
        if(current==null)throw new IllegalArgumentException("Projection batch requires a material owner");
        if(owner!=null&&!owner.equals(current))throw new IllegalStateException("Projection batch belongs to another material scope");
        if(requested==null||requested.size()>MAX_POSITIONS)throw new IllegalArgumentException("Projection batch positions must contain 0..2048 coordinates");
        var checked=new LinkedHashSet<P>();
        for(P pos:requested){
            if(pos==null||!expectedNonAir.test(pos))throw new IllegalArgumentException("Projection batch coordinate is outside the selected non-air projection: "+pos);
            if(!checked.add(pos))throw new IllegalArgumentException("Projection batch has duplicate coordinates: "+pos);
        }
        positions=Set.copyOf(checked);minFeetY=minimumFeetY;owner=current; // Replace only after every coordinate passes.
    }
    public void clear(Owner current){
        if(owner!=null&&!owner.equals(current))throw new IllegalStateException("Projection batch belongs to another material scope");
        reset();
    }
    public void reset(){owner=null;positions=Set.of();minFeetY=null;}
    static int minimumFeet(double value,int minY,int maxY){
        if(!Double.isFinite(value)||value!=Math.rint(value)||value<minY||value>(long)maxY+3)throw new IllegalArgumentException("min_feet_y must be an integer within the selected projection minY..maxY+3");
        return (int)value;
    }
    static void request(boolean supported,boolean idle,boolean scoped,long requestRevision,long actualRevision,long lifetimeMillis){
        if(!supported)throw new IllegalStateException("Projection batch printer gate is unsupported; full client update required");
        if(!scoped||requestRevision!=actualRevision||lifetimeMillis<0||lifetimeMillis>15000)
            throw new IllegalStateException("Projection batch action expired or material scope changed");
        if(!idle)throw new IllegalStateException("Stop the owned projection and printer before changing the projection batch");
    }
}
