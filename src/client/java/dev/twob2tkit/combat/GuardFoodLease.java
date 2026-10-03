package dev.twob2tkit.combat;

import com.google.gson.*;
import net.minecraft.client.Minecraft;
import java.nio.file.*;
import java.util.*;

/** Observe normal AutoEat settings, borrowing only the settings needed for owned health recovery. */
public final class GuardFoodLease {
    private static final String AUTO_EAT = "meteordevelopment.meteorclient.systems.modules.player.AutoEat";
    private record Borrowed(String name, Object setting, Object original, Object written) {}
    private static final List<Borrowed> borrowed = new ArrayList<>();
    private static Path backupPath;
    private static boolean recoveryAttempted;

    private GuardFoodLease() {}
    private static Path path(Minecraft c) {
        return c.gameDirectory.toPath().resolve("config/twob2tkit/guard-food-settings.bak.json");
    }
    private static Object module() throws Exception {
        var type = Class.forName("meteordevelopment.meteorclient.systems.modules.Modules");
        return type.getMethod("get", Class.class).invoke(type.getMethod("get").invoke(null), Class.forName(AUTO_EAT));
    }
    private static Object setting(Object module, String name) throws Exception {
        var field = module.getClass().getDeclaredField(name);
        field.setAccessible(true);
        return field.get(module);
    }
    private static Object read(Object setting) throws Exception {
        return setting.getClass().getMethod("get").invoke(setting);
    }
    private static void write(Object setting, Object value) throws Exception {
        Object accepted = setting.getClass().getMethod("set", Object.class).invoke(setting, value);
        if (Boolean.FALSE.equals(accepted) || !Objects.equals(read(setting), value))
            throw new IllegalStateException("AutoEat rejected the scoped setting");
    }
    private static Object decoded(JsonElement value, Object current) {
        if (current instanceof Boolean) return value.getAsBoolean();
        if (current instanceof Integer) return value.getAsInt();
        if (current instanceof Double) return value.getAsDouble();
        if (current instanceof Enum<?> e)
            for (Object option : e.getDeclaringClass().getEnumConstants())
                if (((Enum<?>) option).name().equals(value.getAsString())) return option;
        throw new IllegalStateException("Unsupported AutoEat setting type");
    }

    public static void recover(Minecraft c) {
        if (!borrowed.isEmpty() || !Files.exists(path(c))) return;
        try { recover(module(), path(c)); }
        catch (Exception e) { throw new IllegalStateException("Cannot restore prior AutoEat settings", e); }
    }
    static void recover(Object module, Path path) {
        if (!borrowed.isEmpty() || !Files.exists(path)) return;
        try {
            var record = JsonParser.parseString(Files.readString(path)).getAsJsonObject();
            for (var entry : record.entrySet()) {
                Object option = setting(module, entry.getKey()), current = read(option);
                var values = entry.getValue().getAsJsonObject();
                Object previous = decoded(values.get("original"), current);
                Object written = decoded(values.get("written"), current);
                if (Objects.equals(current, written)) write(option, previous);
            }
            Files.delete(path);
            if (path.equals(backupPath)) backupPath = null;
        } catch (Exception e) { throw new IllegalStateException("Cannot restore prior AutoEat settings", e); }
    }

    /** Normal work must retain all user thresholds and food choices. */
    public static void acquire(Minecraft c) {
        if (!borrowed.isEmpty()) return;
        try { acquire(module(), path(c)); }
        catch (Exception e) { throw new IllegalStateException("Cannot observe AutoEat for unattended work", e); }
    }
    static void acquire(Object module, Path path) {
        if (!borrowed.isEmpty()) return;
        recover(module, path);
        if (module == null) throw new IllegalStateException("Meteor AutoEat unavailable");
    }

