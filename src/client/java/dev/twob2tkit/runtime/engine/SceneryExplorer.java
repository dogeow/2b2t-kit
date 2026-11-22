package dev.twob2tkit.runtime.engine;

import dev.twob2tkit.runtime.api.RotationAim;
import net.minecraft.client.Minecraft;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.core.BlockPos;
import net.minecraft.network.chat.Component;
import net.minecraft.world.level.chunk.LevelChunk;
import net.minecraft.world.level.chunk.status.ChunkStatus;
import net.minecraft.world.level.levelgen.Heightmap;
import java.nio.file.Path;
import java.util.*;

/** Centre-out terrain capture. Does not dig, place, attack, select inventory slots or touch cruise destinations. */
final class SceneryExplorer {
	private final DefaultTunnelBorerEngine engine;
	private final BorerAreaFlightSession flight = new BorerAreaFlightSession();
	private SceneryCache cacheBackend;
	private final SceneryServerView serverView = new SceneryServerView();
	private SceneryServerView.Limits view;
	private SceneryCoverage coverage;
	private SceneryCoverage.Chunk target;
	private Iterator<SceneryCoverage.Chunk> reuseScan;
	private final Map<SceneryCoverage.Chunk,java.util.concurrent.CompletableFuture<Boolean>> reusePending = new LinkedHashMap<>();
	private int reuseChecked, reuseTotal, lastCheckpointTick;
	private Integer batchX, batchZ;
	private ClientLevel level;
	private Path progress;
	private String world, cache, status = "尚未开始风景预加载";
	private boolean active;
	private int ticks, scan, waitTicks, idleTicks, lastCovered;
	private final SceneryCapturePolicy.Quiet quiet = new SceneryCapturePolicy.Quiet();
	private double altitude, bestDistance = Double.POSITIVE_INFINITY;
	private String goalKey = "";
	private RotationAim.Look look;
	private record Observed(LevelChunk chunk, int tick) {}
	private final Map<Long, Observed> observed = new HashMap<>();
	SceneryExplorer(DefaultTunnelBorerEngine engine) { this.engine = engine; }
    private ClientLevel mappedLevel;
    private SceneryCoverage mappedCoverage;

    dev.twob2tkit.runtime.api.MapTaskView.Scenery mapView(Minecraft c, dev.twob2tkit.runtime.api.MapTaskView.Area viewport) {
        if (c.level == null) return null;
        SceneryCoverage plan = level == c.level ? coverage : null;
        if (plan == null) {
            if (mappedLevel != c.level) {
                mappedLevel = c.level;
                try {
                    mappedCoverage = SceneryProgress.readForMap(
                        c.gameDirectory.toPath().resolve("config/twob2tkit/scenery-progress.json"), world(c));
                } catch (java.io.IOException unavailable) { mappedCoverage = null; }
            }
            plan = mappedCoverage;
        }
        if (plan == null) return null;
        var bounds = borderBounds(c);
        if (!active) plan.clipTo(bounds);
        var current = active ? target : null;
        boolean preview = !active && viewport == null && c.player != null;
        if (preview) current = plan.nextNearest(null,c.player.getX(),c.player.getZ());
        var batch = active && batchX != null ? new dev.twob2tkit.runtime.api.MapTaskView.Area(
            batchX * 512, batchZ * 512, batchX * 512 + 512, batchZ * 512 + 512) : null;
        if (preview && current != null && plan.radius > SceneryCoverage.LEGACY_RADIUS) {
            int x = Math.floorDiv(current.x(),32)*512, z = Math.floorDiv(current.z(),32)*512;
            batch = new dev.twob2tkit.runtime.api.MapTaskView.Area(x,z,x+512,z+512);
        }
        var next = current == null ? null : new BlockPos(current.x() * 16 + 8, 0, current.z() * 16 + 8);
        String reason = preview ? current == null ? "当前边界内的区块已确认"
            : "按当前位置预览最近的未确认区块；实际运行时会先核对缓存"
            : !active ? "已保存的覆盖进度" : current == null ? "等待当前批次核对或返回圆心"
            : batch == null ? "优先前往离当前位置最近的未确认区块"
            : "优先补齐当前 512×512 分区内最近的缺块；完成后再选其它分区";
        var tiles = viewport == null ? new SceneryMapTiles.Tiles(java.util.List.of(),1) : SceneryMapTiles.missing(plan, viewport);
        return new dev.twob2tkit.runtime.api.MapTaskView.Scenery(plan.centreX, plan.centreZ, plan.radius,
            plan.confirmed(), plan.total(), batch, next, reason, tiles.areas(), tiles.step());
    }

