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
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;

/**
 * 合适时机异步问本机已登录的 Grok。卡住且招数用尽时让 Grok 改引擎代码，
 * 再由本类编译复制 jar。不在游戏线程里等。
 */
final class BorerAreaThinkAsk {
	private static final Logger LOGGER = LoggerFactory.getLogger("2b2t-kit/Borer");
	private static final HttpClient HTTP = HttpClient.newBuilder()
		.connectTimeout(Duration.ofSeconds(8))
		.build();
	private static final AtomicBoolean BUSY = new AtomicBoolean(false);
	private static final String MODEL = "grok-4.5";
	private static final String URL = "https://api.x.ai/v1/chat/completions";
	private static final int GROK_TIMEOUT_SECONDS = 60;
	private static final int GROK_PATCH_TIMEOUT_SECONDS = 480;
	static final String ADVICE_SCHEMA = "{\"type\":\"object\",\"properties\":{"
		+ "\"prefer\":{\"type\":\"array\",\"items\":{\"type\":\"string\"}},"
		+ "\"avoid\":{\"type\":\"array\",\"items\":{\"type\":\"string\"}},"
		+ "\"lesson\":{\"type\":\"string\"},"
		+ "\"patched\":{\"type\":\"boolean\"},"
		+ "\"deployed\":{\"type\":\"boolean\"},"
		+ "\"version\":{\"type\":\"string\"}},"
		+ "\"required\":[\"prefer\",\"avoid\",\"lesson\"],"
		+ "\"additionalProperties\":false}";

	/** Grok/HTTP 返回的招数建议，以及是否已改代码并部署。 */
	public static final class Advice {
		final List<BorerAreaThinkPolicy.Move> prefer = new ArrayList<>();
		final List<BorerAreaThinkPolicy.Move> avoid = new ArrayList<>();
		String lesson = "";
		boolean patched;
		boolean deployed;
		String version = "";
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
		return grokAvailable() || !apiKey(client).isEmpty();
	}

	/** 解析源码根目录。 */
	static Path sourceRoot(Minecraft client) {
		Path configDir = client == null
			? null
			: client.gameDirectory.toPath().resolve("config/2b2t-kit");
		Path marker = configDir == null ? null : configDir.resolve("source-root.txt");
		String home = System.getenv("HOME");
		Path found = BorerAreaThinkPolicy.sourceRoot(
			System.getenv("AUTOCRUISE_SRC"),
			marker,
			BorerAreaThinkPolicy.defaultSourceRoot(home != null && !home.isBlank()
				? Path.of(home)
				: Path.of(System.getProperty("user.home", ""))));
		if (found == null) {
			found = BorerAreaThinkPolicy.sourceRoot(null, null,
				BorerAreaThinkPolicy.defaultSourceRoot(Path.of(System.getProperty("user.home", ""))));
		}
		if (found != null && configDir != null) writeSourceRootMarker(marker, found);
		return found;
	}

