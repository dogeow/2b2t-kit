package dev.twob2tkit.automation;

import java.util.ArrayList;
import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Borrow only the installed Scaffold's exact settings; configure while inactive. */
public final class ScaffoldModuleLease implements AutoCloseable {
    public static final String MODULE="meteordevelopment.meteorclient.systems.modules.movement.Scaffold";
    private record Borrowed(String name,Object setting,Object original,Object written) {}
    private static ScaffoldModuleLease observedLease;
    private final Map<String,Borrowed> borrowed=new LinkedHashMap<>();
    private Object module;
    private boolean expectedActive,activeOwnershipLost,internalToggle;
    private String failure="";

    public boolean acquired(){return module!=null;}
    public String failure(){return failure;}
    /** Accepts the real Minecraft Item; reflection keeps Meteor an optional dependency. */
    public boolean acquire(Object expectedItem) {
        try{
            Class<?> blockItem=Class.forName("net.minecraft.world.item.BlockItem");
            if(!blockItem.isInstance(expectedItem))throw new IllegalArgumentException("Scaffold requires a BlockItem");
            Object block=blockItem.getMethod("getBlock").invoke(expectedItem);
            Class<?> modulesType=Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
            Object modules=modulesType.getMethod("get").invoke(null);
            Object selected=modulesType.getMethod("get",Class.class).invoke(modules,Class.forName(MODULE));
            return acquireModule(selected,block);
        }catch(ReflectiveOperationException|RuntimeException error){failure=error.getClass().getSimpleName();return false;}
    }
    public boolean acquire(String itemId) {
        try{
            if(itemId==null||!itemId.matches("minecraft:[a-z0-9_./-]+"))return false;
            Class<?> idType=Class.forName("net.minecraft.resources.Identifier");
            Object id=idType.getMethod("parse",String.class).invoke(null,itemId);
            Object registry=Class.forName("net.minecraft.core.registries.BuiltInRegistries").getField("ITEM").get(null);
            return acquire(registry.getClass().getMethod("getValue",idType).invoke(registry,id));
        }catch(ReflectiveOperationException|RuntimeException error){failure=error.getClass().getSimpleName();return false;}
    }
    /** Package-local test seam; production resolves the actual module and registered block above. */
    boolean acquireModule(Object selected,Object block) {
        if(module!=null||selected==null||block==null||observedLease!=null)return false;
        try{
            if(isActive(selected))return false;
            module=selected;expectedActive=false;activeOwnershipLost=false;failure="";
            Object mode=read(setting(module,"blocksFilter"));
            if(!(mode instanceof Enum<?>))throw new IllegalStateException("Scaffold filter is not an enum");
            Object whitelist=null;
            for(Object value:mode.getClass().getEnumConstants())if(((Enum<?>)value).name().equals("Whitelist"))whitelist=value;
            if(whitelist==null)throw new IllegalStateException("Scaffold Whitelist mode unavailable");
            borrow("blocks",List.of(block));borrow("blocksFilter",whitelist);
            borrow("airPlace",true);borrow("radius",0.0);borrow("aheadDistance",0.0);
            borrow("blocksPerTick",1);borrow("autoSwitch",true);borrow("fastTower",false);
            borrow("onlyOnClick",false);borrow("rotate",false);
            if(isActive(module))throw new IllegalStateException("Scaffold activated during configuration");
            observedLease=this;
            if(!settingsCurrent())throw new IllegalStateException("Scaffold configuration changed");
            return true;
        }catch(ReflectiveOperationException|RuntimeException error){failure=error.getClass().getSimpleName();close();return false;}
    }
    public boolean settingsCurrent() {
        if(module==null||activeOwnershipLost)return false;
        try{
            if(isActive(module)!=expectedActive){activeOwnershipLost=true;return false;}
            for(var entry:borrowed.values())if(setting(module,entry.name())!=entry.setting()
                    ||!Objects.equals(read(entry.setting()),entry.written()))return false;
            return true;
        }catch(ReflectiveOperationException|RuntimeException error){return false;}
    }
    public boolean activeOwned() {
        if(module==null||!expectedActive||activeOwnershipLost)return false;
        try{if(isActive(module))return true;activeOwnershipLost=true;}catch(ReflectiveOperationException|RuntimeException ignored){}
        return false;
    }
    public boolean enableOwned() {
        if(!settingsCurrent())return false;
        if(expectedActive)return true;
        expectedActive=true;
        try{toggle();return isActive(module)&&settingsCurrent();}
        catch(ReflectiveOperationException|RuntimeException error){failure=error.getClass().getSimpleName();disableOwned();return false;}
    }
    /** Immediate guard-busy stop, before any flight/height adjustment or settings restoration. */
    public boolean disableOwned() {
        if(module==null)return true;
        try{
            boolean current=isActive(module);
            if(activeOwnershipLost)return !current;
            if(current!=expectedActive){activeOwnershipLost=true;return !current;}
            if(!current)return true;
            toggle();boolean off=!isActive(module);if(off)expectedActive=false;return off;
        }catch(ReflectiveOperationException|RuntimeException error){failure=error.getClass().getSimpleName();return false;}
    }
    /** Called at Module.toggle HEAD; own calls are marked and external round trips are retained. */
    public static void moduleToggleObserved(Object toggledModule) {
        ScaffoldModuleLease lease=observedLease;
        if(lease!=null&&lease.module==toggledModule&&!lease.internalToggle)lease.activeOwnershipLost=true;
    }
    @Override public void close() {
        if(module==null)return;
        // A failed owned stop is not a release. Keep the narrowed settings and
        // ownership so the controller can retry; never ascend under active Scaffold.
        if(!disableOwned()&&!activeOwnershipLost)return;
        for(var entry:borrowed.values())try{
            if(setting(module,entry.name())==entry.setting()&&Objects.equals(read(entry.setting()),entry.written()))
                write(entry.setting(),copy(entry.original()));
        }catch(ReflectiveOperationException|RuntimeException ignored){}
        if(observedLease==this)observedLease=null;
        borrowed.clear();module=null;expectedActive=false;activeOwnershipLost=false;internalToggle=false;
    }
    private void borrow(String name,Object value)throws ReflectiveOperationException {
        Object option=setting(module,name),original=copy(read(option)),written=copy(value);
        borrowed.put(name,new Borrowed(name,option,original,copy(written)));
        if(!Objects.equals(original,written))write(option,written);
    }
    private void toggle()throws ReflectiveOperationException {
        internalToggle=true;
        try{module.getClass().getMethod("toggle").invoke(module);}finally{internalToggle=false;}
    }
    private static Object copy(Object value){
        if(value instanceof List<?> list)return new ArrayList<>(list);
        if(value instanceof Set<?> set)return new LinkedHashSet<>(set);
        if(value instanceof Map<?,?> map)return new LinkedHashMap<>(map);
        return value;
    }
    private static Object setting(Object selected,String name)throws ReflectiveOperationException {
        for(Class<?> type=selected.getClass();type!=null;type=type.getSuperclass())try{
            var field=type.getDeclaredField(name);field.setAccessible(true);return field.get(selected);
        }catch(NoSuchFieldException ignored){}
        throw new NoSuchFieldException(name);
    }
    private static Object read(Object option)throws ReflectiveOperationException{return option.getClass().getMethod("get").invoke(option);}
    private static void write(Object option,Object value)throws ReflectiveOperationException {
        Object result=option.getClass().getMethod("set",Object.class).invoke(option,value);
        if(Boolean.FALSE.equals(result)||!Objects.equals(read(option),value))throw new IllegalStateException("Scaffold rejected scoped setting");
    }
    private static boolean isActive(Object selected)throws ReflectiveOperationException{return Boolean.TRUE.equals(selected.getClass().getMethod("isActive").invoke(selected));}
}
