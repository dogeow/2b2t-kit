package dev.twob2tkit.runtime.engine;

import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.client.Minecraft;
import net.minecraft.client.player.LocalPlayer;
import net.minecraft.core.BlockPos;
import net.minecraft.core.Direction;
import net.minecraft.gizmos.GizmoStyle;
import net.minecraft.gizmos.Gizmos;
import net.minecraft.gizmos.TextGizmo;
import net.minecraft.world.phys.Vec3;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;

/** 记录挖矿走过的路点，供沿原路返回。热加载后从磁盘/快照恢复。 */
final class BorerTrail {
	private static final Logger LOGGER = LoggerFactory.getLogger("2b2t-kit/Borer");
	private static final int MAX_POINTS = 5000;
	/** 没挖矿时在下界闲逛，只留最近这一段去回门，不要把一辈子的路都攒进去。 */
	static final int IDLE_KEEP = 120;
	/** 磁盘里已经顶满的旧路，加载时只留门和最近一段。 */
	static final int STALE_KEEP = 200;
	private static final double RECORD_DISTANCE = 2.2;
	/** 每隔几个路点补一个方块框。路点间距约 2.2 格，四个大概九格一个。 */
	private static final int MARKER_EVERY = 4;
	/** 回家箭头只画眼前这一段，整条穿墙会卡。 */
	private static final int HOME_ARROWS = 40;
	/** 走到这个距离内就算踏上该路点，再取更靠近家的下一个。 */
	private static final double ARRIVE_DISTANCE_SQR = 2.25;
	/** 沿已挖开的巷道 BFS。只确认还在这条巷道里，不必扫 2500 格。 */
	private static final int REACH_SCAN_LIMIT = 400;
	private static final long SAVE_INTERVAL_MS = 8000L;
	private static final int REACH_CACHE_TICKS = 8;
	private final ArrayList<BlockPos> points = new ArrayList<>();
	private BlockPos portal;
	/** 沿路回家时粘住的路点下标，避免 BFS 每 tick 跳到旁边的分叉。 */
	private int stickyIndex = -1;
	private boolean dirty;
	private long lastSaveMs;
	private Map<Long, Integer> indexAtCache;
	private int indexAtSize = -1;
	private BlockPos indexAtTail;
	private int cachedReachable = -1;
	private BlockPos cachedReachAt;
	private int reachCacheLeft;

	/** 路点数量。 */
	int size() {
		return points.size();
	}

	/** 清空路点。 */
	void clear() {
		points.clear();
		stickyIndex = -1;
		dirty = true;
		invalidateReachCache();
	}

	/** 重置沿路跟随进度。 */
	void resetFollow() {
		stickyIndex = -1;
		invalidateReachCache();
	}

	/** 已记地狱门坐标；无则 null。 */
	BlockPos portal() {
		return portal;
	}

	/** 路点列表第一个。 */
	BlockPos first() {
		return points.isEmpty() ? null : points.getFirst();
	}

	/** 记下地狱门坐标。 */
	void setPortal(Minecraft client, BlockPos pos) {
		if (pos == null) return;
		portal = pos.immutable();
		ensureFirst(portal);
		savePortal(client);
	}

	/** 确保路点列表有脚下起点。 */
	void ensureFirst(BlockPos pos) {
		if (pos == null) return;
		BlockPos anchor = pos.immutable();
		if (!points.isEmpty() && points.getFirst().distSqr(anchor) <= 9.0) return;
		if (points.size() >= MAX_POINTS) points.removeLast();
		points.addFirst(anchor);
		dirty = true;
		invalidateReachCache();
	}

	/** 路点列表最后一个。 */
	BlockPos last() {
		return points.isEmpty() ? null : points.getLast();
	}

	/** 弹出最后一个路点。 */
	void popLast() {
		if (!points.isEmpty()) points.removeLast();
	}

