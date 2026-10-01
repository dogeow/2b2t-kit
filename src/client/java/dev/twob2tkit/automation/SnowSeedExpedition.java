package dev.twob2tkit.automation;

import com.google.gson.JsonArray;
import com.google.gson.JsonObject;
import dev.twob2tkit.KitClient;
import dev.twob2tkit.KitConfig;
import dev.twob2tkit.structure.OverworldSnowLocator;
import net.minecraft.client.Minecraft;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.StandardOpenOption;
import java.security.MessageDigest;
import java.util.Iterator;
import java.util.LinkedHashMap;
import java.util.Map;
import java.util.UUID;

/** Host-owned permits for seed-guided snow travel and the unique return home. */
final class SnowSeedExpedition {
	static final int PROTOCOL = 1;
	private static final long PERMIT_MS = 90L * 60L * 1000L;
	private static final int MAX_PERMITS = 256;
	private static final Map<String, Permit> PERMITS = new LinkedHashMap<>();
	private record ReturnTarget(double x, double y, double z, String dimension, String source) {}

	private record Permit(String token, String routeId, String world, String job,
		double targetX, double targetY, double targetZ,
		ReturnTarget home, long expiresAt,
		boolean outboundUsed, boolean outboundArrived,
		boolean outboundTerminated, boolean returnUsed) {
		Permit withOutboundUsed() { return new Permit(token, routeId, world, job,
			targetX, targetY, targetZ, home, expiresAt, true, outboundArrived,
			outboundTerminated, returnUsed); }
		Permit withOutboundArrived(long renewedExpiry) { return new Permit(token, routeId, world, job,
			targetX, targetY, targetZ, home, renewedExpiry, outboundUsed, true, true, returnUsed); }
		Permit withOutboundTerminated(long renewedExpiry) { return new Permit(token, routeId, world, job,
			targetX, targetY, targetZ, home, renewedExpiry, outboundUsed, false, true, returnUsed); }
		Permit withReturnUsed() { return new Permit(token, routeId, world, job,
			targetX, targetY, targetZ, home, expiresAt, outboundUsed, outboundArrived,
			outboundTerminated, true); }
	}

	private SnowSeedExpedition() {}

	static JsonObject candidates(Minecraft client, JsonObject request, String world,
		double taskOriginX, double taskOriginY, double taskOriginZ) {
		if (client.player == null || client.level == null || KitClient.seedScout() == null)
			throw new IllegalStateException("Snow seed locator requires a loaded world");
		String dimension = client.level.dimension().identifier().toString();
		if (!"minecraft:overworld".equals(dimension))
			throw new IllegalStateException("Snow seed locator is available only in the Overworld");
		if (!Double.isFinite(taskOriginX)||!Double.isFinite(taskOriginY)||!Double.isFinite(taskOriginZ))
			throw new IllegalStateException("The host-bound material search origin is invalid");
		KitConfig.HomeTarget configuredHome = KitClient.config().homeTarget();
		boolean useHome = eligibleHome(configuredHome,dimension);
		ReturnTarget home = useHome
			? new ReturnTarget(configuredHome.x(), safeCruiseY(configuredHome.cruiseY(),taskOriginY), configuredHome.z(),
				dimension, "saved_home")
			: new ReturnTarget(taskOriginX, safeCruiseY(taskOriginY,200),
				taskOriginZ, dimension, "task_search_origin");
		int cursor = exactInt(request, "cursor", 0);
		int budget = exactInt(request, "budget", 64);
		int radius = KitConfig.clampStructureRadius(KitClient.config().structureSearchRadius);
		int originX = (int)Math.floor(home.x());
		int originZ = (int)Math.floor(home.z());
		long now=System.currentTimeMillis();cleanup(now);
		String job=str(request,"task_session");
		if(PERMITS.values().stream().anyMatch(permit->permit.world.equals(world)
				&&permit.job.equals(job)&&permit.outboundUsed))
			throw new IllegalStateException("A snow expedition route is still active or waiting to return");
		OverworldSnowLocator.Batch batch;
		try{
			batch=KitClient.seedScout().snowyBiomeCandidates(originX,originZ,radius,cursor,budget);
		}catch(OverworldSnowLocator.SamplerUnavailable error){
			KitClient.LOGGER.error("[Snow Seed] vanilla biome sampler unavailable; using loaded server survey",error);
			return samplerUnavailableReply();
		}
		reservePermitCapacity(batch.candidates().size());
		JsonArray rows = new JsonArray();
		for (var candidate : batch.candidates()) {
			String token = UUID.randomUUID().toString();
			String routeId = UUID.randomUUID().toString();
			double targetY = home.y();
			long expires = System.currentTimeMillis() + PERMIT_MS;
			Permit permit = new Permit(token, routeId, world, str(request, "task_session"),
				candidate.x() + .5, targetY, candidate.z() + .5, home, expires,
				false, false, false, false);
			PERMITS.put(token, permit);
			JsonObject row = new JsonObject();
			row.addProperty("sample_cursor", candidate.cursor());
			row.addProperty("x", candidate.x());
			row.addProperty("z", candidate.z());
			row.addProperty("sample_y", candidate.sampleY());
			row.addProperty("biome", candidate.biome());
			row.addProperty("distance", candidate.distance());
			row.addProperty("token", token);
			row.addProperty("route_id", routeId);
			row.addProperty("expires_at", expires);
			row.add("target", doubles(permit.targetX, permit.targetY, permit.targetZ));
			rows.add(row);
			record(client, permit, "candidate_issued", candidate.biome());
		}
		JsonObject result = new JsonObject();
		result.addProperty("protocol", PROTOCOL);
		result.addProperty("available",true);
		result.addProperty("cursor", batch.cursor());
		result.addProperty("next_cursor", batch.nextCursor());
		result.addProperty("processed", batch.processed());
		result.addProperty("total", batch.total());
		result.addProperty("done", batch.done());
		result.addProperty("radius", radius);
		result.addProperty("stride", OverworldSnowLocator.STRIDE);
		result.add("candidates", rows);
		return result;
	}

