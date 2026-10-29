package dev.twob2tkit.automation;

import java.util.*;

/** Select an existing object. This interface deliberately cannot add or delete placements. */
final class ProjectionSelectionTransaction<P> {
    interface Access<P>{List<P> all();P selected();boolean enabled(P p);String fingerprint(P p);
        String contentFingerprint(P p);void enable(P p,boolean value);void select(P p);}
    record Saved<P>(P object,boolean enabled,String fingerprint,String content){}
    private final Access<P> access;
    private final List<Saved<P>> before;
    private final P target,previous;
    ProjectionSelectionTransaction(Access<P> access,P target){
        this.access=access;this.target=Objects.requireNonNull(target);previous=access.selected();
        var all=access.all();
        if(all.size()>1024||all.stream().noneMatch(p->p==target)||previous!=null&&all.stream().noneMatch(p->p==previous))
            throw new IllegalStateException("Selection target or previous selection is not registered");
        before=all.stream().map(p->new Saved<>(p,access.enabled(p),access.fingerprint(p),access.contentFingerprint(p))).toList();
    }
    private boolean sameContent(){
        var all=access.all();if(all.size()!=before.size())return false;
        for(int i=0;i<all.size();i++)if(all.get(i)!=before.get(i).object||!access.contentFingerprint(all.get(i)).equals(before.get(i).content))return false;
        return true;
    }
    void apply(){
        if(!sameContent()||access.selected()!=previous||before.stream().anyMatch(p->access.enabled(p.object)!=p.enabled))
            throw new IllegalStateException("Projection registry changed before selection");
        for(var p:before)if(p.enabled!=(p.object==target))access.enable(p.object,p.object==target);
        access.select(target);
        if(!sameContent()||access.selected()!=target||before.stream().anyMatch(p->access.enabled(p.object)!=(p.object==target)))
            throw new IllegalStateException("Existing projection selection could not be verified");
    }
    boolean rollback(){
        if(!sameContent())return false; // Never restore over a moved or newly added user placement.
        boolean ok=true;
        for(var p:before)try{if(access.enabled(p.object)!=p.enabled)access.enable(p.object,p.enabled);}catch(RuntimeException e){ok=false;}
        try{access.select(previous);}catch(RuntimeException e){ok=false;}
        return ok&&sameContent()&&access.selected()==previous
            &&before.stream().allMatch(p->access.fingerprint(p.object).equals(p.fingerprint));
    }
}
