package dev.twob2tkit;

import java.util.LinkedHashMap;
import java.util.Map;

/** Separate uncommitted strings from live configuration; external changes invalidate only their own fields. */
public final class UiDraft {
    public Map<String, String> values = new LinkedHashMap<>();
    public Map<String, String> baseline = new LinkedHashMap<>();
    public int scroll;
    public String query = "";
    public String read(String key, String current) {
        if (current == null) current = "";
        if (values == null) values = new LinkedHashMap<>();
        if (baseline == null) baseline = new LinkedHashMap<>();
        if (!current.equals(baseline.get(key))) { values.put(key, current); baseline.put(key, current); }
        String saved = values.get(key);
        return saved == null ? current : saved;
    }
    public void remember(String key, String value, String current) {
        if (current == null) current = "";
        if (baseline != null && baseline.containsKey(key) && !current.equals(baseline.get(key))) { read(key, current); return; }
        read(key, current); values.put(key, value == null ? "" : value);
    }
    public void committed(String key, String current) {
        read(key, current); values.put(key, current); baseline.put(key, current);
    }
    public static double number(String raw, String label, double min, double max, boolean integer) {
        final double value;
        try { value = Double.parseDouble(raw.trim()); }
        catch (RuntimeException error) { throw new IllegalArgumentException(label + "：请输入" + (integer ? "整数" : "数字")); }
        if (!Double.isFinite(value) || value < min || value > max || integer && value != Math.rint(value))
            throw new IllegalArgumentException(label + "：范围 " + min + "–" + max + (integer ? "，仅整数" : ""));
        return value;
    }
}