	static JsonObject samplerUnavailableReply(){
		JsonObject result=new JsonObject();result.addProperty("protocol",PROTOCOL);
		result.addProperty("available",false);result.addProperty("reason","sampler_unavailable");
		return result;
	}

	/** Mutates only the target field after validating an exact host-owned permit. */
	static void authorizeNavigate(Minecraft client, JsonObject request, String world) {
		String token = str(request, "snow_expedition_token");
		Permit permit = PERMITS.get(token);
		long now = System.currentTimeMillis();
		if (permit == null || now > permit.expiresAt || !permit.world.equals(world)
			|| permit.job.isBlank() || !permit.job.equals(str(request, "task_session")))
			throw new IllegalStateException("Snow expedition permit is missing, expired, or belongs to another task");
		boolean returning = request.has("snow_expedition_return")
			&& request.get("snow_expedition_return").getAsBoolean();
		if (returning) {
			if (!permit.outboundTerminated || permit.returnUsed)
				throw new IllegalStateException("Snow expedition cannot return before a confirmed outbound arrival");
			KitConfig.HomeTarget current = KitClient.config().homeTarget();
			if ("saved_home".equals(permit.home.source())
				&& (current == null || !sameHome(permit.home, current)))
				throw new IllegalStateException("The unique home changed after the snow route was authorized");
			request.add("target", doubles(permit.home.x(), permit.home.y(), permit.home.z()));
			PERMITS.put(token, permit.withReturnUsed());
			record(client, permit, "return_started", "host_home");
			return;
		}
		if (permit.outboundUsed)
			throw new IllegalStateException("Snow expedition outbound permit was already spent");
		JsonArray target = request.getAsJsonArray("target");
		if (!sameTarget(target, permit.targetX, permit.targetY, permit.targetZ))
			throw new IllegalStateException("Snow expedition target does not match the seed candidate permit");
		PERMITS.put(token, permit.withOutboundUsed());
		record(client, permit, "outbound_started", "candidate");
	}

	static void navigationFinished(Minecraft client, JsonObject request, String world, boolean arrived) {
		if (request == null || !request.has("snow_expedition_token")) return;
		String token = str(request, "snow_expedition_token");
		Permit permit = PERMITS.get(token);
		if (permit == null) return;
		boolean returning = request.has("snow_expedition_return")
			&& request.get("snow_expedition_return").getAsBoolean();
		JsonArray target=request.getAsJsonArray("target");
		boolean scope=permit.world.equals(world)&&permit.job.equals(str(request,"task_session"));
		boolean targetMatches=returning
			?sameTarget(target,permit.home.x(),permit.home.y(),permit.home.z())
			:sameTarget(target,permit.targetX,permit.targetY,permit.targetZ);
		if(!settlementAllowed(returning,navigationOperation(request),scope,targetMatches,
			permit.outboundUsed,permit.outboundTerminated,permit.returnUsed))return;
		if(returning){
			record(client,permit,arrived?"home_arrived":"return_stopped",
				arrived?"arrived":"stopped");
			PERMITS.remove(token);return;
		}
		if (arrived) {
			permit = permit.withOutboundArrived(System.currentTimeMillis()+PERMIT_MS);
			PERMITS.put(token, permit);
		}
		else {
			permit=permit.withOutboundTerminated(System.currentTimeMillis()+PERMIT_MS);
			PERMITS.put(token,permit);
		}
		record(client,permit,arrived?"candidate_arrived":"outbound_stopped",
			arrived?"arrived":"stopped");
	}

