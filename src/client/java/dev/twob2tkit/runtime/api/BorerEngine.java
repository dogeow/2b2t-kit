package dev.twob2tkit.runtime.api;

import net.minecraft.client.Minecraft;

/**
 * 可热加载的盾构引擎契约。Fabric 注册与 Mixin 留在稳定核心，本接口由引擎 jar 实现。
 */
public interface BorerEngine {
	/** 本引擎要求的最低宿主 API 版本；兼容 1.6.9 包时保持为 1。 */
	default int requiredHostApiVersion() {
		return 1;
	}

	/** 当前功能包版本，给设置页和日志用。 */
	String runtimeVersion();

	/** 是否正在挖矿或找矿。 */
	boolean isActive();

	/** 当前模式内部名。 */
	String modeName();

	/** 给 HUD / 聊天看的短状态。 */
	String status();

	/** 按模式名启动盾构机。 */
	void start(Minecraft client, String modeName);

	/** 停止并松开按键。 */
	void stop(Minecraft client, String reason);

	/** 开关：运行则停，否则用上次模式启动。 */
	void toggle(Minecraft client);

	/** 每个客户端 tick 推进挖矿逻辑。 */
	void tick(Minecraft client);

	/** 世界每帧收集 gizmo 时画回家箭头。不要在 tick 里画，否则会闪。 */
	default void emitFrameGizmos(Minecraft client) {
	}

	/** 沿挖矿时记下的路往回走。没有路线时什么都不做。 */
	default void goHome(Minecraft client) {
	}

	/** 只显示回家箭头，不自动走。再调一次关闭。 */
	default void toggleHomeRoute(Minecraft client) {
	}

	/** 是否正在显示回家路线。 */
	default boolean isShowingHomeRoute() {
		return false;
	}

	/** 沿走过的路飞回记下的地狱门。 */
	default void goToPortal(Minecraft client) {
	}

	/** 未开盾构时也记过门坐标和下界路线。 */
	default void observeWorld(Minecraft client) {
	}

	/** 是否正在沿原路返回。 */
	default boolean isGoingHome() {
		return false;
	}

	/** 是否正在飞回地狱门。 */
	default boolean isReturningToPortal() {
		return false;
	}

	/** 是否已经记下地狱门。 */
	default boolean hasNetherPortal() {
		return false;
	}

	/** 已记录的回家路点数量。 */
	default int trailLength() {
		return 0;
	}

	/** 丢掉旧路点，只留地狱门。 */
	default void clearTrailKeepPortal() {
	}

	/** Meteor 改朝向之后，回家/回门时把视角写回去。 */
	default void reapplyLook(Minecraft client) {
	}

	/** 热加载前把内存中的挖矿路线导出来，避免只存在旧引擎里。 */
	default String exportTrailSnapshot() {
		return "";
	}

	/** 热加载后把路线导回新引擎。 */
	default void importTrailSnapshot(String snapshot) {
	}

	/** 从磁盘恢复路线和地狱门；内存已有路点时不会覆盖。 */
	default void restorePersistentState(Minecraft client) {
	}

	/** 关掉区域黄框与 HUD；配置里已无区域时引擎应清掉缓存。 */
	default void dismissAreaPreview() {
	}
}
