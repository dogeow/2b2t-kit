package dev.twob2tkit.runtime.api;

import net.minecraft.client.Minecraft;

/**
 * 稳定核心暴露给可热加载盾构引擎的宿主桥。
 * 新方法必须带 {@code default}，否则旧主机热加载会崩。
 */
public interface BorerHost {
	default boolean borerAutoDefend() { return true; }
	default boolean borerAreaDiscardStone() { return false; }
	default boolean borerAreaStoreDrops() { return false; }
	/** Shared host ballistics, also used by the existing ghast archer. */
	default net.minecraft.world.phys.Vec3 borerBowAim(Minecraft client, net.minecraft.world.entity.Entity target) { return null; }
	default void borerRangedMode(boolean active) {}
	/** New host supplies the camera and release hooks; an old host must not silently use the new firing protocol. */
	default boolean supportsVisibleBowAim() { return false; }
	default String borerBowDiagnostics() { return ""; }
	/** 宿主 API 版本，功能包用它判断能不能加载。 */
	int apiVersion();

	/** 启动盾构前关掉巡航等冲突模块。 */
	void prepareForBorer(Minecraft client);

	/** 苦力怕围箱是否正在进行。 */
	boolean surroundActive();

	/** 让核心模组立刻开始围箱。 */
	void startEmergencySurround(Minecraft client);

	/** 上次使用的盾构模式。 */
	String borerLastMode();

	/** 记住这次启动的模式。 */
	void setBorerLastMode(String value);

	/** 锁定朝向：LOOK 或东南西北。 */
	String borerHeading();

	/** 勾选矿种，逗号分隔，例如 DIAMOND,LAPIS。 */
	String borerOreTarget();

	/** 挖煤只拿经验、不捡煤，避免煤把背包塞满。 */
	default boolean borerCoalXpMode() {
		return false;
	}

	/** 挖下界石英只拿经验、不捡石英，专门用来升级。 */
	default boolean borerQuartzXpMode() {
		return false;
	}

	/** 背包满或镐快坏时沿路回家（下界则飞回地狱门）。 */
	default boolean borerHomeOnDone() {
		return true;
	}

	/** 向前挖时遇岩浆提前拐弯。关掉则保持直线，适合地铁。 */
	default boolean borerTurnAroundLava() {
		return true;
	}

	/** 默认轴向瞄准：只沿东西南北上下挖眼前通道，不斜着瞄。关掉则任意方向。 */
	default boolean borerAxisAim() {
		return true;
	}

	/** 巷道宽度（找矿时强制 1）。 */
	int borerWidth();

	/** 巷道高度（找矿时强制 2）。 */
	int borerHeight();

	/** 向前看几格再挖。 */
	int borerLookAhead();

	/** 怪物停手/举盾的距离。 */
	int borerMobRadius();

	/** 找矿水平扫描半径。 */
	int borerOreRadius();

	/** 区域挖两点都已设。 */
	default boolean borerAreaSet() {
		return false;
	}

	/** 区域角点 A 的 X。 */
	default int borerAreaAx() {
		return 0;
	}

	/** 区域角点 A 的 Y。 */
	default int borerAreaAy() {
		return 0;
	}

	/** 区域角点 A 的 Z。 */
	default int borerAreaAz() {
		return 0;
	}

	/** 区域角点 B 的 X。 */
	default int borerAreaBx() {
		return 0;
	}

	/** 区域角点 B 的 Y。 */
	default int borerAreaBy() {
		return 0;
	}

	/** 区域角点 B 的 Z。 */
	default int borerAreaBz() {
		return 0;
	}

	/** 区域挖每次沿条带挖几格高。2=1×2。 */
	default int borerAreaSliceHeight() {
		return 2;
	}

	/**
	 * 区域挖换格顺序。{@code vertical}=竖井网格（默认），{@code nearest}=飞最近一口。
	 * 新字段带 default，旧主机热加载不会崩。
	 */
	default String borerAreaOrder() {
		return "vertical";
	}

	/** 附近有岩浆时是否停机。 */
	boolean borerStopOnLava();

	/** 是否自动封水和岩浆。 */
	boolean borerSealLiquids();

	/** 附近有敌对生物时是否躲开（向前挖拐弯；贴身才停手）。 */
	boolean borerPauseOnMob();

	/** 是否用副手盾牌举盾。 */
	boolean borerShieldOnMob();

	/** 苦力怕靠近时是否自动围箱。挖矿默认关掉，改躲开。 */
	boolean borerSurroundOnCreeper();

	/** 把当前设置写回配置文件。 */
	void saveSettings();

	/** 遇怪交战时按设置打开 Meteor KillAura / AutoLog。 */
	default void armAutoProtectIfEnabled(Minecraft client) {
	}

	/** 屏幕固定位置开始显示 AI 过程。旧主机空实现。 */
	default void beginAiProcess(String title) {
	}

	/** 追加一条 AI 步骤。 */
	default void noteAiProcess(String step) {
	}

	/** 结束 AI 过程；failed 时面板标红，结果再留几秒。 */
	default void endAiProcess(String result, boolean failed) {
	}

	/** 挖矿状态画到屏幕固定位置。旧主机空实现，引擎会退回准星字。 */
	default void showBorerHud(String action, int color, String detail) {
	}

	/** 隐藏屏幕上的盾构状态 HUD。 */
	default void hideBorerHud() {
	}
}
