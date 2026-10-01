package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonArray;
import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import net.minecraft.client.Minecraft;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/**
 * 异步请求纯 HTTP 招数建议，并记录诊断上下文。自动入口没有工具、源码写入或部署能力。
 */
final class BorerAreaThinkAsk {
	private static final Logger LOGGER = LoggerFactory.getLogger("twob2tkit/Borer");
	private static final HttpClient HTTP = HttpClient.newBuilder()
		.connectTimeout(Duration.ofSeconds(8))
		.build();
	private static final AtomicBoolean BUSY = new AtomicBoolean(false);
	private static final String MODEL = "grok-4.5";
	private static final String URL = "https://api.x.ai/v1/chat/completions";
	/** HTTP 返回的只读招数建议。 */
	public static final class Advice {
		final List<BorerAreaThinkPolicy.Move> prefer = new ArrayList<>();
		final List<BorerAreaThinkPolicy.Move> avoid = new ArrayList<>();
		String lesson = "";
	}

	private BorerAreaThinkAsk() {
	}

	/** 询问/部署是否进行中。 */
	static boolean busy() {
		return BUSY.get();
	}

	/** Grok 安装目录。 */
	static Path grokHome(Path userHome, String grokHomeEnv) {
		if (grokHomeEnv != null && !grokHomeEnv.isBlank()) return Path.of(grokHomeEnv);
		if (userHome == null) return null;
		return userHome.resolve(".grok");
	}

	/** Grok 可执行文件路径。 */
	static Path grokBin(Path grokHome, String grokBinEnv) {
		return BorerAreaThinkPolicy.discoverGrokBin(grokHome, grokBinEnv);
	}

	/** Grok 是否已登录。 */
	static boolean grokLoggedIn(Path grokHome) {
		return grokHome != null && Files.isRegularFile(grokHome.resolve("auth.json"));
	}

	/** 本机 Grok CLI 是否可用。 */
	static boolean grokAvailable(Path grokHome, String grokBinEnv) {
		return grokBin(grokHome, grokBinEnv) != null && grokLoggedIn(grokHome);
	}

	/** 本机 Grok CLI 是否可用。 */
	static boolean grokAvailable() {
		return grokAvailable(grokHome(), System.getenv("GROK_BIN"));
	}

	/** 当前是否允许发起询问。 */
	static boolean canAsk(Minecraft client) {
		return !apiKey(client).isEmpty();
	}

	/** 读取本机 API 密钥。 */
	static String apiKey(Minecraft client) {
		String env = System.getenv("XAI_API_KEY");
		if (env != null && !env.isBlank()) return env.trim();
		if (client == null) return "";
		Path path = client.gameDirectory.toPath().resolve("config/twob2tkit/xai.key");
		if (!Files.isRegularFile(path)) return "";
		try {
			List<String> lines = Files.readAllLines(path, StandardCharsets.UTF_8);
			for (String line : lines) {
				String trimmed = line.trim();
				if (!trimmed.isEmpty() && !trimmed.startsWith("#")) return trimmed;
			}
		} catch (Exception ignored) {
			return "";
		}
		return "";
	}

	/** 异步请求只读建议；成功/失败回调。 */
	static void ask(
		Minecraft client,
		String scene,
		String scores,
		String logTail,
		String engineVersion,
		Consumer<String> progress,
		Consumer<Advice> onOk,
		Runnable onFail
	) {
		if (!BUSY.compareAndSet(false, true)) {
			client.execute(onFail);
			return;
		}
		Thread thread = new Thread(
			() -> {
				try {
					askWorker(client, scene, scores, logTail, engineVersion, progress, onOk, onFail);
				} finally {
					BUSY.set(false);
				}
			},
			"twob2tkit-area-think-ask");
		thread.setDaemon(true);
		thread.start();
	}

	/** 记下进度步骤。 */
	private static void note(Minecraft client, Consumer<String> progress, String step) {
		if (progress == null || step == null || step.isBlank()) return;
		client.execute(() -> progress.accept(step));
	}