	/** Re-check the exact in-flight request when the player is beyond the old worksite radius. */
	static boolean activeNavigation(JsonObject request, String world) {
		if (request == null || !navigationOperation(request)
			|| !request.has("snow_expedition_token")) return false;
		Permit permit = PERMITS.get(str(request,"snow_expedition_token"));
		if (permit == null || !permit.world.equals(world)
			|| !permit.job.equals(str(request,"task_session"))) return false;
		boolean returning=request.has("snow_expedition_return")
			&& request.get("snow_expedition_return").getAsBoolean();
		JsonArray target=request.getAsJsonArray("target");
		if (returning) {
			// The external return request intentionally carries no coordinates.
			// Permit it through the first guard only when outbound arrival is known;
			// authorizeNavigate immediately injects the host-owned target.
			if (target == null) return permit.outboundTerminated && !permit.returnUsed;
			return permit.returnUsed
				&& sameTarget(target,permit.home.x(),permit.home.y(),permit.home.z());
		}
		return permit.outboundUsed && !permit.outboundTerminated
			&& sameTarget(target,permit.targetX,permit.targetY,permit.targetZ);
	}

	static boolean pendingReturn(JsonObject request,String world){
		if(request==null||!navigationOperation(request)
				||!request.has("snow_expedition_token")
				||!request.has("snow_expedition_return")
				||!request.get("snow_expedition_return").getAsBoolean()
				||request.has("target"))return false;
		Permit permit=PERMITS.get(str(request,"snow_expedition_token"));
		return permit!=null&&System.currentTimeMillis()<=permit.expiresAt
			&&permit.world.equals(world)&&permit.job.equals(str(request,"task_session"))
			&&permit.outboundTerminated&&!permit.returnUsed;
	}
	static boolean navigationOperation(JsonObject request){
		return request!=null&&"navigate".equals(str(request,"op"));
	}
	static boolean settlementAllowed(boolean returning,boolean navigate,
		boolean scopeMatches,boolean targetMatches,boolean outboundUsed,
		boolean outboundTerminated,boolean returnUsed){
		if(!navigate||!scopeMatches||!targetMatches)return false;
		return returning?returnUsed:outboundUsed&&!outboundTerminated;
	}

	private static boolean sameHome(ReturnTarget left, KitConfig.HomeTarget right) {
		return "saved_home".equals(left.source())
			&& Double.compare(left.x(), right.x()) == 0
			&& Double.compare(left.z(), right.z()) == 0
			&& Double.compare(left.y(), safeCruiseY(right.cruiseY(),left.y())) == 0
			&& (normalizedDimension(right.dimension()).isEmpty()
				|| left.dimension().equals(normalizedDimension(right.dimension())));
	}

	static double safeCruiseY(double requested, double fallback) {
		double value=Double.isFinite(requested)?requested:fallback;
		if(!Double.isFinite(value))value=200;
		return Math.max(160,Math.min(316,value));
	}

	static boolean safeHorizontal(double x,double z) {
		return Double.isFinite(x)&&Double.isFinite(z)
			&&Math.abs(x)<=29_999_984&&Math.abs(z)<=29_999_984;
	}

	static boolean eligibleHome(KitConfig.HomeTarget home,String dimension) {
		if(home==null||!safeHorizontal(home.x(),home.z()))return false;
		String stored=normalizedDimension(home.dimension());
		return stored.isEmpty()||stored.equals(dimension);
	}

	private static String normalizedDimension(String raw) {
		if(raw==null||raw.isBlank())return "";
		String value=raw.trim().toLowerCase(java.util.Locale.ROOT);
		if(value.contains("nether"))return "minecraft:the_nether";
		if(value.endsWith("the_end")||value.equals("end"))return "minecraft:the_end";
		if(value.endsWith("overworld")||value.equals("world"))return "minecraft:overworld";
		return raw.trim();
	}

