package dev.twob2tkit.ui.components;

import dev.twob2tkit.KitUi;
import java.util.function.Consumer;
import net.minecraft.client.gui.Font;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.network.chat.Component;

/** Shared search and clear controls; clearing keeps typing focus in the text field. */
public record SearchBar(EditBox field, Button clear) {
    public static SearchBar create(Font font, int x, int y, int width, String label, String hint,
                                   String query, Consumer<String> changed, Consumer<EditBox> focus) {
        String initial = query == null ? "" : query;
        EditBox field = KitUi.field(font, x, y, width - 44, label, initial, 80);
        field.setHint(Component.literal(hint));
        Button clear = Button.builder(Component.literal("清空"), button -> {
            field.setValue("");
            focus.accept(field);
        }).bounds(x + width - 40, y, 40, 20).build();
        clear.active = !initial.isEmpty();
        field.setResponder(value -> {
            clear.active = !value.isEmpty();
            changed.accept(value);
        });
        return new SearchBar(field, clear);
    }
}
