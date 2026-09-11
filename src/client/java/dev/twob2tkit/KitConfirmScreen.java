package dev.twob2tkit;

import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.gui.components.Button;
import net.minecraft.network.chat.Component;

/** Destructive actions always name their target; the initial focus is Cancel. */
public final class KitConfirmScreen extends KitHudScreen {
    private final String explanation; private final Runnable confirm;
    public KitConfirmScreen(Screen parent, String title, String explanation, Runnable confirm) {
        super(Component.literal(title), parent); this.explanation = explanation; this.confirm = confirm;
    }
    @Override protected void init() {
        var layout = UiPageLayout.of(width, height);
        centeredLabel(KitUi.fit(font, title.getString(), layout.width()), 24, 0xFFFF77);
        int y = 52; for (String line : KitUi.wrap(font, explanation, layout.width())) { centeredLabel(line, y, 0xDDDDDD); y += 12; }
        var cancel = addRenderableWidget(Button.builder(Component.literal("取消"), b -> onClose()).bounds(layout.footerButtonX(0, 2), layout.footer(), layout.footerButtonWidth(2), 20).build());
        addRenderableWidget(Button.builder(Component.literal("确认"), b -> { minecraft.setScreen(parent); confirm.run(); if (minecraft.screen == parent && parent != null) parent.resize(width, height); })
            .bounds(layout.footerButtonX(1, 2), layout.footer(), layout.footerButtonWidth(2), 20).build());
        setInitialFocus(cancel);
    }
    @Override protected boolean onEnterPressed() { return false; }
}