    /** The caller supplies ownership of PvE recovery; full health or loss of that ownership releases the lease. */
    public static void tickRecovery(Minecraft c, boolean ownedRecoveryNeeded) {
        boolean needed = c.player != null && needsRecovery(ownedRecoveryNeeded,
            c.player.getHealth(), c.player.getMaxHealth());
        if (!enterRecovery(needed)) return;
        try { acquireRecovery(module(), path(c)); }
        catch (Exception e) { throw new IllegalStateException("Cannot prepare AutoEat for health recovery", e); }
    }
    static void tickRecovery(Object module, Path path, boolean ownedRecoveryNeeded, float health, float maxHealth) {
        if (!enterRecovery(needsRecovery(ownedRecoveryNeeded, health, maxHealth))) return;
        try { acquireRecovery(module, path); }
        catch (Exception e) { throw new IllegalStateException("Cannot prepare AutoEat for health recovery", e); }
    }
    private static boolean needsRecovery(boolean ownedRecoveryNeeded, float health, float maxHealth) {
        return ownedRecoveryNeeded && Float.isFinite(health) && Float.isFinite(maxHealth)
            && health > 0 && health < maxHealth;
    }
    private static boolean enterRecovery(boolean needed) {
        if (!needed) {
            if (recoveryAttempted || !borrowed.isEmpty() || backupPath != null) release();
            return false;
        }
        if (recoveryAttempted) return false;
        recoveryAttempted = true;
        return true;
    }
    private static void acquireRecovery(Object module, Path path) throws Exception {
        // A failed previous release must be resolved before creating another backup.
        restoreBorrowed();
        recover(module, path);
        if (module == null) throw new IllegalStateException("Meteor AutoEat unavailable");
        var proposed = new ArrayList<Borrowed>();
        Object mode = setting(module, "thresholdMode"), originalMode = read(mode);
        if (!(originalMode instanceof Enum<?>)) throw new IllegalStateException("Unsupported AutoEat threshold mode");
        add(proposed, "thresholdMode", mode, originalMode, decoded(new JsonPrimitive("Any"), originalMode));
        Object hunger = setting(module, "hungerThreshold"), originalHunger = read(hunger);
        Object search = setting(module, "searchInventory"), originalSearch = read(search);
        if (!(originalHunger instanceof Integer) || !(originalSearch instanceof Boolean))
            throw new IllegalStateException("Unsupported AutoEat recovery settings");
        add(proposed, "hungerThreshold", hunger, originalHunger, 19);
        add(proposed, "searchInventory", search, originalSearch, true);
        if (proposed.isEmpty()) return;

        // The complete original/written record reaches disk atomically before the first setting is changed.
        save(proposed, path);
        backupPath = path;
        borrowed.addAll(proposed);
        try {
            for (var entry : proposed) write(entry.setting(), entry.written());
        } catch (Exception failure) {
            try { restoreBorrowed(); }
            catch (Exception rollbackFailure) { failure.addSuppressed(rollbackFailure); }
            throw failure;
        }
    }
    private static void add(List<Borrowed> values, String name, Object setting, Object original, Object written) {
        if (!Objects.equals(original, written)) values.add(new Borrowed(name, setting, original, written));
    }
    private static void save(List<Borrowed> values, Path path) throws Exception {
        Path parent = path.toAbsolutePath().getParent();
        Files.createDirectories(parent);
        var record = new JsonObject();
        var gson = new Gson();
        for (var entry : values) {
            var value = new JsonObject();
            value.add("original", gson.toJsonTree(entry.original()));
            value.add("written", gson.toJsonTree(entry.written()));
            record.add(entry.name(), value);
        }
        Path temporary = Files.createTempFile(parent, path.getFileName().toString(), ".tmp");
        try {
            Files.writeString(temporary, record.toString());
            Files.move(temporary, path, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
        } finally { Files.deleteIfExists(temporary); }
    }

    public static void release() {
        recoveryAttempted = false;
        try { restoreBorrowed(); }
        catch (Exception e) { throw new IllegalStateException("Cannot restore borrowed AutoEat settings", e); }
    }
    private static void restoreBorrowed() throws Exception {
        Exception failure = null;
        for (var iterator = borrowed.iterator(); iterator.hasNext();) {
            var entry = iterator.next();
            try {
                if (Objects.equals(read(entry.setting()), entry.written())) write(entry.setting(), entry.original());
                iterator.remove();
            } catch (Exception e) {
                if (failure == null) failure = e;
                else failure.addSuppressed(e);
            }
        }
        if (borrowed.isEmpty() && backupPath != null) {
            try { Files.deleteIfExists(backupPath); backupPath = null; }
            catch (Exception e) {
                if (failure == null) failure = e;
                else failure.addSuppressed(e);
            }
        }
        if (failure != null) throw failure;
    }

    public static JsonObject snapshot() {
        var result = new JsonObject();
        result.addProperty("owned", !borrowed.isEmpty());
        try {
            Object m = module();
            for (String name : List.of("thresholdMode", "healthThreshold", "hungerThreshold", "searchInventory"))
                result.add(name, new Gson().toJsonTree(read(setting(m, name))));
        } catch (Exception e) { result.addProperty("available", false); }
        return result;
    }
}