	/** 路点尾部描述短文。 */
	String describeTail(int count) {
		if (points.isEmpty()) return "-";
		int from = Math.max(0, points.size() - Math.max(1, count));
		StringBuilder text = new StringBuilder();
		for (int i = points.size() - 1; i >= from; i--) {
			if (!text.isEmpty()) text.append(" <- ");
			BlockPos pos = points.get(i);
			text.append(pos.getX()).append(',').append(pos.getY()).append(',').append(pos.getZ());
		}
		return text.toString();
	}

	/** 按当前位置追加路点并裁到上限。 */
	void record(Minecraft client, LocalPlayer player) {
		record(client, player, MAX_POINTS);
	}

	/** 没开盾构时只留最近一段路回门，避免和下界乱飞叠成 5000 点。 */
	void recordIdle(Minecraft client, LocalPlayer player) {
		record(client, player, IDLE_KEEP);
	}

	/** 按当前位置追加路点并裁到上限。 */
	private void record(Minecraft client, LocalPlayer player, int maxKeep) {
		if (player == null) return;
		BlockPos here = player.blockPosition();
		if (points.isEmpty()) {
			points.add(here.immutable());
			save(client);
			return;
		}
		BlockPos last = points.getLast();
		if (here.distSqr(last) < RECORD_DISTANCE * RECORD_DISTANCE) return;
		points.add(here.immutable());
		trimKeepFirst(maxKeep);
		dirty = true;
		invalidateReachCache();
		maybeSave(client);
	}

	/**
	 * 新开一局挖矿。人还在旧巷道里就接着记，不要清成「门 + 脚底」两条再画穿墙斜线。
	 * 主世界不把下界门坐标写进路点。
	 */
	void beginMiningSession(Minecraft client, LocalPlayer player, boolean inNether) {
		if (!inNether) detachPortalAnchor();
		if (player != null && !points.isEmpty()) {
			Vec3 pos = player.position();
			int nearest = nearestIndex(pos);
			double dist = Math.sqrt(pos.distanceToSqr(Vec3.atCenterOf(points.get(nearest))));
			if (BorerTrailPolicy.resumeExistingTrail(dist)) {
				if (inNether && portal != null) ensureFirst(portal);
				record(client, player, MAX_POINTS);
				save(client);
				return;
			}
		}
		BlockPos gate = portal;
		points.clear();
		stickyIndex = -1;
		invalidateReachCache();
		if (BorerTrailPolicy.includePortalAsHome(inNether) && gate != null) {
			points.add(gate.immutable());
		}
		if (player != null) {
			BlockPos here = player.blockPosition();
			if (points.isEmpty() || here.distSqr(points.getLast()) >= RECORD_DISTANCE * RECORD_DISTANCE) {
				points.add(here.immutable());
			}
		}
		dirty = true;
		save(client);
	}

	/** 主世界路点里的下界门坐标不是能走的巷道。 */
	void detachPortalAnchor() {
		if (portal == null || points.isEmpty()) return;
		boolean removed = points.removeIf(pos -> pos.distManhattan(portal) <= 3);
		if (removed) {
			stickyIndex = -1;
			dirty = true;
			invalidateReachCache();
		}
	}

	/** 清空路点但保留地狱门。 */
	void clearKeepPortal() {
		BlockPos gate = portal;
		points.clear();
		stickyIndex = -1;
		invalidateReachCache();
		if (gate != null) points.add(gate.immutable());
		dirty = true;
	}

	/** 裁路点但保留起点。 */
	private void trimKeepFirst(int maxKeep) {
		int keep = Math.max(2, maxKeep);
		while (points.size() > keep) {
			if (points.size() > 1) points.remove(1);
			else break;
		}
	}

	/** 画出回家路点箭头。 */
	void emitGizmos() {
		int start = Math.max(0, points.size() - 16);
		for (int i = start; i < points.size() - 1; i++) {
			BorerGizmos.hold(Gizmos.arrow(
				Vec3.atCenterOf(points.get(i)), Vec3.atCenterOf(points.get(i + 1)), 0xFF00E5FF, 2.2F));
		}
	}

