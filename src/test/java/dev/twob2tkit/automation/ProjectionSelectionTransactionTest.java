package dev.twob2tkit.automation;

import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

class ProjectionSelectionTransactionTest {
    static final class Placement {boolean enabled;String content="locked/origin/rotation/regions";}
    static final class Manager implements ProjectionSelectionTransaction.Access<Placement>{
        final List<Placement> all=new ArrayList<>();Placement selected;int writes,failAt=-1;
        public List<Placement> all(){return new ArrayList<>(all);}public Placement selected(){return selected;}
        public boolean enabled(Placement p){return p.enabled;}public String fingerprint(Placement p){return p.content+":"+p.enabled;}
        public String contentFingerprint(Placement p){return p.content;}
        void write(){if(++writes==failAt)throw new IllegalStateException("selection failure");}
        public void enable(Placement p,boolean enabled){p.enabled=enabled;write();}
        public void select(Placement p){selected=p;write();}
    }
    Manager manager(){var m=new Manager();for(int i=0;i<65;i++)m.all.add(new Placement());m.selected=m.all.getFirst();m.selected.enabled=true;return m;}
    @Test void registryAboveImportLimitCanSelectWithoutAddingRemovingOrMovingAnything(){
        var m=manager();var objects=new ArrayList<>(m.all);var target=m.all.getLast();
        var t=new ProjectionSelectionTransaction<>(m,target);t.apply();
        assertEquals(objects,m.all);assertSame(target,m.selected);assertTrue(target.enabled);
        assertEquals(1,m.all.stream().filter(p->p.enabled).count());assertTrue(m.all.stream().allMatch(p->p.content.equals("locked/origin/rotation/regions")));
        assertTrue(t.rollback());assertSame(objects.getFirst(),m.selected);assertTrue(m.selected.enabled);
    }
    @Test void everyPartialEnableOrSelectFailureRestoresTheExactOldObjects(){
        for(int i=1;i<=3;i++){
            var m=manager();var objects=new ArrayList<>(m.all);var old=m.selected;m.failAt=i;
            var t=new ProjectionSelectionTransaction<>(m,m.all.getLast());assertThrows(IllegalStateException.class,t::apply);
            assertTrue(t.rollback());assertEquals(objects,m.all);assertSame(old,m.selected);assertTrue(old.enabled);
            assertEquals(1,m.all.stream().filter(p->p.enabled).count());
        }
    }
    @Test void changedRegistryDoesNotGetOverwrittenByStaleSelection(){
        var m=manager();var t=new ProjectionSelectionTransaction<>(m,m.all.getLast());m.all.add(new Placement());
        assertThrows(IllegalStateException.class,t::apply);assertEquals(0,m.writes);assertFalse(t.rollback());assertEquals(66,m.all.size());
    }
    @Test void laterTransformsAreNeverOverwrittenByRollback(){
        var m=manager();var t=new ProjectionSelectionTransaction<>(m,m.all.getLast());t.apply();
        m.all.getFirst().content="user moved placement";int writes=m.writes;assertFalse(t.rollback());
        assertEquals(writes,m.writes);assertEquals("user moved placement",m.all.getFirst().content);
    }
    @Test void unregisteredTargetAndOversizedRegistryFailWithoutMutation(){
        var m=manager();assertThrows(IllegalStateException.class,()->new ProjectionSelectionTransaction<>(m,new Placement()));
        for(int i=m.all.size();i<1025;i++)m.all.add(new Placement());
        assertThrows(IllegalStateException.class,()->new ProjectionSelectionTransaction<>(m,m.all.getFirst()));assertEquals(0,m.writes);
    }
    @Test void selectingCurrentOnlyEnabledObjectDoesNotToggleIt(){
        var m=manager();new ProjectionSelectionTransaction<>(m,m.selected).apply();assertEquals(1,m.writes);assertTrue(m.selected.enabled);
    }
}
