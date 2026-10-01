package dev.twob2tkit.combat;

import java.util.LinkedHashMap;
import java.util.LinkedHashSet;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** Temporarily arm Meteor for a detected melee threat while retaining the user's settings. */
public final class MeteorCombatTargetLease {
    private record Borrowed(Object setting, Object original, Object written) {}
    private final Map<String, Borrowed> borrowed = new LinkedHashMap<>();
    private Object aura;
    private Object target;
    private boolean enabledByUs;

    public boolean active() { return aura != null; }

    /** True only when Meteor accepted the target and can attack without held mining input. */
    public boolean prepare(Object module, Object entityType) {
        if (module == null || entityType == null) return false;
        if (aura != null && aura != module) release();
        if (aura != null && !ready()) return false; // Respect changes made during the lease.
        try {
            aura = module;
            Object entities = setting(module, "entities");
            Object current = read(entities);
            if (!(current instanceof Set<?> selected)) throw new IllegalStateException("Invalid Meteor entities setting");
            Set<Object> targets = new LinkedHashSet<>(selected);
            targets.add(entityType);
            borrow("entities", targets);
            borrow("onlyOnClick", false);
            borrow("onlyOnLook", false);
            borrow("autoSwitch", true);
            borrow("swapBack", true);
            // Meteor 26.1.2-42 filters non-aggressive Piglins here, even when their type is selected.
            borrow("ignorePassive", true);
            target = entityType;
            if (!isActive(module)) {
                module.getClass().getMethod("toggle").invoke(module);
                enabledByUs = isActive(module);
            }
            if (!ready()) throw new IllegalStateException("Meteor melee preparation was rejected");
            return true;
        } catch (ReflectiveOperationException | RuntimeException e) {
            release();
            return false;
        }
    }

    /** Verify the lease without rewriting user changes or re-enabling a manually disabled module. */
    public boolean ready() {
        if (aura == null) return false;
        try {
            if (!isActive(aura)) return false;
            Object selected = read(setting(aura, "entities"));
            if (!(selected instanceof Set<?> types) || !types.contains(target)) return false;
            for (Borrowed entry : borrowed.values()) if (!Objects.equals(read(entry.setting()), entry.written())) return false;
            return true;
        } catch (ReflectiveOperationException | RuntimeException e) {
            return false;
        }
    }

    /** Restore only settings still equal to our writes; preserve later user edits. */
    public void release() {
        if (aura == null) return;
        // Disable before restoring swapBack, so Meteor can return the borrowed weapon slot.
        if (enabledByUs) try {
            if (isActive(aura)) aura.getClass().getMethod("toggle").invoke(aura);
        } catch (ReflectiveOperationException | RuntimeException ignored) {}
        for (Borrowed entry : borrowed.values()) try {
            if (Objects.equals(read(entry.setting()), entry.written())) write(entry.setting(), copy(entry.original()));
        } catch (ReflectiveOperationException | RuntimeException ignored) {}
        borrowed.clear();
        aura = null;
        target = null;
        enabledByUs = false;
    }

    private void borrow(String name, Object value) throws ReflectiveOperationException {
        Object option = setting(aura, name);
        Object current = read(option);
        Borrowed previous = borrowed.get(name);
        Object original = previous == null ? copy(current) : previous.original();
        Object written = copy(value);
        if (Objects.equals(current, value)) {
            // Observe even unchanged controls, so later user edits are not overwritten by prepare.
            if (previous == null) borrowed.put(name, new Borrowed(option, original, copy(written)));
            return;
        }
        // Record before writing, so partially accepted writes can also be restored on failure.
        borrowed.put(name, new Borrowed(option, original, copy(written)));
        write(option, written);
    }
    private static Object copy(Object value) {
        return value instanceof Set<?> set ? new LinkedHashSet<>(set) : value;
    }
    private static Object setting(Object module, String name) throws ReflectiveOperationException {
        var field = module.getClass().getDeclaredField(name);
        field.setAccessible(true);
        return field.get(module);
    }
    private static Object read(Object option) throws ReflectiveOperationException {
        return option.getClass().getMethod("get").invoke(option);
    }
    private static void write(Object option, Object value) throws ReflectiveOperationException {
        Object accepted = option.getClass().getMethod("set", Object.class).invoke(option, value);
        if (Boolean.FALSE.equals(accepted) || !Objects.equals(read(option), value))
            throw new IllegalStateException("Meteor rejected the scoped setting");
    }
    private static boolean isActive(Object module) throws ReflectiveOperationException {
        return Boolean.TRUE.equals(module.getClass().getMethod("isActive").invoke(module));
    }
}