	/** 组装发给模型的提示词。 */
	static String promptText(String scene, String scores, String logTail) {
		return "You help a Minecraft area-miner recover when stuck. "
			+ "Reply with JSON only: {\"prefer\":[\"MINE_LOOKED\"],\"avoid\":[\"FLY_UP\"],\"lesson\":\"short Chinese\"}. "
			+ "Moves: MINE_LOOKED, MINE_FRONT, RELEASE_FORWARD, DESCEND, FLY_LEVEL, FLY_UP, SKIP_SHAFT. "
			+ "prefer = try first next time; avoid = demote. Do not use tools. No markdown.\n\n"
			+ "scene=" + scene + "\nscores=\n" + nullToEmpty(scores)
			+ "\nlog=\n" + nullToEmpty(logTail);
	}

	/** 组装 HTTP 请求体。 */
	static String requestBody(String scene, String scores, String logTail) {
		JsonObject system = new JsonObject();
		system.addProperty("role", "system");
		system.addProperty("content",
			"You help a Minecraft area-miner recover when stuck. "
				+ "Reply with JSON only: {\"prefer\":[\"MINE_LOOKED\"],\"avoid\":[\"FLY_UP\"],\"lesson\":\"short Chinese\"}. "
				+ "Moves: MINE_LOOKED, MINE_FRONT, RELEASE_FORWARD, DESCEND, FLY_LEVEL, FLY_UP, SKIP_SHAFT. "
				+ "prefer = try first next time; avoid = demote. No markdown.");
		JsonObject user = new JsonObject();
		user.addProperty("role", "user");
		user.addProperty("content",
			"scene=" + scene + "\nscores=\n" + nullToEmpty(scores)
				+ "\nlog=\n" + nullToEmpty(logTail));
		JsonArray messages = new JsonArray();
		messages.add(system);
		messages.add(user);
		JsonObject root = new JsonObject();
		root.addProperty("model", MODEL);
		root.addProperty("temperature", 0.2);
		root.add("messages", messages);
		return root.toString();
	}

	/** 建议是否有效可执行。 */
	static boolean hasAdvice(Advice advice) {
		return advice != null
			&& (!advice.prefer.isEmpty() || !advice.avoid.isEmpty()
			|| (advice.lesson != null && !advice.lesson.isBlank()));
	}

	/** 解析文本为结构化结果。 */
	static Advice parse(String raw) {
		Advice empty = new Advice();
		if (raw == null || raw.isBlank()) return empty;
		try {
			JsonElement element = JsonParser.parseString(BorerAreaThinkPolicy.stripJsonFence(raw));
			if (!element.isJsonObject()) return empty;
			JsonObject root = element.getAsJsonObject();
			if (root.has("type") && root.get("type").isJsonPrimitive()
				&& "error".equals(root.get("type").getAsString())) {
				return empty;
			}
			if (root.has("choices") && root.get("choices").isJsonArray()) {
				String content = root.getAsJsonArray("choices")
					.get(0).getAsJsonObject()
					.getAsJsonObject("message")
					.get("content").getAsString();
				return parseAdviceJson(content);
			}
			if (root.has("text")) {
				JsonElement text = root.get("text");
				if (text.isJsonPrimitive()) return parseAdviceJson(text.getAsString());
				if (text.isJsonObject()) return parseAdviceObject(text.getAsJsonObject());
			}
			if (root.has("prefer") || root.has("avoid") || root.has("lesson")) {
				return parseAdviceObject(root);
			}
		} catch (RuntimeException ignored) {
			return empty;
		}
		return empty;
	}

	/** 后台：记录上下文，通过无工具的 HTTP 请求只读建议。 */
	private static void askWorker(
		Minecraft client,
		String scene,
		String scores,
		String logTail,
		String engineVersion,
		Consumer<String> progress,
		Consumer<Advice> onOk,
		Runnable onFail
	) {
		try {
			Path dir = client.gameDirectory.toPath().resolve("config/twob2tkit");
			Files.createDirectories(dir);
			writeAsk(dir.resolve("area-think-ask.json"), scene, scores, logTail, engineVersion);
			String key = apiKey(client);
			if (!key.isEmpty()) {
				note(client, progress, "正在请求 xAI");
				Advice advice = askHttp(key, scene, scores, logTail);
				if (hasAdvice(advice)) {
					note(client, progress, "已收到 xAI 回复");
					client.execute(() -> onOk.accept(advice));
					return;
				}
			}
		} catch (RuntimeException | IOException exception) {
			LOGGER.warn("area-think ask failed: {}", exception.toString());
		}
		client.execute(onFail);
	}