	/** 金色箭头从人脚边沿记下的巷道指向家，不把下层旧路穿墙画上来。 */
	BlockPos emitHomeRoute(Minecraft client, LocalPlayer player) {
		if (points.isEmpty() || player == null) return null;
		int from = followIndex(client, player);
		BlockPos feet = player.blockPosition();
		BlockPos home = points.getFirst();
		int drawn = 0;
		int start = Math.max(1, from);
		for (int i = start; i >= 1 && drawn < HOME_ARROWS; i--) {
			BlockPos a = points.get(i);
			BlockPos b = points.get(i - 1);
			int xz = Math.abs(a.getX() - feet.getX()) + Math.abs(a.getZ() - feet.getZ());
			int dy = Math.abs(a.getY() - feet.getY());
			if (BorerTrailPolicy.stopDrawingBeyond(xz)) break;
			if (!BorerTrailPolicy.drawSegmentNearPlayer(xz, dy)) continue;
			if (!BorerTrailPolicy.isCorridorSegment(a.distManhattan(b))) continue;
			if (BorerTrailPolicy.skipDetourWhenDrawing()
				&& home != null
				&& !BorerTrailPolicy.towardHome(b.distSqr(home), a.distSqr(home))) {
				continue;
			}
			float width = drawn == 0 ? 3.4F : 2.2F;
			BorerGizmos.holdOnTop(Gizmos.arrow(
				Vec3.atCenterOf(a), Vec3.atCenterOf(b), 0xFFFFCC33, width));
			if (drawn % MARKER_EVERY == 0) {
				BorerGizmos.holdOnTop(Gizmos.cuboid(a, GizmoStyle.stroke(0xFFFFCC33, 2.0F)));
			}
			drawn++;
		}
		if (home != null && BorerTrailPolicy.drawSegmentNearPlayer(
			Math.abs(home.getX() - feet.getX()) + Math.abs(home.getZ() - feet.getZ()),
			Math.abs(home.getY() - feet.getY()))) {
			BorerGizmos.holdOnTop(Gizmos.cuboid(home, GizmoStyle.strokeAndFill(0xFFFFCC33, 3.6F, 0x44FFCC33)));
			try {
				BorerGizmos.holdOnTop(Gizmos.billboardText("家", Vec3.atCenterOf(home.above()),
					TextGizmo.Style.forColorAndCentered(0xFFFFCC33).withScale(0.32F)));
			} catch (IllegalStateException ignored) {
			}
		}
		return nextTowardHome(client, player);
	}

	/**
	 * 下一个该走的路点：先回到最近路点，再选更靠近家的邻居。
	 * 不能一律往下标减小，否则后来往家走时记下的点会把人指回去。
	 */
	BlockPos nextTowardHome(Minecraft client, LocalPlayer player) {
		if (points.isEmpty() || player == null) return null;
		int from = followIndex(client, player);
		Vec3 pos = player.position();
		BlockPos stand = points.get(from);
		if (pos.distanceToSqr(Vec3.atCenterOf(stand)) >= ARRIVE_DISTANCE_SQR) return stand;
		BlockPos home = points.getFirst();
		double current = stand.distSqr(home);
		BlockPos best = null;
		double bestDist = current;
		if (from > 0) {
			BlockPos prev = points.get(from - 1);
			if (BorerTrailPolicy.towardHome(prev.distSqr(home), bestDist)) {
				best = prev;
				bestDist = prev.distSqr(home);
			}
		}
		if (from + 1 < points.size()) {
			BlockPos next = points.get(from + 1);
			if (BorerTrailPolicy.towardHome(next.distSqr(home), bestDist)) {
				best = next;
				bestDist = next.distSqr(home);
			}
		}
		return best != null ? best : stand;
	}

