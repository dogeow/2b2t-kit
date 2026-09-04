package dev.twob2tkit;

import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.GuiGraphicsExtractor;
import net.minecraft.client.gui.components.Button;
import net.minecraft.client.gui.components.ContainerObjectSelectionList;
import net.minecraft.client.gui.components.EditBox;
import net.minecraft.client.gui.components.Tooltip;
import net.minecraft.client.gui.components.events.GuiEventListener;
import net.minecraft.client.gui.narration.NarratableEntry;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.network.chat.Component;

import java.util.List;

/** 玩家白名单：添加/移除附近玩家保护例外。 */
final class KitTrustedPlayersScreen extends KitHudScreen {
	private final KitConfig config;
	private EditBox playerName;
	private PlayerList list;
	private String draftName = "";

	KitTrustedPlayersScreen(Screen parent, KitConfig config) {
		super(Component.literal("2b2t-kit 玩家白名单"), parent);
		this.config = config;
	}

	/** 布置输入框、名单列表与返回。 */
	@Override
	protected void init() {
		int left = panelLeft(320);
		if (playerName != null) draftName = playerName.getValue();
		playerName = addRenderableWidget(KitUi.field(this.font, left, bodyTop(44), 196, "玩家名", draftName, 16));
		playerName.setHint(Component.literal("输入玩家名后回车添加"));
		addRenderableWidget(Button.builder(Component.literal("添加"), button -> addPlayer())
			.bounds(left + 204, bodyTop(44), 56, 20)
			.tooltip(Tooltip.create(Component.literal("白名单中的玩家不会触发附近玩家离线")))
			.build());
		addRenderableWidget(Button.builder(Component.literal("移除"), button -> removeTyped())
			.bounds(left + 264, bodyTop(44), 56, 20).build());

		int listTop = bodyTop(86);
		int listHeight = Math.max(48, contentBottom() - 28 - listTop);
		list = addRenderableWidget(new PlayerList(this.minecraft, this.width, listHeight, listTop));
		list.populate();

		addRenderableWidget(Button.builder(Component.literal("返回"), button -> onClose())
			.bounds(this.width / 2 - 75, contentBottom(), 150, 20).build());
		setInitialFocus(playerName);
	}

	/** 画标题与空名单提示。 */
	@Override
	public void extractRenderState(GuiGraphicsExtractor graphics, int mouseX, int mouseY, float delta) {
		super.extractRenderState(graphics, mouseX, mouseY, delta);
		int center = this.width / 2;
		KitUi.centered(graphics, this.font, this.title.getString(), center, headerY(12), 0xFFFFFF);
		KitUi.centered(graphics, this.font, "点击名单可填回输入框，右侧按钮直接移除", center, headerY(26), 0xA0A0A0);
		if (!notice.isEmpty()) KitUi.centered(graphics, this.font, notice, center, bodyTop(72), noticeColor);
		if (config.trustedPlayers.isEmpty()) {
			KitUi.centered(graphics, this.font, "白名单为空", center, bodyTop(110), 0xA0A0A0);
		}
	}

	/** 回车添加当前输入名。 */
	@Override
	protected boolean onEnterPressed() {
		addPlayer();
		return true;
	}

	/** 校验并加入白名单。 */
	private void addPlayer() {
		String name = playerName.getValue().trim();
		if (!validName(name)) return;
		if (config.addTrusted(name)) showNotice("已添加：" + name, 0x55FF55);
		else showNotice("已经在白名单中：" + name, 0xFFFF55);
		playerName.setValue("");
		list.populate();
	}

	/** 移除输入框中的名字。 */
	private void removeTyped() {
		String name = playerName.getValue().trim();
		if (!validName(name)) return;
		removeName(name);
	}

	/** 按名移除并刷新列表。 */
	private void removeName(String name) {
		if (config.removeTrusted(name)) showNotice("已移除：" + name, 0x55FF55);
		else showNotice("白名单中没有：" + name, 0xFFFF55);
		playerName.setValue("");
		list.populate();
	}

	/** 校验 Minecraft 玩家名格式。 */
	private boolean validName(String name) {
		if (!KitUi.isMinecraftName(name)) {
			showNotice("请输入 1-16 位、不含空格的玩家名", 0xFF5555);
			return false;
		}
		return true;
	}

	/** 白名单可滚动列表。 */
	private final class PlayerList extends ContainerObjectSelectionList<PlayerList.Entry> {
		private PlayerList(Minecraft minecraft, int width, int height, int y) {
			super(minecraft, width, height, y, 24);
			this.centerListVertically = false;
		}

		/** 按配置重建条目。 */
		private void populate() {
			clearEntries();
			for (String name : config.trustedPlayers) addEntry(new Entry(name));
		}

		/** 行宽不超过 320。 */
		@Override
		public int getRowWidth() {
			return Math.min(320, this.width - 24);
		}

		/** 单行：填入与移除。 */
		private final class Entry extends ContainerObjectSelectionList.Entry<Entry> {
			private final String name;
			private final Button load;
			private final Button remove;

			private Entry(String name) {
				this.name = name;
				this.load = Button.builder(Component.literal("填入"), button -> {
					playerName.setValue(name);
					setInitialFocus(playerName);
				}).bounds(0, 0, 44, 20).build();
				this.remove = Button.builder(Component.literal("移除"), button -> removeName(name)).bounds(0, 0, 44, 20).build();
			}

			/** 画玩家名与填入/移除按钮。 */
			@Override
			public void extractContent(GuiGraphicsExtractor graphics, int mouseX, int mouseY, boolean hovered, float delta) {
				graphics.text(font, name, getContentX(), getContentYMiddle() - 4, KitUi.argb(hovered ? 0xFFFF55 : 0xFFFFFF));
				int buttonY = getContentY() - 2;
				remove.setPosition(getContentRight() - 46, buttonY);
				load.setPosition(getContentRight() - 94, buttonY);
				load.extractRenderState(graphics, mouseX, mouseY, delta);
				remove.extractRenderState(graphics, mouseX, mouseY, delta);
			}

			/** 行内可点按钮。 */
			@Override
			public List<? extends GuiEventListener> children() {
				return List.of(load, remove);
			}

			/** 旁白包含行内按钮。 */
			@Override
			public List<? extends NarratableEntry> narratables() {
				return List.of(load, remove);
			}
		}
	}
}
