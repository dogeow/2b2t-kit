package dev.twob2tkit.automation;

import java.util.IdentityHashMap;
import java.util.Map;
import com.google.gson.JsonNull;
import com.google.gson.JsonObject;

/** Pause only InstantRebreak while normal, owned material interactions control mining. */
public final class MaterialMiningLease implements AutoCloseable {
    public static final String MODULE="meteordevelopment.meteorclient.systems.modules.player.InstantRebreak";
    private static final Map<Object,Borrowed> observed=new IdentityHashMap<>();
    private static long generation;
    private static final class Borrowed {
        final Object module;
        final long generation;
        int references;
        boolean pausedByUs,ownershipLost,internalToggle;
        Borrowed(Object module){this.module=module;this.generation=++MaterialMiningLease.generation;}
    }
    private Borrowed state;
    private boolean closed;
    private String failure="";

    private MaterialMiningLease(Borrowed state){this.state=state;}
    public static MaterialMiningLease acquire(){
        try{
            Class<?> type=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
            Class<?> moduleType=Class.forName(MODULE);
            Object system=type.getMethod("get").invoke(null);
            Object selected=type.getMethod("get",Class.class).invoke(system,moduleType);
            if(selected==null)throw new IllegalStateException("Installed InstantRebreak is unavailable");
            return acquireModule(selected);
        }catch(ClassNotFoundException absent){return acquireModule(null);}
        catch(ReflectiveOperationException error){throw new IllegalStateException("Cannot pause installed InstantRebreak",error);}
    }
    /** Package-local seam: the only production selector above resolves the installed module. */
    static synchronized MaterialMiningLease acquireModule(Object selected){
        if(selected==null)return new MaterialMiningLease(null);
        Borrowed current=observed.get(selected);
        if(current!=null){
            if(!ready(current))throw new IllegalStateException("InstantRebreak was changed during material ownership");
            current.references++;return new MaterialMiningLease(current);
        }
        var next=new Borrowed(selected);next.references=1;observed.put(selected,next);
        try{
            selected.getClass().getMethod("isActive");selected.getClass().getMethod("toggle");
            if(active(selected)){
                next.pausedByUs=true;toggle(next);
                if(active(selected))throw new IllegalStateException("InstantRebreak pause was rejected");
            }
            // Confirm the replacement before revoking old restore ownership.
            for(Borrowed prior:observed.values())if(prior!=next)prior.ownershipLost=true;
            return new MaterialMiningLease(next);
        }catch(ReflectiveOperationException|RuntimeException failure){
            observed.remove(selected);
            // An uncertain toggle is never followed by another toggle.
            throw new IllegalStateException("Cannot confirm InstantRebreak pause",failure);
        }
    }
    /** Read only: current module observation remains available after a scope is released. */
    public static synchronized JsonObject snapshot(MaterialMiningLease lease,boolean currentScope){
        try{
            Class<?> type=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
            Object system=type.getMethod("get").invoke(null);
            Object selected=type.getMethod("get",Class.class).invoke(system,Class.forName(MODULE));
            if(selected==null)throw new IllegalStateException("Installed InstantRebreak is unavailable");
            return snapshot(lease,currentScope,selected);
        }catch(ClassNotFoundException absent){return snapshot(lease,currentScope,null);}
        catch(ReflectiveOperationException|RuntimeException unavailable){
            var result=snapshot(lease,currentScope,null);
            result.add("module_available",JsonNull.INSTANCE);result.add("module_active",JsonNull.INSTANCE);
            return result;
        }
    }
    static synchronized JsonObject snapshot(MaterialMiningLease lease,boolean currentScope,Object selected){
        var result=new JsonObject();
        result.addProperty("active_scope",lease!=null&&lease.packetBlocked(currentScope));
        result.addProperty("module_available",selected!=null);
        result.addProperty("generation",lease!=null&&lease.state!=null?lease.state.generation:generation);
        Boolean moduleActive=null;
        if(selected!=null)try{moduleActive=active(selected);}catch(ReflectiveOperationException|RuntimeException ignored){}
        if(moduleActive==null)result.add("module_active",JsonNull.INSTANCE);
        else result.addProperty("module_active",moduleActive);
        Borrowed held=lease==null?null:lease.state;
        result.addProperty("restore_owned",held!=null&&held.module==selected&&held.pausedByUs
            &&!held.ownershipLost&&Boolean.FALSE.equals(moduleActive));
        return result;
    }
    public boolean available(){return state!=null;}
    public String failure(){return failure;}
    public boolean packetBlocked(boolean currentScope){return !closed&&currentScope;}
    public synchronized boolean ready(){return !closed&&(state==null||ready(state));}
    private static boolean ready(Borrowed borrowed){
        if(borrowed.ownershipLost)return false;
        try{
            if(!active(borrowed.module))return true;
        }catch(ReflectiveOperationException|RuntimeException ignored){}
        borrowed.ownershipLost=true;return false;
    }
    /** Module.toggle HEAD observes even OFF-ON-OFF changes between ordinary snapshots. */
    public static synchronized void moduleToggleObserved(Object toggled){
        Borrowed borrowed=observed.get(toggled);
        if(borrowed!=null&&!borrowed.internalToggle)borrowed.ownershipLost=true;
    }
    @Override public void close(){
        synchronized(MaterialMiningLease.class){
            if(closed)return;closed=true;
            Borrowed borrowed=state;state=null;
            if(borrowed==null||--borrowed.references>0)return;
            try{
                if(borrowed.pausedByUs&&!borrowed.ownershipLost&&!active(borrowed.module)){
                    toggle(borrowed);
                    if(!active(borrowed.module))failure="InstantRebreak restoration was not confirmed";
                }
            }catch(ReflectiveOperationException|RuntimeException ignored){
                failure="InstantRebreak restoration could not be observed";
                // Preserve the observed state if restoration cannot be confirmed.
            }finally{observed.remove(borrowed.module);}
        }
    }
    private static boolean active(Object module)throws ReflectiveOperationException{
        Object value=module.getClass().getMethod("isActive").invoke(module);
        if(!(value instanceof Boolean))throw new IllegalStateException("Invalid InstantRebreak active state");
        return (Boolean)value;
    }
    private static void toggle(Borrowed borrowed)throws ReflectiveOperationException{
        borrowed.internalToggle=true;
        try{borrowed.module.getClass().getMethod("toggle").invoke(borrowed.module);}
        finally{borrowed.internalToggle=false;}
    }
}