	/** 往家方向看更远的路点，避免盯着脚边 2 格外的锯齿点左右甩头。 */
	BlockPos lookTowardHome(Minecraft client, LocalPlayer player, int skip) {
		if (points.isEmpty() || player == null) return nextTowardHome(client, player);
		int from = followIndex(client, player);
		return points.get(Math.max(0, from - Math.max(1, skip)));
	}

	/** 沿路回家还剩几段。 */
	int remainingTowardHome(Minecraft client, LocalPlayer player) {
		if (points.isEmpty() || player == null) return 0;
		return followIndex(client, player);
	}

	/** 还在已记录的巷道附近。不再每 tick 跑一遍 BFS。 */
	boolean connectedToTrail(Minecraft client, LocalPlayer player) {
		if (points.isEmpty() || player == null) return false;
		int idx = followIndex(client, player);
		return player.position().distanceToSqr(Vec3.atCenterOf(points.get(idx))) <= 12.0 * 12.0;
	}

	/** 沿已挖开的 1×2 走到的路点下标。人已经离开就改贴最近的，箭头从脚边开始。 */
	int followIndex(Minecraft client, LocalPlayer player) {
		if (points.isEmpty() || player == null) return 0;
		Vec3 pos = player.position();
		boolean needStick = stickyIndex < 0 || stickyIndex >= points.size();
		if (!needStick) {
			needStick = BorerTrailPolicy.shouldRestick(
				Math.sqrt(pos.distanceToSqr(Vec3.atCenterOf(points.get(stickyIndex)))));
		}
		if (needStick) {
			int reachable = nearestReachableIndex(client, player);
			stickyIndex = reachable >= 0 ? reachable : nearestIndex(pos);
		}
		while (stickyIndex > 0 && pos.distanceToSqr(Vec3.atCenterOf(points.get(stickyIndex))) < ARRIVE_DISTANCE_SQR) {
			int prev = stickyIndex - 1;
			BlockPos home = points.getFirst();
			if (home != null && !BorerTrailPolicy.towardHome(
				points.get(prev).distSqr(home), points.get(stickyIndex).distSqr(home))) {
				break;
			}
			stickyIndex--;
		}
		return stickyIndex;
	}

	/** 最近可达路点下标。 */
	private int nearestReachableIndex(Minecraft client, LocalPlayer player) {
		if (points.isEmpty() || client == null || client.level == null || player == null) return -1;
		BlockPos start = player.blockPosition();
		if (cachedReachable >= 0 && cachedReachAt != null && cachedReachAt.distManhattan(start) <= 2 && reachCacheLeft > 0) {
			reachCacheLeft--;
			return cachedReachable;
		}
		int found = scanReachable(client, player, start);
		cachedReachable = found;
		cachedReachAt = start.immutable();
		reachCacheLeft = REACH_CACHE_TICKS;
		return found;
	}

	/** 从起点扫描可达路点数。 */
	private int scanReachable(Minecraft client, LocalPlayer player, BlockPos start) {
		Map<Long, Integer> indexAt = indexAtMap();
		Integer standing = indexAt.get(start.asLong());
		if (standing == null) standing = indexAt.get(start.below().asLong());
		if (standing == null) standing = indexAt.get(start.above().asLong());
		if (standing != null) return standing;
		ArrayDeque<BlockPos> queue = new ArrayDeque<>();
		Set<Long> seen = new HashSet<>();
		queue.add(start);
		seen.add(start.asLong());
		int visited = 0;
		while (!queue.isEmpty() && visited < REACH_SCAN_LIMIT) {
			BlockPos cur = queue.removeFirst();
			visited++;
			Integer hit = indexAt.get(cur.asLong());
			if (hit == null) hit = indexAt.get(cur.below().asLong());
			if (hit == null) hit = indexAt.get(cur.above().asLong());
			if (hit != null) return hit;
			for (Direction dir : Direction.values()) {
				BlockPos next = cur.relative(dir);
				if (!seen.add(next.asLong())) continue;
				if (!client.level.hasChunkAt(next)) continue;
				if (!BorerHazards.isOpenStandColumn(client, next)) continue;
				queue.add(next);
			}
		}
		return -1;
	}