	boolean active() { return active; }
	String status() { return status; }

	boolean start(Minecraft c, int radius, boolean resume, double x, double z, boolean expand) {
		if (c.player == null || c.level == null || c.gameMode == null) return false;
		try {
			cacheBackend = SceneryCache.create();
			String world = world(c), cache = cacheBackend.connect(c.level);
			view = serverView.read(c.getConnection(), c.options.renderDistance().get());
			Path progress = c.gameDirectory.toPath().resolve("config/twob2tkit/scenery-progress.json");
			SceneryCoverage plan = (resume || expand) ? SceneryProgress.read(progress, world, cache) : new SceneryCoverage(x, z, radius);
			if (expand) plan=plan.expanded(radius);
			plan.clipTo(borderBounds(c));
			if (plan.total()==0) { say(c,"所选范围在世界边界内没有可安全到达的区块"); return false; }
			if (resume && plan.complete()) { say(c,"上次任务的边界内范围已完成"); return false; }
			if (plan.skippedOutside()>0) say(c,"所选范围跨过世界边界，将跳过边界外的 "+plan.skippedOutside()+" 个区块");
			if (c.player.getY() > SceneryFlightPolicy.MAX_Y) throw new IllegalStateException("请先降低至 Y512 以下再开始");
			// Reuse the tested flight lease and its single recovery receipt; mining and scenery are mutually exclusive.
			flight.prepare(c.gameDirectory.toPath().resolve("config/twob2tkit/area-flight-speed.bak"));
			String error = flight.acquire(c.player); if (error != null) throw new IllegalStateException(error);
			this.coverage = plan; target = null;
			reusePending.clear(); reuseChecked = 0;
			batchX=batchZ=null;
			reuseTotal=plan.chunks().size();
			reuseScan = cacheBackend.supportsReuse() && plan.radius<=SceneryCoverage.LEGACY_RADIUS ? plan.chunks().iterator() : null; this.world = world; this.cache = cache; this.progress = progress; level = c.level;
			ticks = scan = waitTicks = idleTicks = lastCheckpointTick = 0; quiet.reset(); lastCovered = plan.confirmed();
			observed.clear(); goalKey = ""; bestDistance = Double.POSITIVE_INFINITY; altitude = Math.max(160, c.player.getY());
			active = true;
			SceneryProgress.write(progress, world, cache, coverage);
			say(c, "已" + (resume ? "继续" : "开始") + "风景预加载（" + cacheBackend.name() + "）：圆心 " + Math.round(plan.centreX) + ", " + Math.round(plan.centreZ)
				+ "，半径 " + plan.radius + " 格，共 " + plan.total() + " 区块；服务端视距 " + view.server() + " 区块，完成后飞回圆心附近的安全范围");
			engine.fileLog(c, "scenery-start backend=" + cacheBackend.name() + " view=" + view + " resume=" + resume + " radius=" + plan.radius + " chunks=" + plan.total());
			return true;
		} catch (Exception | LinkageError error) {
			if (active) stop(c, error.getMessage());
			else { closeFlight(c); say(c, "无法开始：" + error.getMessage()); }
			return false;
		}
	}
	void tick(Minecraft c) {
		if (!active) return;
		if (c.player == null || c.level != level || c.gameMode == null) { stop(c, "世界或连接已变化，进度已保留"); return; }
		try {
			ticks++; releaseMovement(c); look = null;
			String error = flight.acquire(c.player); if (error != null) throw new IllegalStateException(error);
			cacheBackend.check();
			if (coverage.clipTo(borderBounds(c))) {
				batchX=batchZ=null;
				target=null;
				say(c,"世界边界已变化，将跳过边界外的 "+coverage.skippedOutside()+" 个区块");
			}
			if (coverage.total()==0) { stop(c,"世界边界内已无可达目标"); return; }
			SceneryServerView.Limits latestView = serverView.read(c.getConnection(), c.options.renderDistance().get());
			if (!latestView.equals(view)) { view = latestView; scan = 0; engine.fileLog(c, "scenery-server-view " + view); }
			if (c.gui.screen() != null) { flight.hover(); show(c, "界面打开，已悬停；关闭界面继续"); return; }
			if (checkSaved(c)) return;
			target = nextTarget(c);
			if (checkSaved(c) || target!=null && !coverage.needs(target.x(),target.z())) return;
			var border=c.level.getWorldBorder();
			double x = target == null ? returnCoordinate(coverage.centreX,border.getMinX(),border.getMaxX()) : target.x() * 16.0 + 8;
			double z = target == null ? returnCoordinate(coverage.centreZ,border.getMinZ(),border.getMaxZ()) : target.z() * 16.0 + 8;
			double dx = x - c.player.getX(), dz = z - c.player.getZ();
			Integer surface = terrain(c, dx, dz);
			if (surface == null) { waiting(c, "等待前方地形数据，不飞进未知障碍"); return; }
			altitude = SceneryFlightPolicy.altitude(c.player.getY(), surface, altitude);
			if (c.player.isInWater() || c.player.isInLava()) altitude = Math.max(altitude, c.player.getY() + 48);
			if (altitude > SceneryFlightPolicy.MAX_Y) throw new IllegalStateException("前方地形需要超过 Y512，已保留漏块并停飞");
			if (quiet.observe(coverage.submitted() > 0, cacheBackend.idle())) {
				cacheBackend.batchCommitted();
				coverage.commitBatch();
				checkpointBatch();
				engine.fileLog(c, "scenery-confirmed chunks=" + coverage.confirmed() + "/" + coverage.total());
			}
			boolean draining = SceneryCapturePolicy.drain(coverage.submitted(), cacheBackend.queued(), target == null, coverage.complete());
			if (!draining) observe(c, target);
			var input = SceneryFlightPolicy.input(dx, dz, altitude - c.player.getY(), c.player.getDeltaMovement().y, c.player.getYRot());
			if (!input.up() && draining) { waiting(c, "等待 " + cacheBackend.name() + " 缓存写入与复核，再继续飞行"); return; }
			if (coverage.complete() && target == null && Math.hypot(dx, dz) < 1.5 && !input.up() && Math.abs(c.player.getDeltaMovement().y) < .08) {
				stop(c, "完成：" + coverage.total() + " 区块已有有效的 " + cacheBackend.name() + " 缓存，已回到圆心附近的安全范围；保留飞行供你接管"); return;
			}
			if (!input.forward() && !input.up() && !coverage.complete()) { waiting(c, captureWait(c, target)); return; }
			waitTicks = 0;
			if (!safeStep(c, input)) throw new IllegalStateException(input.up() ? "头顶有障碍，未挖掘；请到露天位置继续" : "飞行通道受阻，已悬停并保留进度");
			look = new RotationAim.Look(input.yaw(), 0); RotationAim.apply(c.player, look);
			flight.speed(input.speed()); c.options.keyUp.setDown(input.forward()); c.options.keyJump.setDown(input.up());
			String key = target == null ? "return" : target.key() + "";
			double distance = Math.hypot(dx, dz) + Math.max(0, altitude - c.player.getY());
			int covered = coverage.confirmed() + coverage.insideSubmitted();
			if (!key.equals(goalKey) || distance < bestDistance - .15 || covered > lastCovered) {
				goalKey = key; bestDistance = distance; idleTicks = 0; lastCovered = covered;
			} else if (++idleTicks >= 600) throw new IllegalStateException("连续 30 秒无前进进展，可能被服务器限速或挡住；未标记完成");
			show(c, input.up() ? "保持离地 48 格，升至 Y" + Math.round(altitude) : coverage.complete() ? "覆盖完成，返回圆心附近" : "前往附近未加载区块");
		} catch (Exception | LinkageError error) {
			engine.fileLog(c, "scenery-error " + error); stop(c, "已停止：" + error.getMessage());
		}
	}
	private static SceneryCoverage.ChunkBounds borderBounds(Minecraft c) {
		var b=c.level.getWorldBorder();
		return SceneryCoverage.ChunkBounds.inside(b.getMinX(),b.getMaxX(),b.getMinZ(),b.getMaxZ());
	}

