package dev.twob2tkit.automation;

import java.util.*;

/** Placement-only transaction. Only the newly prepared object may ever be removed. */
final class ProjectionLoadTransaction<P> {
    interface Access<P>{List<P> all();P selected();boolean enabled(P placement);String fingerprint(P placement);
        void add(P placement);void remove(P placement);void enable(P placement,boolean enabled);void select(P placement);}
    record Saved<P>(P placement,boolean enabled,String fingerprint){}
    private final Access<P> access;
    private final P added,oldSelection;
    private final List<Saved<P>> before;
    private List<Saved<P>> installed;
    private boolean applied;
    ProjectionLoadTransaction(Access<P> access,P added){
        this.access=access;this.added=Objects.requireNonNull(added);this.oldSelection=access.selected();
        var old=access.all();if(old.contains(added)||old.size()>64)throw new IllegalStateException("Too many placements or new placement is already registered");
        this.before=old.stream().map(p->new Saved<>(p,access.enabled(p),access.fingerprint(p))).toList();
    }
    List<Saved<P>> before(){return before;}
    P oldSelection(){return oldSelection;}
    void apply(){
        access.add(added);if(!access.all().contains(added))throw new IllegalStateException("Placement manager did not add new projection");
        for(var old:before)if(old.enabled)access.enable(old.placement,false);
        access.enable(added,true);access.select(added);
        if(access.selected()!=added||!access.enabled(added)||before.stream().anyMatch(old->access.enabled(old.placement)))throw new IllegalStateException("Projection activation could not be confirmed");
        installed=access.all().stream().map(p->new Saved<>(p,access.enabled(p),access.fingerprint(p))).toList();applied=true;
    }
    boolean unchanged(){
        if(!applied||access.selected()!=added||installed==null||!sameObjects(access.all(),installed.stream().map(Saved::placement).toList()))return false;
        return installed.stream().allMatch(s->access.enabled(s.placement)==s.enabled&&access.fingerprint(s.placement).equals(s.fingerprint));
    }
    void rollbackExplicit(){if(!unchanged())throw new IllegalStateException("Projection configuration changed since import; rollback will not overwrite later edits");if(!rollback())throw new IllegalStateException("Projection rollback could not restore the previous configuration");}
    boolean rollback(){
        boolean ok=true;
        try{if(access.all().contains(added))access.enable(added,false);}catch(RuntimeException e){ok=false;}
        for(var old:before)try{if(!access.all().contains(old.placement)){ok=false;continue;}access.enable(old.placement,old.enabled);}catch(RuntimeException e){ok=false;}
        try{access.select(oldSelection);}catch(RuntimeException e){ok=false;}
        try{if(access.all().contains(added))access.remove(added);}catch(RuntimeException e){ok=false;}
        applied=false;
        try{return ok&&access.selected()==oldSelection&&sameObjects(access.all(),before.stream().map(Saved::placement).toList())
            &&before.stream().allMatch(s->access.enabled(s.placement)==s.enabled&&access.fingerprint(s.placement).equals(s.fingerprint));}
        catch(RuntimeException e){return false;}
    }
    private static <P> boolean sameObjects(List<P> a,List<P> b){return a.size()==b.size()&&a.stream().allMatch(p->b.stream().anyMatch(q->p==q));}
}
