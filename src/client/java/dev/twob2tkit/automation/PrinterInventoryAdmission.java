package dev.twob2tkit.automation;

import com.google.gson.JsonObject;
import net.fabricmc.loader.api.FabricLoader;

/** Validate on the client thread before a material session can stop an external printer. */
public final class PrinterInventoryAdmission {
    private PrinterInventoryAdmission() {}
    private static boolean requested(JsonObject request) {
        if(!request.has("printer_idle_required"))return false;
        var value=request.get("printer_idle_required");
        if(!value.isJsonPrimitive()||!value.getAsJsonPrimitive().isBoolean())throw new IllegalArgumentException("printer_idle_required must be boolean");
        return value.getAsBoolean();
    }
    public static void requireIdle(JsonObject request) {
        if(!requested(request))return;
        requireIdle(request,FabricLoader.getInstance().isModLoaded("litematica_printer"),ProfessionalPrinter.status());
    }
    static void requireIdle(JsonObject request,boolean installed,JsonObject printer) {
        if(!requested(request)||!installed)return;
        if(printer==null||!knownBoolean(printer,"enabled")||!knownBoolean(printer,"owned"))throw new IllegalStateException("Printer mode state unavailable; no material session acquired");
        if(printer.get("owned").getAsBoolean())throw new IllegalStateException("Another task owns the printer; no material session acquired");
        if(printer.get("enabled").getAsBoolean())throw new IllegalStateException("External Litematica Printer is enabled; no material session acquired");
    }
    private static boolean knownBoolean(JsonObject state,String key) {
        return state.has(key)&&state.get(key).isJsonPrimitive()&&state.get(key).getAsJsonPrimitive().isBoolean();
    }
}