	static double returnCoordinate(double center,double min,double max) {
		return Math.max(min+3,Math.min(max-3,center));
	}

	/** Large bitmaps are checkpointed periodically; a graceful stop writes the latest batch. */
	private void checkpointBatch() throws java.io.IOException {
		if (coverage.radius>SceneryCoverage.LEGACY_RADIUS && !coverage.complete()
				&& ticks-lastCheckpointTick<600) return;
		SceneryProgress.write(progress,world,cache,coverage);
		lastCheckpointTick=ticks;
	}

	private SceneryCoverage.Chunk nextTarget(Minecraft c) {
		double x=c.player.getX(), z=c.player.getZ();
		if (target!=null && coverage.needs(target.x(),target.z())) return target;
		if (coverage.radius>SceneryCoverage.LEGACY_RADIUS && batchX!=null) {
			var nearby=coverage.nearestInRegion(batchX,batchZ,x,z);
			if (nearby!=null) return nearby;
		}
		var next=coverage.nextNearest(null,x,z);
		if (next!=null && coverage.radius>SceneryCoverage.LEGACY_RADIUS) {
			batchX=Math.floorDiv(next.x(),32);
			batchZ=Math.floorDiv(next.z(),32);
			if (cacheBackend.supportsReuse()) {
				var missing=coverage.missingInRegion(batchX,batchZ);
				reuseChecked=0;
				reuseTotal=missing.size();
				reuseScan=missing.iterator();
			}
		}
		return next;
	}