	/** 走 HTTP 问模型拿建议。 */
	private static Advice askHttp(String key, String scene, String scores, String logTail) {
		String body = requestBody(scene, scores, logTail);
		HttpRequest request = HttpRequest.newBuilder(URI.create(URL))
			.timeout(Duration.ofSeconds(20))
			.header("Authorization", "Bearer " + key)
			.header("Content-Type", "application/json")
			.POST(HttpRequest.BodyPublishers.ofString(body, StandardCharsets.UTF_8))
			.build();
		try {
			HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
			if (response.statusCode() >= 300) {
				LOGGER.warn("area-think AI ask failed: http {}", response.statusCode());
				return new Advice();
			}
			return parse(response.body());
		} catch (Exception exception) {
			LOGGER.warn("area-think AI ask failed: {}", exception.toString());
			return new Advice();
		}
	}

	/** 把本次提问上下文写成 area-think-ask.json。 */
	private static void writeAsk(
		Path path, String scene, String scores, String logTail, String version
	) {
		try {
			JsonObject root = new JsonObject();
			root.addProperty("scene", nullToEmpty(scene));
			root.addProperty("scores", nullToEmpty(scores));
			root.addProperty("log", nullToEmpty(logTail));
			root.addProperty("mode", "read_only_advice");
			root.addProperty("version", nullToEmpty(version));
			Files.writeString(path, root.toString(), StandardCharsets.UTF_8);
		} catch (IOException ignored) {
		}
	}

	/** 解析建议 JSON。 */
	private static Advice parseAdviceJson(String raw) {
		if (raw == null || raw.isBlank()) return new Advice();
		try {
			JsonElement element = JsonParser.parseString(BorerAreaThinkPolicy.stripJsonFence(raw));
			if (!element.isJsonObject()) return new Advice();
			return parseAdviceObject(element.getAsJsonObject());
		} catch (RuntimeException ignored) {
			return new Advice();
		}
	}

	/** 从 JSON 对象取出建议字段。 */
	private static Advice parseAdviceObject(JsonObject json) {
		Advice advice = new Advice();
		addMoves(json.get("prefer"), advice.prefer);
		addMoves(json.get("avoid"), advice.avoid);
		if (json.has("lesson") && json.get("lesson").isJsonPrimitive()) {
			advice.lesson = json.get("lesson").getAsString();
		}
		return advice;
	}

	/** 把 JSON 元素里的招数填进列表。 */
	private static void addMoves(JsonElement element, List<BorerAreaThinkPolicy.Move> into) {
		if (element == null || !element.isJsonArray()) return;
		for (JsonElement item : element.getAsJsonArray()) {
			if (!item.isJsonPrimitive()) continue;
			BorerAreaThinkPolicy.Move move = BorerAreaThinkPolicy.parseMove(item.getAsString());
			if (move != null) into.add(move);
		}
	}

	/** Grok 安装目录。 */
	private static Path grokHome() {
		return BorerAreaThinkPolicy.discoverGrokHome(
			System.getenv("GROK_HOME"),
			System.getenv("HOME"),
			System.getProperty("user.home", ""));
	}

	/** 探测用短文本。 */
	static String probeText() {
		Path home = grokHome();
		Path bin = grokBin(home, System.getenv("GROK_BIN"));
		boolean auth = home != null && Files.isRegularFile(home.resolve("auth.json"));
		return "home=" + home
			+ " bin=" + bin
			+ " auth=" + auth
			+ " HOME=" + System.getenv("HOME")
			+ " user.home=" + System.getProperty("user.home", "");
	}

	/** null 转空串。 */
	private static String nullToEmpty(String text) {
		return text == null ? "" : text;
	}

	/** 截断过长文本。 */
	private static String clip(String text, int max) {
		if (text == null) return "";
		String trimmed = text.trim();
		if (trimmed.length() <= max) return trimmed;
		return trimmed.substring(0, max);
	}
}