	private static boolean sameTarget(JsonArray target, double x, double y, double z) {
		return target != null && target.size() == 3
			&& Double.compare(target.get(0).getAsDouble(), x) == 0
			&& Double.compare(target.get(1).getAsDouble(), y) == 0
			&& Double.compare(target.get(2).getAsDouble(), z) == 0;
	}

	private static int exactInt(JsonObject request, String key, int fallback) {
		if (!request.has(key)) return fallback;
		double value = request.get(key).getAsDouble();
		if (!Double.isFinite(value) || value != Math.rint(value)
			|| value < Integer.MIN_VALUE || value > Integer.MAX_VALUE)
			throw new IllegalArgumentException("Snow seed " + key + " must be an integer");
		return (int)value;
	}

	private static JsonArray doubles(double... values) {
		JsonArray result = new JsonArray();
		for (double value : values) result.add(value);
		return result;
	}

	private static String str(JsonObject object, String key) {
		return object != null && object.has(key) && object.get(key).isJsonPrimitive()
			? object.get(key).getAsString() : "";
	}

	private static void cleanup(long now) {
		PERMITS.entrySet().removeIf(entry -> {
			Permit permit=entry.getValue();
			return cleanupEligible(now>permit.expiresAt,permit.outboundUsed,
				permit.outboundTerminated,permit.returnUsed);
		});
	}
	static boolean cleanupEligible(boolean expired,boolean outboundUsed,
		boolean outboundTerminated,boolean returnUsed){
		boolean inFlight=outboundUsed&&!outboundTerminated||returnUsed;
		return expired&&!inFlight;
	}

	private static void reservePermitCapacity(int incoming) {
		long protectedCount=PERMITS.values().stream().filter(permit->permit.outboundUsed).count();
		if(!capacityPossible((int)protectedCount,incoming))
			throw new IllegalStateException("Snow expedition permit capacity is occupied by active routes");
		Iterator<Map.Entry<String,Permit>> entries=PERMITS.entrySet().iterator();
		while(PERMITS.size()+incoming>MAX_PERMITS&&entries.hasNext()){
			var entry=entries.next();if(!entry.getValue().outboundUsed)entries.remove();
		}
		if(PERMITS.size()+incoming>MAX_PERMITS)
			throw new IllegalStateException("Snow expedition permit capacity is unavailable");
	}
	static boolean capacityPossible(int protectedCount,int incoming){
		return protectedCount>=0&&incoming>=0&&incoming<=MAX_PERMITS
			&&protectedCount+incoming<=MAX_PERMITS;
	}
	static void clearWorld(String world){
		if(world==null||world.isBlank())return;
		PERMITS.entrySet().removeIf(entry->entry.getValue().world.equals(world));
	}
	static void clearAll(){PERMITS.clear();}

	private static void record(Minecraft client, Permit permit, String phase, String detail) {
		try {
			JsonObject row = new JsonObject();
			row.addProperty("time", System.currentTimeMillis());
			row.addProperty("route_id", permit.routeId);
			row.addProperty("world_session", permit.world);
			row.addProperty("phase", phase);
			row.addProperty("detail", detail);
			row.addProperty("scenery_boundary", "single_controller_passive_chunk_cache");
			row.add("candidate", doubles(permit.targetX, permit.targetY, permit.targetZ));
			row.add("home", doubles(permit.home.x(), permit.home.y(), permit.home.z()));
			row.addProperty("home_source", permit.home.source());
			var path = client.gameDirectory.toPath().resolve("config/twob2tkit/snow-expedition-routes.jsonl");
			Files.createDirectories(path.getParent());
			Files.writeString(path, row + System.lineSeparator(), StandardCharsets.UTF_8,
				StandardOpenOption.CREATE, StandardOpenOption.APPEND);
		} catch (Exception ignored) {
			// Optional route evidence must never turn a verified navigation into a replay.
		}
	}

	static String tokenFingerprint(String token) {
		try {
			byte[] digest = MessageDigest.getInstance("SHA-256")
				.digest(token.getBytes(StandardCharsets.UTF_8));
			StringBuilder out = new StringBuilder();
			for (int index = 0; index < 8; index++) out.append(String.format("%02x", digest[index]));
			return out.toString();
		} catch (Exception error) {
			throw new IllegalStateException(error);
		}
	}
}
