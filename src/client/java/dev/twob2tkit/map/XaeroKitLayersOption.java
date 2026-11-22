package dev.twob2tkit.map;

import dev.twob2tkit.KitMapLayers;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.network.chat.Component;
import xaero.map.gui.IRightClickableElement;
import xaero.map.gui.dropdown.rightclick.RightClickOption;

public final class XaeroKitLayersOption extends RightClickOption {
    public enum Action {
        LAYERS("Kit 地图图层与物资搜索"), NEXT_BATCH("Kit 查看下一批预加载"),
        SAVE_PLACE("Kit 保存角色当前位置"), WORKSITE("Kit 标记投影施工入口／补料点");

        final String label;
        Action(String label) { this.label = label; }
    }

    private final KitMapLayers layers;
    private final Action action;
    private final ClientLevel level;
    private final int x, z;

    public XaeroKitLayersOption(Object target, int index, KitMapLayers layers, Action action, int x, int z, boolean sameDimension) {
        super("twob2tkit.layers." + action.name(), index, (IRightClickableElement)target);
        this.layers = layers;
        this.action = action;
        this.x = x;
        this.z = z;
        level = Minecraft.getInstance().level;
        setActive(level != null && Minecraft.getInstance().player != null
            && (action != Action.WORKSITE || sameDimension));
    }

    @Override public Component getDisplayName() { return Component.literal(action.label); }

    @Override public void onAction(Screen screen) {
        Minecraft client = Minecraft.getInstance();
        if (client.level != level || client.player == null) return;
        switch (action) {
            case LAYERS -> layers.open(screen);
            case NEXT_BATCH -> layers.openScenery(screen, client);
            case SAVE_PLACE -> layers.savePlace(screen, client);
            case WORKSITE -> layers.worksite(screen, client, x, z);
        }
    }
}