	/** 读取本机 API 密钥。 */
	static String apiKey(Minecraft client) {
		String env = System.getenv("XAI_API_KEY");
		if (env != null && !env.isBlank()) return env.trim();
		if (client == null) return "";
		Path path = client.gameDirectory.toPath().resolve("config/2b2t-kit/xai.key");
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

	/** 异步问 Grok/改代码；成功/失败回调。 */
	static void ask(
		Minecraft client,
		String scene,
		String scores,
		String logTail,
		boolean patchCode,
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
					askWorker(client, scene, scores, logTail, patchCode, engineVersion, progress, onOk, onFail);
				} finally {
					BUSY.set(false);
				}
			},
			"2b2t-kit-area-think-ask");
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

	/** 组装让 Grok 改引擎源码的提示词。 */
	static String patchPromptText(
		String scene, String scores, String logTail, String engineVersion,
		Path sourceRoot, Path replyFile
	) {
		return """
			You are patching 2b2t-kit, a Fabric Minecraft 26.1.2 client mod, while the player keeps mining.

			Repo: %s
			Current engine version: %s
			Write this reply file when done: %s

			The miner is STUCK. Local try-moves all failed. Diagnose from the log, then fix the real engine rule.

			Allowed edits only:
			- src/client/java/dev/twob2tkit/runtime/engine/*.java
			- src/test/java/dev/twob2tkit/runtime/engine/*Test.java
			- gradle.properties (runtime_engine_version only)
			- DefaultTunnelBorerEngine.RUNTIME_VERSION must match runtime_engine_version

			Never edit host/UI/Mixin/chopper/planter, never meteor-client-source, never runClient, never copy mods/*.jar.
			Do not copy the engine jar yourself. Do not run gradle jar; tests are optional.

			Policy map: fly/obstruction/area bounds → BorerAreaPolicy; fall → BorerFallPolicy; adjacent ore → BorerOrePolicy; stairs → BorerStairPolicy; centering → BorerCenterPolicy; crosshair mine → BorerMiningPolicy; loot → BorerLootPolicy; think order → BorerAreaThinkPolicy. Add or extend the matching *Test.

			If this is not a code bug (just a bad try-move), do not edit Java.

			When finished, write the reply file as JSON only:
			{"prefer":["MINE_LOOKED"],"avoid":["FLY_UP"],"lesson":"短中文","patched":true,"deployed":false,"version":"%s"}
			patched=true only if you actually changed Java. Moves: MINE_LOOKED, MINE_FRONT, RELEASE_FORWARD, DESCEND, FLY_LEVEL, FLY_UP, SKIP_SHAFT.

			scene=%s
			scores=
			%s
			log=
			%s
			""".formatted(
			sourceRoot.toAbsolutePath(),
			nullToEmpty(engineVersion),
			replyFile.toAbsolutePath(),
			nullToEmpty(engineVersion),
			scene,
			nullToEmpty(scores),
			nullToEmpty(logTail)
		);
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
			|| (advice.lesson != null && !advice.lesson.isBlank())
			|| advice.patched);
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
			if (root.has("prefer") || root.has("avoid") || root.has("lesson") || root.has("patched")) {
				return parseAdviceObject(root);
			}
		} catch (RuntimeException ignored) {
			return empty;
		}
		return empty;
	}

	/** 后台：写 ask 文件，优先改代码，否则问建议。 */
	private static void askWorker(
		Minecraft client,
		String scene,
		String scores,
		String logTail,
		boolean patchCode,
		String engineVersion,
		Consumer<String> progress,
		Consumer<Advice> onOk,
		Runnable onFail
	) {
		try {
			Path dir = client.gameDirectory.toPath().resolve("config/2b2t-kit");
			Files.createDirectories(dir);
			Path replyFile = dir.resolve("area-think-reply.json");
			Files.deleteIfExists(replyFile);
			writeAsk(dir.resolve("area-think-ask.json"), scene, scores, logTail, patchCode, engineVersion);
			Path repo = sourceRoot(client);
			boolean patch = patchCode && grokAvailable() && repo != null;
			if (patch) {
				try {
					note(client, progress, "正在让 Grok 改挖矿代码");
					Advice advice = runGrokPatch(client, repo, replyFile, scene, scores, logTail, engineVersion);
					if (advice.patched) {
						note(client, progress, "正在编译新引擎");
						Path dest = dir.resolve("runtime/2b2t-kit-engine.jar");
						Path javaHome = BorerAreaThinkDeploy.javaHome(
							repo, System.getenv("JAVA_HOME"), System.getProperty("java.home"));
						BorerAreaThinkDeploy.Result deployed = BorerAreaThinkDeploy.deploy(
							repo, javaHome, dest, engineVersion);
						advice.deployed = deployed.ok;
						if (!deployed.version.isBlank()) advice.version = deployed.version;
						if (!deployed.ok && (advice.lesson == null || advice.lesson.isBlank())) {
							advice.lesson = "改了代码但编译失败";
						}
						note(client, progress, deployed.ok
							? "已编出 " + advice.version
							: "编译失败 " + deployed.error);
						LOGGER.warn("area-think deploy ok={} version={} err={}",
							deployed.ok, deployed.version, deployed.error);
					}
					if (hasAdvice(advice)) {
						note(client, progress, "已收到 Grok 回复");
						client.execute(() -> onOk.accept(advice));
						return;
					}
					LOGGER.warn("area-think grok-patch returned empty advice");
					note(client, progress, "改代码没给出课，改问招数");
				} catch (Exception exception) {
					LOGGER.warn("area-think grok-patch failed: {}", exception.toString());
					note(client, progress, "改代码失败，改问招数");
				}
			}
			if (grokAvailable()) {
				try {
					note(client, progress, "正在问本机 Grok");
					Advice advice = runGrokCli(client, scene, scores, logTail);
					if (hasAdvice(advice)) {
						note(client, progress, "已收到 Grok 招数");
						client.execute(() -> onOk.accept(advice));
						return;
					}
					LOGGER.warn("area-think grok-cli returned empty advice");
				} catch (Exception exception) {
					LOGGER.warn("area-think grok-cli failed: {}", exception.toString());
					note(client, progress, "本机 Grok 失败");
				}
			}
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

	/** 调本机 Grok 改挖矿引擎并读回复。 */
	private static Advice runGrokPatch(
		Minecraft client, Path repo, Path replyFile,
		String scene, String scores, String logTail, String engineVersion
	) throws IOException, InterruptedException {
		Path home = grokHome();
		Path bin = grokBin(home, System.getenv("GROK_BIN"));
		if (bin == null) throw new IOException("grok binary missing");
		Path dir = client.gameDirectory.toPath().resolve("config/2b2t-kit");
		Path promptPath = dir.resolve("area-think-patch-prompt.txt");
		Path outPath = dir.resolve("area-think-grok.out");
		Path errPath = dir.resolve("area-think-grok.err");
		Path sockPath = dir.resolve("area-think-leader.sock");
		Files.writeString(promptPath,
			patchPromptText(scene, scores, logTail, engineVersion, repo, replyFile),
			StandardCharsets.UTF_8);
		ProcessBuilder builder = new ProcessBuilder(
			bin.toString(),
			"--prompt-file", promptPath.toAbsolutePath().toString(),
			"--output-format", "json",
			"--max-turns", "20",
			"--yolo",
			"--no-subagents",
			"--disable-web-search",
			"--no-auto-update",
			"--no-alt-screen",
			"--cwd", repo.toAbsolutePath().toString(),
			"--leader-socket", sockPath.toAbsolutePath().toString()
		);
		builder.directory(repo.toFile());
		BorerAreaThinkPolicy.discardStdin(builder);
		builder.redirectOutput(outPath.toFile());
		builder.redirectError(errPath.toFile());
		Map<String, String> env = builder.environment();
		env.put("HOME", BorerAreaThinkPolicy.realHome(home, System.getenv("HOME"), System.getProperty("user.home", "")));
		env.put("GROK_HOME", home.toString());
		env.put("GROK_DISABLE_AUTOUPDATER", "1");
		env.put("RUST_LOG", "off");
		Process process = builder.start();
		boolean finished = process.waitFor(GROK_PATCH_TIMEOUT_SECONDS, TimeUnit.SECONDS);
		if (!finished) {
			process.destroyForcibly();
			process.waitFor(2, TimeUnit.SECONDS);
			throw new IOException("grok patch timeout after " + GROK_PATCH_TIMEOUT_SECONDS + "s");
		}
		Advice fromFile = readReply(replyFile);
		if (hasAdvice(fromFile)) return fromFile;
		String stdout = Files.isRegularFile(outPath)
			? Files.readString(outPath, StandardCharsets.UTF_8)
			: "";
		if (process.exitValue() != 0) {
			String stderr = Files.isRegularFile(errPath)
				? Files.readString(errPath, StandardCharsets.UTF_8)
				: "";
			throw new IOException("grok patch exit " + process.exitValue() + " " + clip(stderr, 400));
		}
		return parse(stdout);
	}

	/** 调本机 Grok CLI 只问招数建议。 */
	private static Advice runGrokCli(
		Minecraft client, String scene, String scores, String logTail
	) throws IOException, InterruptedException {
		Path home = grokHome();
		Path bin = grokBin(home, System.getenv("GROK_BIN"));
		if (bin == null) throw new IOException("grok binary missing");
		Path dir = client.gameDirectory.toPath().resolve("config/2b2t-kit");
		Files.createDirectories(dir);
		Path promptPath = dir.resolve("area-think-prompt.txt");
		Path outPath = dir.resolve("area-think-grok.out");
		Path errPath = dir.resolve("area-think-grok.err");
		Path sockPath = dir.resolve("area-think-leader.sock");
		Files.writeString(promptPath, promptText(scene, scores, logTail), StandardCharsets.UTF_8);
		ProcessBuilder builder = new ProcessBuilder(
			bin.toString(),
			"--prompt-file", promptPath.toAbsolutePath().toString(),
			"--json-schema", ADVICE_SCHEMA,
			"--max-turns", "1",
			"--no-subagents",
			"--disable-web-search",
			"--no-auto-update",
			"--no-alt-screen",
			"--cwd", dir.toAbsolutePath().toString(),
			"--leader-socket", sockPath.toAbsolutePath().toString()
		);
		builder.directory(dir.toFile());
		BorerAreaThinkPolicy.discardStdin(builder);
		builder.redirectOutput(outPath.toFile());
		builder.redirectError(errPath.toFile());
		Map<String, String> env = builder.environment();
		env.put("HOME", BorerAreaThinkPolicy.realHome(home, System.getenv("HOME"), System.getProperty("user.home", "")));
		env.put("GROK_HOME", home.toString());
		env.put("GROK_DISABLE_AUTOUPDATER", "1");
		env.put("RUST_LOG", "off");
		Process process = builder.start();
		boolean finished = process.waitFor(GROK_TIMEOUT_SECONDS, TimeUnit.SECONDS);
		if (!finished) {
			process.destroyForcibly();
			process.waitFor(2, TimeUnit.SECONDS);
			throw new IOException("grok timeout after " + GROK_TIMEOUT_SECONDS + "s");
		}
		int code = process.exitValue();
		String stdout = Files.isRegularFile(outPath)
			? Files.readString(outPath, StandardCharsets.UTF_8)
			: "";
		if (code != 0) {
			String stderr = Files.isRegularFile(errPath)
				? Files.readString(errPath, StandardCharsets.UTF_8)
				: "";
			throw new IOException("grok exit " + code + " " + clip(stderr, 400));
		}
		return parse(stdout);
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

	/** 从回复文件解析建议。 */
	private static Advice readReply(Path path) {
		if (path == null || !Files.isRegularFile(path)) return new Advice();
		try {
			return parse(Files.readString(path, StandardCharsets.UTF_8));
		} catch (IOException ignored) {
			return new Advice();
		}
	}

	/** 把本次提问上下文写成 area-think-ask.json。 */
	private static void writeAsk(
		Path path, String scene, String scores, String logTail, boolean patch, String version
	) {
		try {
			JsonObject root = new JsonObject();
			root.addProperty("scene", nullToEmpty(scene));
			root.addProperty("scores", nullToEmpty(scores));
			root.addProperty("log", nullToEmpty(logTail));
			root.addProperty("patch", patch);
			root.addProperty("version", nullToEmpty(version));
			Files.writeString(path, root.toString(), StandardCharsets.UTF_8);
		} catch (IOException ignored) {
		}
	}

	/** 写入源码根标记文件。 */
	private static void writeSourceRootMarker(Path marker, Path repo) {
		try {
			if (marker == null || repo == null) return;
			Files.createDirectories(marker.getParent());
			if (Files.isRegularFile(marker)) return;
			Files.writeString(marker, repo.toAbsolutePath() + System.lineSeparator(), StandardCharsets.UTF_8);
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
		if (json.has("patched") && json.get("patched").isJsonPrimitive()) {
			advice.patched = json.get("patched").getAsBoolean();
		}
		if (json.has("deployed") && json.get("deployed").isJsonPrimitive()) {
			advice.deployed = json.get("deployed").getAsBoolean();
		}
		if (json.has("version") && json.get("version").isJsonPrimitive()) {
			advice.version = json.get("version").getAsString();
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