	/** 路点坐标 → 最大下标缓存表。 */
	private Map<Long, Integer> indexAtMap() {
		BlockPos tail = last();
		if (indexAtCache != null && indexAtSize == points.size() && Objects.equals(indexAtTail, tail)) {
			return indexAtCache;
		}
		Map<Long, Integer> indexAt = new HashMap<>(Math.max(16, points.size() * 2));
		for (int i = 0; i < points.size(); i++) {
			indexAt.merge(points.get(i).asLong(), i, Math::max);
		}
		indexAtCache = indexAt;
		indexAtSize = points.size();
		indexAtTail = tail;
		return indexAt;
	}

	/** 作废可达缓存。 */
	private void invalidateReachCache() {
		indexAtCache = null;
		indexAtSize = -1;
		indexAtTail = null;
		cachedReachable = -1;
		cachedReachAt = null;
		reachCacheLeft = 0;
	}

	/** 是否已到家/门。 */
	boolean arrivedHome(Minecraft client, LocalPlayer player) {
		BlockPos home = first();
		if (home == null || player == null) return false;
		if (player.position().distanceToSqr(Vec3.atCenterOf(home)) > 16.0) return false;
		return followIndex(client, player) <= 1;
	}

	/** 最近路点下标。 */
	private int nearestIndex(Vec3 playerPos) {
		int best = 0;
		double bestDist = Double.MAX_VALUE;
		for (int i = 0; i < points.size(); i++) {
			double dist = playerPos.distanceToSqr(Vec3.atCenterOf(points.get(i)));
			if (dist < bestDist) {
				bestDist = dist;
				best = i;
			}
		}
		return best;
	}

	/** 导出路点快照字符串。 */
	String snapshot() {
		StringBuilder text = new StringBuilder();
		if (portal != null) {
			text.append("portal ").append(portal.getX()).append(' ').append(portal.getY()).append(' ')
				.append(portal.getZ()).append('\n');
		}
		for (BlockPos pos : points) {
			text.append(pos.getX()).append(' ').append(pos.getY()).append(' ').append(pos.getZ()).append('\n');
		}
		return text.toString();
	}

	/** 从快照恢复路点。 */
	void restore(String snapshot) {
		if (snapshot == null || snapshot.isBlank()) return;
		points.clear();
		stickyIndex = -1;
		invalidateReachCache();
		for (String line : snapshot.split("\n")) {
			parseLine(line.trim());
		}
		if (points.size() >= MAX_POINTS) trimKeepFirst(STALE_KEEP);
	}

	/** 有变更时写盘。 */
	void maybeSave(Minecraft client) {
		if (!dirty) return;
		if (System.currentTimeMillis() - lastSaveMs < SAVE_INTERVAL_MS) return;
		save(client);
	}

	/** 立即写盘。 */
	void save(Minecraft client) {
		try {
			Path file = trailFile();
			Files.createDirectories(file.getParent());
			List<String> lines = new ArrayList<>(points.size() + 1);
			if (portal != null) {
				lines.add("portal " + portal.getX() + " " + portal.getY() + " " + portal.getZ());
			}
			for (BlockPos pos : points) {
				lines.add(pos.getX() + " " + pos.getY() + " " + pos.getZ());
			}
			Files.write(file, lines, StandardCharsets.UTF_8);
			dirty = false;
			lastSaveMs = System.currentTimeMillis();
		} catch (IOException exception) {
			LOGGER.warn("Could not save borer trail", exception);
		}
	}

