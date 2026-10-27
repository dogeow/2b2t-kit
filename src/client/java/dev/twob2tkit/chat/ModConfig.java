package dev.twob2tkit.chat;

import com.google.gson.Gson;
import com.google.gson.GsonBuilder;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;

/** Client-only preferences. A damaged existing file is never silently replaced. */
public final class ModConfig {
    private static final Gson GSON = new GsonBuilder().setPrettyPrinting().create();
    private static final long MAX_CONFIG_BYTES = 64 * 1024;

    public boolean enabled = true;
    public boolean onDemandTranslation = false;
    public boolean bilingual = true;
    public boolean translateSystemMessages = true;
    public boolean translateOwnMessages = false;
    public boolean outgoingTranslation = false;
    public boolean antiSpamEnabled = true;
    public int spamRepeatThreshold = 3;
    public int spamWindowSeconds = 15;
    public boolean sendIgnoreCommand = true;
    public String targetLanguage = "zh-Hans";
    public String sourceLanguage = "auto";
    public String outgoingTargetLanguage = "en";
    public int helperPort = 8765;

    /** The caller can log this warning without exposing the contents of the file. */
    public transient String loadWarning;
    private transient Path protectedCorruptPath;

    public static ModConfig load(Path path) {
        ModConfig config = new ModConfig();
        if (!Files.exists(path)) {
            return config;
        }
        try {
            if (Files.size(path) > MAX_CONFIG_BYTES) {
                throw new IllegalArgumentException("configuration file is too large");
            }
            JsonElement parsed = JsonParser.parseString(Files.readString(path, StandardCharsets.UTF_8));
            if (!parsed.isJsonObject()) {
                throw new IllegalArgumentException("configuration must be a JSON object");
            }
            JsonObject json = parsed.getAsJsonObject();
            config.enabled = booleanValue(json, "enabled", config.enabled);
            config.onDemandTranslation = booleanValue(json, "onDemandTranslation", config.onDemandTranslation);
            config.bilingual = booleanValue(json, "bilingual", config.bilingual);
            config.translateSystemMessages = booleanValue(json, "translateSystemMessages", config.translateSystemMessages);
            config.translateOwnMessages = booleanValue(json, "translateOwnMessages", config.translateOwnMessages);
            config.outgoingTranslation = booleanValue(json, "outgoingTranslation", config.outgoingTranslation);
            config.antiSpamEnabled = booleanValue(json, "antiSpamEnabled", config.antiSpamEnabled);
            config.sendIgnoreCommand = booleanValue(json, "sendIgnoreCommand", config.sendIgnoreCommand);
            config.spamRepeatThreshold = integerValue(json, "spamRepeatThreshold", config.spamRepeatThreshold, 2, 100);
            config.spamWindowSeconds = integerValue(json, "spamWindowSeconds", config.spamWindowSeconds, 1, 3600);
            config.targetLanguage = languageValue(json, "targetLanguage", config.targetLanguage, false);
            config.sourceLanguage = languageValue(json, "sourceLanguage", config.sourceLanguage, true);
            config.outgoingTargetLanguage = languageValue(json, "outgoingTargetLanguage", config.outgoingTargetLanguage, false);
            config.helperPort = integerValue(json, "helperPort", config.helperPort, 1, 65535);
            return config;
        } catch (IOException | RuntimeException error) {
            ModConfig defaults = new ModConfig();
            defaults.protectedCorruptPath = path.toAbsolutePath().normalize();
            defaults.loadWarning = "Could not read bilingual chat preferences; using defaults. "
                    + "The existing configuration is preserved. Fix or remove it before saving: "
                    + defaults.protectedCorruptPath + " (" + error.getClass().getSimpleName() + ")";
            return defaults;
        }
    }

    public void save(Path path) throws IOException {
        Path destination = path.toAbsolutePath().normalize();
        if (destination.equals(protectedCorruptPath) && Files.exists(destination)) {
            throw new IOException("The invalid configuration is preserved. Fix or remove " + destination
                    + " and restart Minecraft before saving preferences.");
        }
        Files.createDirectories(destination.getParent());
        Path temporary = Files.createTempFile(destination.getParent(), ".mcbilingual-", ".tmp");
        try {
            Files.writeString(temporary, GSON.toJson(this) + System.lineSeparator(), StandardCharsets.UTF_8);
            try {
                Files.move(temporary, destination, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING);
            } catch (AtomicMoveNotSupportedException error) {
                Files.move(temporary, destination, StandardCopyOption.REPLACE_EXISTING);
            }
            protectedCorruptPath = null;
            loadWarning = null;
        } finally {
            Files.deleteIfExists(temporary);
        }
    }

    private static boolean booleanValue(JsonObject json, String key, boolean defaultValue) {
        if (!json.has(key)) {
            return defaultValue;
        }
        JsonElement value = json.get(key);
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isBoolean()) {
            throw new IllegalArgumentException(key + " must be a boolean");
        }
        return value.getAsBoolean();
    }

    private static String languageValue(JsonObject json, String key, String defaultValue, boolean allowAuto) {
        if (!json.has(key)) {
            return defaultValue;
        }
        JsonElement value = json.get(key);
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()) {
            throw new IllegalArgumentException(key + " must be a language tag");
        }
        String language = value.getAsString().trim();
        if ((!allowAuto && language.equalsIgnoreCase("auto"))
                || !language.matches("[A-Za-z]{2,8}(?:-[A-Za-z0-9]{1,8}){0,4}")) {
            throw new IllegalArgumentException(key + " must be a language tag");
        }
        return language;
    }

    private static int integerValue(JsonObject json, String key, int defaultValue, int minimum, int maximum) {
        if (!json.has(key)) {
            return defaultValue;
        }
        JsonElement value = json.get(key);
        if (!value.isJsonPrimitive() || !value.getAsJsonPrimitive().isNumber()) {
            throw new IllegalArgumentException(key + " must be an integer");
        }
        int number = value.getAsBigDecimal().intValueExact();
        if (number < minimum || number > maximum) {
            throw new IllegalArgumentException(key + " must be between " + minimum + " and " + maximum);
        }
        return number;
    }
}
