package dev.twob2tkit.automation;
import org.junit.jupiter.api.Test;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;
class ProjectionLoadTransactionTest {
    static final class Placement {final String name;boolean enabled;String transform="original";Placement(String name,boolean enabled){this.name=name;this.enabled=enabled;}}
    static final class Manager implements ProjectionLoadTransaction.Access<Placement>{
        final List<Placement> all=new ArrayList<>();Placement selected;int failAfter=-1,operations;boolean failRemove;
        public List<Placement> all(){return new ArrayList<>(all);}public Placement selected(){return selected;}
        public boolean enabled(Placement p){return p.enabled;}public String fingerprint(Placement p){return p.name+"/"+p.enabled+"/"+p.transform;}
        void step(){if(++operations==failAfter)throw new IllegalStateException("Injected partial manager failure");}
        public void add(Placement p){all.add(p);if(selected==null)selected=p;step();}
        public void remove(Placement p){if(failRemove)throw new IllegalStateException("remove failed");all.remove(p);step();}
        public void enable(Placement p,boolean value){p.enabled=value;step();}public void select(Placement p){selected=p;step();}
    }
    private Manager old(){var m=new Manager();m.all.add(new Placement("locked-house",true));m.all.add(new Placement("saved-starship",false));m.selected=m.all.getFirst();return m;}
    @Test void loadOnlyDisablesOldPlacementsAndRollbackRestoresExactSelection(){
        var manager=old();var oldSelected=manager.selected;var saved=new ArrayList<>(manager.all);var fresh=new Placement("courtyard",false);
        var tx=new ProjectionLoadTransaction<>(manager,fresh);tx.apply();
        assertEquals(3,manager.all.size());assertSame(fresh,manager.selected);assertTrue(fresh.enabled);assertFalse(oldSelected.enabled);
        assertEquals("original",oldSelected.transform);assertTrue(tx.unchanged());tx.rollbackExplicit();
        assertEquals(saved,manager.all);assertSame(oldSelected,manager.selected);assertTrue(oldSelected.enabled);assertFalse(saved.get(1).enabled);
    }
    @Test void failureAfterEachMutationRestoresOldStateAndRemovesOnlyNewPlacement(){
        for(int failure=1;failure<=4;failure++){
            var manager=old();var before=new ArrayList<>(manager.all);var selection=manager.selected;manager.failAfter=failure;
            var fresh=new Placement("courtyard",false);var tx=new ProjectionLoadTransaction<>(manager,fresh);
            assertThrows(IllegalStateException.class,tx::apply);assertTrue(tx.rollback());
            assertEquals(before,manager.all);assertSame(selection,manager.selected);assertTrue(before.getFirst().enabled);assertFalse(before.get(1).enabled);assertFalse(manager.all.contains(fresh));
        }
    }
    @Test void laterUserEditsOrNewPlacementsPreventDestructiveUndo(){
        var manager=old();var fresh=new Placement("courtyard",false);var tx=new ProjectionLoadTransaction<>(manager,fresh);tx.apply();
        manager.all.getFirst().transform="user moved house";
        assertThrows(IllegalStateException.class,tx::rollbackExplicit);assertEquals("user moved house",manager.all.getFirst().transform);assertSame(fresh,manager.selected);
        manager.all.getFirst().transform="original";manager.all.add(new Placement("user-new",true));
        assertThrows(IllegalStateException.class,tx::rollbackExplicit);assertEquals(4,manager.all.size());
    }
    @Test void rollbackFailureIsExplicitAndNeverDeletesOldPlacements(){
        var manager=old();var old=new ArrayList<>(manager.all);var tx=new ProjectionLoadTransaction<>(manager,new Placement("courtyard",false));tx.apply();manager.failRemove=true;
        assertFalse(tx.rollback());assertTrue(manager.all.containsAll(old));assertTrue(old.getFirst().enabled);
    }
    @Test void emptyManagerRollbackRestoresNoSelection(){
        var manager=new Manager();var tx=new ProjectionLoadTransaction<>(manager,new Placement("courtyard",false));tx.apply();assertTrue(tx.rollback());assertTrue(manager.all.isEmpty());assertNull(manager.selected);
    }
    @Test void oversizedPlacementListFailsBeforeAnyMutation(){
        var manager=new Manager();for(int i=0;i<65;i++)manager.all.add(new Placement("old"+i,false));
        assertThrows(IllegalStateException.class,()->new ProjectionLoadTransaction<>(manager,new Placement("new",false)));assertEquals(0,manager.operations);
    }
}