	/** Read at most 64 cached chunks at once. Valid hits need neither a flight nor a new write. */
	private boolean checkSaved(Minecraft c) throws java.io.IOException {
		if (reuseScan==null) return false;
		for (var it=reusePending.entrySet().iterator();it.hasNext();) {
			var entry=it.next();
			if (!entry.getValue().isDone()) continue;
			if (entry.getValue().getNow(false)) coverage.reuse(entry.getKey());
			reuseChecked++;
			it.remove();
		}
		for (int steps=0;steps<256 && reusePending.size()<64 && reuseScan.hasNext();steps++) {
			var candidate=reuseScan.next();
			if (!coverage.needs(candidate.x(),candidate.z())) { reuseChecked++; continue; }
			var receipt=cacheBackend.hasSaved(candidate);
			if (receipt.isDone()) {
				if (receipt.getNow(false)) coverage.reuse(candidate);
				reuseChecked++;
			} else reusePending.put(candidate,receipt);
		}
		if (!reuseScan.hasNext() && reusePending.isEmpty()) {
			reuseScan=null;
			checkpointBatch();
			engine.fileLog(c,"scenery-cache-reused confirmed="+coverage.confirmed()+"/"+coverage.total());
			return false;
		}
		flight.hover();
		show(c,"检查本批 Bobby 缓存 "+reuseChecked+"/"+reuseTotal);
		return true;
	}

