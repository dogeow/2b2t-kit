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
	private static final Logger LOGGER = LoggerFactory.getLogger("twob2tkit/Borer");
	private static final double RECORD_DISTANCE = 2.2;
	/** 每隔几个路点补一个方块框。路点间距约 2.2 格，四个大概九格一个。 */
	private static final int MARKER_EVERY = 4;
	/** 回家箭头只画眼前这一段，整条穿墙会卡。 */
	private static final int HOME_ARROWS = 40;
	/** 沿已挖开的巷道 BFS。只确认还在这条巷道里，不必扫 2500 格。 */
	private static final int REACH_SCAN_LIMIT = 400;
	private static final long SAVE_INTERVAL_MS = 8000L;
	private static final int REACH_CACHE_TICKS = 8;
	private final ArrayList<BlockPos> points = new ArrayList<>();
	private final Set<Integer> breaks = new HashSet<>();
	private final BorerTrailStore store;
	private String scope;
	private boolean contextLoaded;
	BorerTrail() { this(new BorerTrailStore(FabricLoader.getInstance().getConfigDir().resolve("twob2tkit"))); }
	BorerTrail(BorerTrailStore store) { this.store = store; }
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
		breaks.clear();
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
		if (!points.isEmpty()) return; // Preserve the locked origin when a later portal is found.
		Set<Integer> shifted = new HashSet<>();
		for (int i : breaks) shifted.add(i + 1);
		breaks.clear(); breaks.addAll(shifted);
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
		recordPosition(client, player);
	}

	/** 没开盾构时只留最近一段路回门，避免和下界乱飞叠成 5000 点。 */
	void recordIdle(Minecraft client, LocalPlayer player) {
		// Do not append lobby/teleport jumps while merely connected. An explicit
		// mining restart records the discontinuity without replacing the origin.
		if (player != null && !points.isEmpty()
			&& player.blockPosition().distManhattan(last()) <= BorerTrailPolicy.CORRIDOR_MANHATTAN) recordPosition(client, player);
	}

	/** 按当前位置追加路点并裁到上限。 */
	private void recordPosition(Minecraft client, LocalPlayer player) {
		if (player == null) return;
		append(player.blockPosition());
		maybeSave(client);
	}

	/** Stops/restarts append to the same journey; long unobserved jumps are explicit gaps. */
	void append(BlockPos here) {
		if (points.isEmpty()) {
			points.add(here.immutable());
			dirty = true;
			return;
		}
		BlockPos last = points.getLast();
		if (here.distSqr(last) < RECORD_DISTANCE * RECORD_DISTANCE) return;
		if (!BorerTrailPolicy.isCorridorSegment(here.distManhattan(last))) breaks.add(points.size());
		points.add(here.immutable());
		dirty = true;
		invalidateReachCache();
	}

	/**
	 * 新开一局挖矿。人还在旧巷道里就接着记，不要清成「门 + 脚底」两条再画穿墙斜线。
	 * 主世界不把下界门坐标写进路点。
	 */
	void beginMiningSession(Minecraft client, LocalPlayer player, boolean inNether) {
		loadIfEmpty(client);
		if (!inNether) detachPortalAnchor();
		if (player != null) append(player.blockPosition());
		resetFollow();
		save(client);
	}

	/** 主世界路点里的下界门坐标不是能走的巷道。 */
	void detachPortalAnchor() {
		// World-scoped snapshots never mix portal anchors with overworld points.
		portal = null;
	}

	/** 清空路点但保留地狱门。 */
	void clearKeepPortal() {
		BlockPos gate = portal;
		points.clear();
		breaks.clear();
		stickyIndex = -1;
		invalidateReachCache();
		if (gate != null) points.add(gate.immutable());
		dirty = true;
	}

	/** Back up before replacing the active journey. A failed backup leaves it intact. */
	Path startNewJourney(BlockPos here) throws IOException {
		if (scope == null) throw new IOException("尚未进入有效世界");
		Path backup = store.archive(scope, snapshot());
		String replacement = BorerTrailStore.header(scope)
			+ (portal == null ? "" : "portal " + portal.getX() + " " + portal.getY() + " " + portal.getZ() + "\n")
			+ here.getX() + " " + here.getY() + " " + here.getZ() + "\n";
		store.write(scope, replacement);
		restore(replacement);
		dirty = false;
		return backup;
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

	/** 先贴回已记录的路线，然后按记录的逆序走，保留矿道里的绕行。 */
	BlockPos nextTowardHome(Minecraft client, LocalPlayer player) {
		if (points.isEmpty() || player == null) return null;
		return points.get(followIndex(client, player));
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
		stickyIndex = BorerTrailPolicy.advanceReturnIndex(points, stickyIndex, pos, breaks);
		return stickyIndex;
	}

	boolean returnRouteHasGap(Minecraft client, LocalPlayer player) {
		if (points.isEmpty()) return false;
		if (BorerTrailPolicy.reachedReturnWaypoint(player.position(), first())) return false;
		int index = followIndex(client, player);
		return breaks.contains(index) && BorerTrailPolicy.reachedReturnWaypoint(player.position(), points.get(index))
			|| player.position().distanceToSqr(Vec3.atBottomCenterOf(points.get(index))) > 12 * 12;
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
		if (BorerTrailPolicy.reachedReturnWaypoint(player.position(), home)) return true;
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
		if (scope != null) text.append(BorerTrailStore.header(scope));
		for (int index : breaks.stream().sorted().toList()) text.append("gap ").append(index).append('\n');
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
		breaks.clear(); portal = null; scope = null;
		stickyIndex = -1;
		invalidateReachCache();
		for (String line : snapshot.split("\n")) {
			parseLine(line.trim());
		}
		contextLoaded = scope != null;
	}

	/** 有变更时写盘。 */
	void maybeSave(Minecraft client) {
		if (!dirty) return;
		if (System.currentTimeMillis() - lastSaveMs < SAVE_INTERVAL_MS) return;
		save(client);
	}

	/** Save the bound world, even while the client is disconnecting or changing dimensions. */
	void save(Minecraft client) {
		try {
			if (scope == null) loadIfEmpty(client);
			if (scope == null) return;
			store.write(scope, snapshot());
			dirty = false;
			lastSaveMs = System.currentTimeMillis();
		} catch (IOException exception) {
			LOGGER.warn("Could not save borer journey", exception);
		}
	}

	static String canonicalServer(String address) {
		String value=address.strip().toLowerCase(java.util.Locale.ROOT);
		return value.endsWith(":25565") ? value.substring(0,value.length()-6) : value;
	}

	static String worldScope(Minecraft client) {
		if (client == null || client.level == null) return null;
		String server = client.getCurrentServer() != null ? "server:" + canonicalServer(client.getCurrentServer().ip)
			: client.getSingleplayerServer() != null ? "local:" + client.getSingleplayerServer()
				.getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toAbsolutePath().normalize() : null;
		return server == null ? null : server + "|" + client.level.dimension().identifier();
	}

	boolean matchesWorld(Minecraft client) {
		return contextLoaded && scope != null && scope.equals(worldScope(client));
	}

	/** Restore this world's journey once; an intentionally empty journey stays empty. */
	void loadIfEmpty(Minecraft client) {
		String key = worldScope(client);
		if (key == null) return;
		try { useScope(key); }
		catch (IOException | IllegalArgumentException error) {
			LOGGER.error("Could not switch mining journey; keep prior snapshot and refuse this world", error);
			contextLoaded = false;
		}
	}

	void useScope(String key) throws IOException {
		if (contextLoaded && key.equals(scope)) return;
		String imported = scope == null && !points.isEmpty() ? snapshot() : null;
		if (scope != null && dirty) store.write(scope, snapshot());
		String next = store.read(key);
		if (next == null) next = store.migrateLegacy(key, imported);
		if (next == null) next = BorerTrailStore.header(key);
		restore(next);
		dirty = false;
	}

	/** The portal is part of the scoped journey, not a shared global coordinate. */
	void loadPortalIfMissing(Minecraft client) { loadIfEmpty(client); }

	/** 解析一行持久化路点。 */
	private void parseLine(String line) {
		if (line.isBlank()) return;
		if (line.startsWith("scope ")) { scope = BorerTrailStore.scopeOf(line); return; }
		if (line.startsWith("gap ")) { breaks.add(Integer.parseInt(line.substring(4))); return; }
		String[] parts = line.split("\\s+");
		if (parts.length >= 4 && parts[0].equalsIgnoreCase("portal")) {
			if (portal == null) {
				portal = new BlockPos(Integer.parseInt(parts[1]), Integer.parseInt(parts[2]), Integer.parseInt(parts[3]));
			}
			return;
		}
		if (parts.length < 3) return;
		BlockPos point = new BlockPos(Integer.parseInt(parts[0]), Integer.parseInt(parts[1]), Integer.parseInt(parts[2]));
		if (!points.isEmpty() && point.distManhattan(points.getLast()) > BorerTrailPolicy.CORRIDOR_MANHATTAN) breaks.add(points.size());
		points.add(point);
	}

	/** Portal writes share the same atomic, per-world snapshot. */
	private void savePortal(Minecraft client) { save(client); }
}