	/** 内存空时从磁盘加载路点。 */
	void loadIfEmpty(Minecraft client) {
		if (!points.isEmpty()) return;
		Path file = trailFile();
		if (!Files.isRegularFile(file) && client != null) {
			Path legacy = legacyTrailFile(client);
			if (legacy != null && Files.isRegularFile(legacy)) file = legacy;
		}
		if (!Files.isRegularFile(file)) return;
		try {
			for (String line : Files.readAllLines(file, StandardCharsets.UTF_8)) {
				parseLine(line.trim());
			}
			if (points.size() >= MAX_POINTS) {
				trimKeepFirst(STALE_KEEP);
				dirty = true;
				LOGGER.info("Trimmed stale borer trail to {} points ({})", points.size(), file);
			} else {
				LOGGER.info("Loaded {} borer trail points from {}", points.size(), file);
			}
		} catch (Exception exception) {
			LOGGER.warn("Could not load borer trail", exception);
			points.clear();
		}
	}

	/** 尚未记门时从磁盘加载。 */
	void loadPortalIfMissing(Minecraft client) {
		if (portal != null) return;
		Path file = portalFile();
		if (!Files.isRegularFile(file) && client != null) {
			Path legacy = legacyPortalFile(client);
			if (legacy != null && Files.isRegularFile(legacy)) file = legacy;
		}
		if (!Files.isRegularFile(file)) return;
		try {
			List<String> lines = Files.readAllLines(file, StandardCharsets.UTF_8);
			if (lines.isEmpty()) return;
			String[] parts = lines.getFirst().trim().split("\\s+");
			if (parts.length < 3) return;
			int i = parts[0].equalsIgnoreCase("portal") ? 1 : 0;
			if (parts.length < i + 3) return;
			portal = new BlockPos(Integer.parseInt(parts[i]), Integer.parseInt(parts[i + 1]), Integer.parseInt(parts[i + 2]));
		} catch (Exception exception) {
			LOGGER.warn("Could not load nether portal", exception);
			portal = null;
		}
	}

	/** 解析一行持久化路点。 */
	private void parseLine(String line) {
		if (line.isBlank()) return;
		String[] parts = line.split("\\s+");
		if (parts.length >= 4 && parts[0].equalsIgnoreCase("portal")) {
			if (portal == null) {
				portal = new BlockPos(Integer.parseInt(parts[1]), Integer.parseInt(parts[2]), Integer.parseInt(parts[3]));
			}
			return;
		}
		if (parts.length < 3) return;
		points.add(new BlockPos(Integer.parseInt(parts[0]), Integer.parseInt(parts[1]), Integer.parseInt(parts[2])));
	}

	/** 保存地狱门坐标。 */
	private void savePortal(Minecraft client) {
		if (portal == null) return;
		try {
			Path file = portalFile();
			Files.createDirectories(file.getParent());
			Files.write(file, List.of(portal.getX() + " " + portal.getY() + " " + portal.getZ()), StandardCharsets.UTF_8);
		} catch (IOException exception) {
			LOGGER.warn("Could not save nether portal", exception);
		}
	}

	/** 路点文件路径。 */
	private static Path trailFile() {
		return FabricLoader.getInstance().getConfigDir().resolve("2b2t-kit/borer-trail.txt");
	}

	/** 地狱门文件路径。 */
	private static Path portalFile() {
		return FabricLoader.getInstance().getConfigDir().resolve("2b2t-kit/nether-portal.txt");
	}

	/** 旧版路点文件路径。 */
	private static Path legacyTrailFile(Minecraft client) {
		if (client == null || client.gameDirectory == null) return null;
		return client.gameDirectory.toPath().resolve("config/2b2t-kit/borer-trail.txt");
	}

	/** 旧版地狱门文件路径。 */
	private static Path legacyPortalFile(Minecraft client) {
		if (client == null || client.gameDirectory == null) return null;
		return client.gameDirectory.toPath().resolve("config/2b2t-kit/nether-portal.txt");
	}
}