	private void observe(Minecraft c, SceneryCoverage.Chunk target) {
		int accepted = 0;
		if (target != null && observeOne(c, target.x(), target.z())) accepted++;
		int radius = view.scan();
		int width = radius * 2 + 1, total = width * width;
		int cx = c.player.blockPosition().getX() >> 4, cz = c.player.blockPosition().getZ() >> 4;
		for (int checks = 0; checks < 128 && accepted < 4 && coverage.submitted() < 32; checks++) {
			int index = scan++ % total;
			if (observeOne(c, cx + index % width - radius, cz + index / width - radius)) accepted++;
		}
		if (ticks % 100 == 0) observed.entrySet().removeIf(e -> ticks - e.getValue().tick > 100);
	}
	private boolean observeOne(Minecraft c, int x, int z) {
		if (!coverage.needs(x, z)) return false;
		long key = new SceneryCoverage.Chunk(x, z).key();
		LevelChunk chunk = c.level.getChunkSource().getChunk(x, z, ChunkStatus.FULL, false);
		if (!cacheBackend.isReal(chunk) || !c.level.getLightEngine().lightOnInColumn(SceneryCapturePolicy.lightColumnKey(x, z))) { observed.remove(key); return false; }
		Observed first = observed.get(key);
		if (first == null || first.chunk != chunk) { observed.put(key, new Observed(chunk, ticks)); return false; }
		if (!SceneryCapturePolicy.ready(true, true, first.chunk == chunk, ticks - first.tick)) return false;
		if (!cacheBackend.accept(chunk)) return false;
		coverage.accepted(x, z); observed.remove(key); return true;
	}
	private Integer terrain(Minecraft c, double dx, double dz) {
		double distance = Math.hypot(dx, dz), ux = distance > .01 ? dx / distance : 0, uz = distance > .01 ? dz / distance : 0;
		int highest = c.level.getMinY();
		for (int ahead = 0; ahead <= Math.min(12, distance); ahead += 4) for (int side : new int[]{-4, 0, 4}) {
			int x = (int)Math.floor(c.player.getX() + ux * ahead - uz * side);
			int z = (int)Math.floor(c.player.getZ() + uz * ahead + ux * side);
			LevelChunk chunk = c.level.getChunkSource().getChunk(x >> 4, z >> 4, ChunkStatus.FULL, false);
			if (!cacheBackend.isReal(chunk)) return null;
			highest = Math.max(highest, chunk.getHeight(Heightmap.Types.WORLD_SURFACE, x & 15, z & 15) + 1);
		}
		return highest;
	}
	private boolean safeStep(Minecraft c, SceneryFlightPolicy.Input input) {
		double dx = input.forward() ? -Math.sin(Math.toRadians(input.yaw())) * 1.5 : 0;
		double dz = input.forward() ? Math.cos(Math.toRadians(input.yaw())) * 1.5 : 0;
		double dy = input.up() ? 1.2 : 0;
		var box = c.player.getBoundingBox().expandTowards(dx, dy, dz).inflate(.05);
		if (!c.level.getWorldBorder().isWithinBounds(box) || !c.level.noCollision(c.player, box)) return false;
		for (BlockPos b : BlockPos.betweenClosed(BlockPos.containing(box.minX, box.minY, box.minZ), BlockPos.containing(box.maxX, box.maxY, box.maxZ)))
			if (!cacheBackend.isReal(c.level.getChunkSource().getChunk(b.getX() >> 4, b.getZ() >> 4, ChunkStatus.FULL, false))
				|| !input.up() && !c.level.getFluidState(b).isEmpty()) return false;
		return true;
	}
	private void waiting(Minecraft c, String reason) {
		flight.hover();
		show(c, reason);
		if (++waitTicks >= 2400) throw new IllegalStateException("等待两分钟仍未完成：" + reason + "；可稍后继续");
	}
	private String captureWait(Minecraft c, SceneryCoverage.Chunk target) {
		if (target == null || !coverage.needs(target.x(), target.z())) return "当前区块已接收，稳定飞行后继续";
		LevelChunk chunk = c.level.getChunkSource().getChunk(target.x(), target.z(), ChunkStatus.FULL, false);
		if (chunk == null) return "等待服务器下发目标区块 " + target.x() + ", " + target.z();
		if (!cacheBackend.isReal(chunk)) return "目标目前仅有旧缓存，等待服务器真实区块";
		if (!c.level.getLightEngine().lightOnInColumn(SceneryCapturePolicy.lightColumnKey(target.x(), target.z()))) return "等待目标区块光照数据";
		Observed first = observed.get(target.key());
		if (first == null || first.chunk != chunk || ticks - first.tick < 10) return "确认真实区块与光照稳定，随后保存";
		return "等待 " + cacheBackend.name() + " 接收当前区块";
	}
	private void show(Minecraft c, String action) {
		status = action + " · " + (coverage.confirmed() + coverage.insideSubmitted()) + "/" + coverage.total() + " 区块 · 服务端 " + view.server();
		if (ticks % 10 == 0) c.gui.hud.setOverlayMessage(Component.literal("[风景] " + status).withColor(0x55FFFF), false);
		if (ticks % 100 == 0) {
			engine.fileLog(c, "scenery-state backend=" + cacheBackend.name() + " view=" + view + " " + status + " y=" + c.player.getY() + " pending=" + coverage.submitted());
			if (target != null) {
				LevelChunk chunk = c.level.getChunkSource().getChunk(target.x(), target.z(), ChunkStatus.FULL, false);
				long lightKey = SceneryCapturePolicy.lightColumnKey(target.x(), target.z());
				Observed first = observed.get(target.key());
				engine.fileLog(c, "scenery-capture target=" + target + " chunk=" + (chunk == null ? "missing" : chunk.getClass().getSimpleName())
					+ " real=" + cacheBackend.isReal(chunk) + " light=" + c.level.getLightEngine().lightOnInColumn(lightKey)
					+ " lightKey=" + lightKey + " stableTicks=" + (first == null || first.chunk != chunk ? 0 : ticks - first.tick)
					+ " backendQueued=" + cacheBackend.queued());
			}
		}
	}
	void stop(Minecraft c, String reason) {
		if (!active) return;
		active = false; look = null; releaseMovement(c);
		try { SceneryProgress.write(progress, world, cache, coverage); }
		catch (Exception error) { reason += "；进度保存失败：" + error.getMessage(); }
		closeFlight(c); cacheBackend.close(); observed.clear(); reuseScan=null; reusePending.clear();
		if (c.options != null) net.minecraft.client.KeyMapping.setAll();
		say(c, reason);
		engine.fileLog(c, "scenery-stop confirmed=" + coverage.confirmed() + "/" + coverage.total() + " reason=" + reason);
	}
	private void closeFlight(Minecraft c) {
		if (c.player != null && c.level != null && !c.player.onGround()) flight.closeKeepingFlight(); else flight.close();
	}
	void reapply(Minecraft c) { if (look != null && active && c.player != null && c.gui.screen() == null) RotationAim.apply(c.player, look); }
	private void say(Minecraft c, String message) {
		status = message;
		if (c.player != null) c.player.sendSystemMessage(Component.literal("[风景预加载] " + message));
	}
	private static void releaseMovement(Minecraft c) {
		if (c.options == null) return;
		c.options.keyUp.setDown(false); c.options.keyDown.setDown(false); c.options.keyLeft.setDown(false); c.options.keyRight.setDown(false);
		c.options.keyJump.setDown(false); c.options.keyShift.setDown(false); c.options.keySprint.setDown(false); c.options.keyAttack.setDown(false);
		if (c.player != null) c.player.setSprinting(false);
	}
	private static String world(Minecraft c) {
		String server = c.getCurrentServer() != null ? c.getCurrentServer().ip : c.getSingleplayerServer() != null
			? c.getSingleplayerServer().getWorldPath(net.minecraft.world.level.storage.LevelResource.ROOT).toString() : "unknown";
		return server + "|" + c.level.dimension().identifier();
	}
}
