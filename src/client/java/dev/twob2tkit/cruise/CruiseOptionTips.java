package dev.twob2tkit.cruise;

/** 巡航选项提示，CruiseOptionsScreen 与 ClickGui 共用。 */
public final class CruiseOptionTips {
	public static final String ARRIVAL_RADIUS = "靠近目标多少格算到达。";
	public static final String STUCK_SECONDS = "一直不动就停；会先尝试后退侧移自救。0=关。";
	public static final String TURN_SPEED = "转向速度（度/tick）。越大转得越快，默认 12。";
	public static final String OBSTACLE_LOOK_AHEAD = "前方多少格内开始探测障碍。";
	public static final String OBSTACLE_BYPASS = "绕障时沿侧向平移的基础距离。";

	private CruiseOptionTips() {
	}
}
