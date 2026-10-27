package dev.twob2tkit.chat;

import java.util.List;
import java.util.function.BooleanSupplier;
import java.util.function.Supplier;

import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

/** Compact settings panel, including at Minecraft's 320 x 240 minimum GUI size. */
public final class BilingualSettingsScreen extends Screen {
    private static final List<String> LANGUAGES = List.of("zh-Hans", "zh-Hant", "en", "ja", "ko");
    private final Screen parent;
    private final ModConfig config;
    private final Runnable save;
    private final Runnable checkHealth;
    private final Supplier<String> status;
    private int contentTop;
    private int contentWidth;
    private Button outgoingLanguageButton;

    public BilingualSettingsScreen(Screen parent, ModConfig config, Runnable save,
                                   Runnable checkHealth, Supplier<String> status) {
        super(text("title"));
        this.parent = parent;
        this.config = config;
        this.save = save;
        this.checkHealth = checkHealth;
        this.status = status;
    }

    @Override
    protected void init() {
        contentWidth = Math.min(304, width - 16);
        int left = (width - contentWidth) / 2;
        int half = (contentWidth - 6) / 2;
        int right = left + half + 6;
        contentTop = Math.max(32, height / 2 - 90);

        toggle(left, contentTop, half, "enabled", () -> config.enabled, () -> config.enabled = !config.enabled);
        addButton(right, contentTop, half, modeLabel(), "mode.tip", button -> {
            if (config.onDemandTranslation) config.bilingual = !config.bilingual;
            config.onDemandTranslation = !config.onDemandTranslation;
            button.setMessage(modeLabel());
            save.run();
        });
        addButton(left, contentTop + 22, half, languageLabel("target", config.targetLanguage), "target.tip", button -> {
            config.targetLanguage = nextLanguage(config.targetLanguage);
            button.setMessage(languageLabel("target", config.targetLanguage));
            save.run();
        });
        toggle(right, contentTop + 22, half, "system", () -> config.translateSystemMessages,
                () -> config.translateSystemMessages = !config.translateSystemMessages);
        toggle(left, contentTop + 44, half, "own", () -> config.translateOwnMessages,
                () -> config.translateOwnMessages = !config.translateOwnMessages);
        toggle(right, contentTop + 44, half, "outgoing", () -> config.outgoingTranslation, () -> {
            config.outgoingTranslation = !config.outgoingTranslation;
            outgoingLanguageButton.active = config.outgoingTranslation;
        });
        outgoingLanguageButton = addButton(left, contentTop + 66, half,
                languageLabel("outgoing_target", config.outgoingTargetLanguage), "outgoing_target.tip", button -> {
                    config.outgoingTargetLanguage = nextLanguage(config.outgoingTargetLanguage);
                    button.setMessage(languageLabel("outgoing_target", config.outgoingTargetLanguage));
                    save.run();
                });
        outgoingLanguageButton.active = config.outgoingTranslation;
        addButton(right, contentTop + 66, half, text("check"), "check.tip", button -> checkHealth.run());
        toggle(left, contentTop + 88, half, "anti_spam", () -> config.antiSpamEnabled,
                () -> config.antiSpamEnabled = !config.antiSpamEnabled);
        toggle(right, contentTop + 88, half, "ignore", () -> config.sendIgnoreCommand,
                () -> config.sendIgnoreCommand = !config.sendIgnoreCommand);

        addButton(left, contentTop + 110, half, text("start"), "start.tip", button -> BilingualClient.startHelper());
        addButton(right, contentTop + 110, half, text("open_helper"), "open_helper.tip", button -> BilingualClient.openHelper());

        addRenderableWidget(Button.builder(text("done"), button -> onClose())
                .bounds(width / 2 - 70, Math.min(height - 27, contentTop + 181), 140, 20).build());
    }

    private void toggle(int x, int y, int size, String key, BooleanSupplier value, Runnable change) {
        addButton(x, y, size, toggleLabel(key, value.getAsBoolean()), key + ".tip", button -> {
            change.run();
            button.setMessage(toggleLabel(key, value.getAsBoolean()));
            save.run();
            if (key.equals("enabled") && config.enabled) BilingualClient.startHelper();
        });
    }

    private Button addButton(int x, int y, int size, Component label, String tooltip, Button.OnPress onPress) {
        return addRenderableWidget(Button.builder(label, onPress).bounds(x, y, size, 20)
                .tooltip(Tooltip.create(text(tooltip))).build());
    }

    @Override
    public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float partialTick) {
        graphics.fill(0, 0, width, height, 0xED101721);
        graphics.centeredText(font, title, width / 2, contentTop - 29, 0xFFFFFFFF);
        graphics.centeredText(font, text("subtitle"), width / 2, contentTop - 15, 0xFFB7C8D9);
        String health = status.get();
        if (health == null || health.isBlank()) {
            health = text("unknown").getString();
        }
        String connection = text("status", health).getString();
        graphics.centeredText(font, fit(connection), width / 2, contentTop + 134, 0xFFBFE4D4);
        graphics.centeredText(font, "127.0.0.1:" + config.helperPort, width / 2, contentTop + 147, 0xFF8EA6BC);
        graphics.centeredText(font, text(config.outgoingTranslation ? "outgoing_notice" : "local_notice"),
                width / 2, contentTop + 160, 0xFFCDD5DE);
        super.extractRenderState(graphics, mouseX, mouseY, partialTick);
    }

    private String fit(String value) {
        if (font.width(value) <= contentWidth) {
            return value;
        }
        return font.plainSubstrByWidth(value, contentWidth - font.width("…")) + "…";
    }

    @Override
    public void onClose() {
        save.run();
        minecraft.setScreenAndShow(parent);
    }

    @Override
    public boolean isPauseScreen() {
        return false;
    }

    private Component modeLabel() {
        return text(config.onDemandTranslation ? (config.bilingual ? "mode.manual_bilingual" : "mode.manual_translation")
                : (config.bilingual ? "mode.bilingual" : "mode.translation"));
    }

    private static Component toggleLabel(String key, boolean value) {
        return text(key, text(value ? "on" : "off"));
    }

    private static Component languageLabel(String key, String language) {
        return text(key, LANGUAGES.contains(language) ? text("language." + language) : Component.literal(language));
    }

    private static String nextLanguage(String current) {
        return LANGUAGES.get((LANGUAGES.indexOf(current) + 1) % LANGUAGES.size());
    }

    private static Component text(String key, Object... arguments) {
        return Component.translatable("mcbilingual.settings." + key, arguments);
    }
}
