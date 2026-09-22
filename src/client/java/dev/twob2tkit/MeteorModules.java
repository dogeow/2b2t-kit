package dev.twob2tkit;

/** 反射打开已装的 Meteor 模块。找不到模组就当没装，不报错。 */
public final class MeteorModules {
	/** KillAura 全类名。 */
	public static final String KILL_AURA = "meteordevelopment.meteorclient.systems.modules.combat.KillAura";
	/** AutoLog 全类名。 */
	public static final String AUTO_LOG = "meteordevelopment.meteorclient.systems.modules.combat.AutoLog";
	/** Flight 全类名。 */
	public static final String FLIGHT = "meteordevelopment.meteorclient.systems.modules.movement.Flight";

	private MeteorModules() {
	}

	/** 该 Meteor 模块是否已开启。 */
	public static boolean isActive(String className) {
		Object module = module(className);
		if (module == null) return false;
		try {
			return Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));
		} catch (ReflectiveOperationException ignored) {
			return false;
		}
	}

	/**
	 * 尝试打开模块；已开则不动。
	 * @return true 表示这一拍新打开了
	 */
	public static boolean enable(String className) {
		Object module = module(className);
		if (module == null) return false;
		try {
			if (Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module))) return false;
			try {
				module.getClass().getMethod("enable").invoke(module);
			} catch (NoSuchMethodException ignored) {
				module.getClass().getMethod("toggle").invoke(module);
			}
			return Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));
		} catch (ReflectiveOperationException ignored) {
			return false;
		}
	}
	public static boolean disable(String className) {
		Object module = module(className);
		if (module == null) return false;
		try {
			if (!Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module))) return false;
			module.getClass().getMethod("toggle").invoke(module);
			return !Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));
		} catch (ReflectiveOperationException ignored) { return false; }
	}

    /** Requested unattended PvE: never include players, livestock or neutral piglins/endermen. */
    public static boolean enablePveAura(){
        Object aura=module(KILL_AURA);if(aura==null)return false;
        try{
            var targets=new java.util.HashSet<net.minecraft.world.entity.EntityType<?>>();
            for(var type:net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE){
                String id=net.minecraft.core.registries.BuiltInRegistries.ENTITY_TYPE.getKey(type).toString();
                if(dev.twob2tkit.combat.PveAuraPolicy.allowed(id))targets.add(type);
            }
            if(targets.isEmpty())throw new IllegalStateException("No hostile targets resolved");
            set(aura,"entities",targets);set(aura,"onlyOnClick",false);set(aura,"onlyOnLook",false);
            set(aura,"autoSwitch",true);set(aura,"swapBack",true);set(aura,"pauseOnUse",true);
            set(aura,"ignorePassive",true);set(aura,"ignoreTamed",true);
            enable(KILL_AURA);return isActive(KILL_AURA);
        }catch(ReflectiveOperationException e){throw new IllegalStateException("Cannot verify Meteor PvE settings",e);}
    }
    private static void set(Object module,String name,Object value)throws ReflectiveOperationException{
        var f=module.getClass().getDeclaredField(name);f.setAccessible(true);Object setting=f.get(module);
        Object current=setting.getClass().getMethod("get").invoke(setting);
        if(!java.util.Objects.equals(current,value))setting.getClass().getMethod("set",Object.class).invoke(setting,value);
        if(!java.util.Objects.equals(setting.getClass().getMethod("get").invoke(setting),value))throw new IllegalStateException("Meteor rejected "+name);
    }
	/** 从 Modules 单例按类名取模块实例；未装 Meteor 返回 null。 */
	private static Object module(String className) {
		try {
			Class<?> modulesClz = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
			Object modules = modulesClz.getMethod("get").invoke(null);
			if (modules == null) return null;
			Class<?> moduleClz = Class.forName(className);
			return modulesClz.getMethod("get", Class.class).invoke(modules, moduleClz);
		} catch (Throwable ignored) {
			return null;
		}
	}
}
