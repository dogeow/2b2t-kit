package dev.twob2tkit.logreview;

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
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicBoolean;
import java.util.function.Consumer;
import dev.twob2tkit.aihud.AiHud;

/** 把挖树等主机日志发给本机已登录的 Grok 或 xAI 密钥。不在游戏线程里等。 */
public final class LogReviewAsk {
	private static final Logger LOGGER = LoggerFactory.getLogger("twob2tkit/LogReview");
	private static final HttpClient HTTP = HttpClient.newBuilder()
		.connectTimeout(Duration.ofSeconds(8))
		.build();
	private static final AtomicBoolean BUSY = new AtomicBoolean(false);
	private static final String MODEL = "grok-4.5";
	private static final String URL = "https://api.x.ai/v1/chat/completions";
	private static final int TIMEOUT_SECONDS = 60;
	public static final String SCHEMA = "{\"type\":\"object\",\"properties\":{"
		+ "\"need_fix\":{\"type\":\"boolean\"},"
		+ "\"lesson\":{\"type\":\"string\"},"
		+ "\"cause\":{\"type\":\"string\"}},"
		+ "\"required\":[\"need_fix\",\"lesson\"],"
		+ "\"additionalProperties\":false}";

	public static final class Advice {
		public boolean needFix;
		public String lesson = "";
		public String cause = "";
	}

	/** 把日志尾部送给本机 Grok 换建议。 */
	private LogReviewAsk() {
	}

	/** 是否正在请求中。 */
	public static boolean busy() {
		return BUSY.get();
	}

	/** 本机能否问 Grok（登录或 xai.key）。 */
	public static boolean canAsk(Minecraft client) {
		return grokAvailable() || !apiKey(client).isEmpty();
	}

	/** 异步提问；成功/失败回调。 */
	public static void ask(Minecraft client, String module, String logTail, Consumer<Advice> onOk, Runnable onFail) {
		if (!BUSY.compareAndSet(false, true)) {
			client.execute(onFail);
			return;
		}
		Thread thread = new Thread(() -> {
			try {
				Advice advice = askWorker(client, module, logTail);
				if (advice != null && advice.lesson != null && !advice.lesson.isBlank()) {
					client.execute(() -> onOk.accept(advice));
				} else {
					client.execute(onFail);
				}
			} catch (Exception exception) {
				LOGGER.warn("log-review grok failed: {}", exception.toString());
				writeFailNote(client, exception.toString());
				client.execute(onFail);
			} finally {
				BUSY.set(false);
			}
		}, "twob2tkit-log-review");
		thread.setDaemon(true);
		thread.start();
	}

	/** 拼给 Grok 的提示词。 */
	public static String promptText(String module, String logTail) {
		return "You review twob2tkit Minecraft client logs (" + module + "). "
			+ "The player is in-game. Reply JSON only: "
			+ "{\"need_fix\":true,\"lesson\":\"短中文课\",\"cause\":\"shears-worn\"}. "
			+ "need_fix=true if code or settings should change. lesson is one Chinese sentence. "
			+ "Do not write code. No markdown.\n\nlog=\n" + (logTail == null ? "" : logTail);
	}

	/** 解析 Grok 回复为建议。 */
	public static Advice parse(String raw) {
		Advice empty = new Advice();
		if (raw == null || raw.isBlank()) return empty;
		Advice whole = parseOne(raw.trim());
		if (hasLesson(whole)) return whole;
		String[] lines = raw.split("\\R");
		for (int i = lines.length - 1; i >= 0; i--) {
			if (lines[i].isBlank()) continue;
			Advice line = parseOne(lines[i].trim());
			if (hasLesson(line)) return line;
		}
		return whole;
	}

	/** 是否有可用课。 */
	private static boolean hasLesson(Advice advice) {
		return advice != null && advice.lesson != null && !advice.lesson.isBlank();
	}

	/** 解析单条字段。 */
	private static Advice parseOne(String raw) {
		Advice empty = new Advice();
		if (raw == null || raw.isBlank()) return empty;
		try {
			String text = raw.trim();
			int fence = text.indexOf('{');
			int end = text.lastIndexOf('}');
			if (fence >= 0 && end > fence) text = text.substring(fence, end + 1);
			JsonElement element = JsonParser.parseString(text);
			if (!element.isJsonObject()) return empty;
			JsonObject root = element.getAsJsonObject();
			if (root.has("choices") && root.get("choices").isJsonArray()) {
				String content = root.getAsJsonArray("choices")
					.get(0).getAsJsonObject()
					.getAsJsonObject("message")
					.get("content").getAsString();
				return parse(content);
			}
			if (root.has("result")) {
				JsonElement result = root.get("result");
				if (result.isJsonPrimitive()) return parse(result.getAsString());
				if (result.isJsonObject()) return parse(result.toString());
			}
			if (root.has("text")) {
				JsonElement textEl = root.get("text");
				if (textEl.isJsonPrimitive()) return parse(textEl.getAsString());
				if (textEl.isJsonObject()) return parse(textEl.toString());
			}
			Advice advice = new Advice();
			if (root.has("need_fix")) advice.needFix = root.get("need_fix").getAsBoolean();
			if (root.has("lesson")) advice.lesson = root.get("lesson").getAsString();
			if (root.has("cause")) advice.cause = root.get("cause").getAsString();
			return advice;
		} catch (RuntimeException ignored) {
			return empty;
		}
	}

	/** 后台：优先 Grok CLI，否则 xAI HTTP。 */
	private static Advice askWorker(Minecraft client, String module, String logTail)
		throws IOException, InterruptedException {
		note(client, "准备提问");
		if (grokAvailable()) {
			note(client, "本机已登录，走 Grok CLI");
			try {
				Advice fromCli = askCli(client, module, logTail);
				if (fromCli.lesson != null && !fromCli.lesson.isBlank()) {
					note(client, "已收到 Grok 回复");
					return fromCli;
				}
				note(client, "CLI 没给出课，改试 xAI");
			} catch (Exception exception) {
				LOGGER.warn("log-review grok-cli failed: {}", exception.toString());
				writeFailNote(client, exception.toString());
				note(client, "CLI 失败，改试 xAI");
			}
		}
		String key = apiKey(client);
		if (key.isEmpty()) {
			note(client, "没有 xai.key，结束");
			return new Advice();
		}
		note(client, "正在请求 xAI");
		Advice http = askHttp(key, module, logTail);
		if (http.lesson != null && !http.lesson.isBlank()) note(client, "已收到 xAI 回复");
		return http;
	}

	/** 更新 AiHud 过程步骤。 */
	private static void note(Minecraft client, String step) {
		if (client == null) {
			AiHud.step(step);
			return;
		}
		client.execute(() -> AiHud.step(step));
	}

	/** 用 xAI HTTP 提问。 */
	private static Advice askHttp(String key, String module, String logTail) throws IOException, InterruptedException {
		JsonObject system = new JsonObject();
		system.addProperty("role", "system");
		system.addProperty("content",
			"Review twob2tkit Minecraft logs. JSON only: "
				+ "{\"need_fix\":true,\"lesson\":\"短中文\",\"cause\":\"\"}. No markdown.");
		JsonObject user = new JsonObject();
		user.addProperty("role", "user");
		user.addProperty("content", promptText(module, logTail));
		JsonArray messages = new JsonArray();
		messages.add(system);
		messages.add(user);
		JsonObject root = new JsonObject();
		root.addProperty("model", MODEL);
		root.addProperty("temperature", 0.2);
		root.add("messages", messages);
		HttpRequest request = HttpRequest.newBuilder(URI.create(URL))
			.timeout(Duration.ofSeconds(TIMEOUT_SECONDS))
			.header("Authorization", "Bearer " + key)
			.header("Content-Type", "application/json")
			.POST(HttpRequest.BodyPublishers.ofString(root.toString(), StandardCharsets.UTF_8))
			.build();
		HttpResponse<String> response = HTTP.send(request, HttpResponse.BodyHandlers.ofString(StandardCharsets.UTF_8));
		return parse(response.body());
	}

	/** 调本机 Grok CLI 审日志。 */
	private static Advice askCli(Minecraft client, String module, String logTail)
		throws IOException, InterruptedException {
		Path home = grokHome();
		Path bin = grokBin(home);
		if (bin == null) throw new IOException("grok missing");
		Path dir = client.gameDirectory.toPath().resolve("config/twob2tkit");
		Files.createDirectories(dir);
		Path promptPath = dir.resolve("log-review-prompt.txt");
		Path outPath = dir.resolve("log-review-grok.out");
		Path errPath = dir.resolve("log-review-grok.err");
		Path sockPath = dir.resolve("log-review-leader.sock");
		Files.writeString(promptPath, promptText(module, logTail), StandardCharsets.UTF_8);
		note(client, "正在等本机 Grok 回复");
		ProcessBuilder builder = new ProcessBuilder(
			bin.toString(),
			"--prompt-file", promptPath.toAbsolutePath().toString(),
			"--json-schema", SCHEMA,
			"--max-turns", "1",
			"--no-subagents",
			"--disable-web-search",
			"--no-auto-update",
			"--no-alt-screen",
			"--cwd", dir.toAbsolutePath().toString(),
			"--leader-socket", sockPath.toAbsolutePath().toString()
		);
		builder.directory(dir.toFile());
		dev.twob2tkit.runtime.engine.BorerAreaThinkPolicy.discardStdin(builder);
		builder.redirectOutput(outPath.toFile());
		builder.redirectError(errPath.toFile());
		Map<String, String> env = builder.environment();
		env.put("HOME", dev.twob2tkit.runtime.engine.BorerAreaThinkPolicy.realHome(
			home, System.getenv("HOME"), System.getProperty("user.home", "")));
		env.put("GROK_HOME", home.toString());
		env.put("GROK_DISABLE_AUTOUPDATER", "1");
		env.put("RUST_LOG", "off");
		Process process = builder.start();
		boolean finished = process.waitFor(TIMEOUT_SECONDS, TimeUnit.SECONDS);
		if (!finished) {
			note(client, "Grok 超时");
			process.destroyForcibly();
			throw new IOException("grok log-review timeout");
		}
		int code = process.exitValue();
		String stdout = Files.isRegularFile(outPath)
			? Files.readString(outPath, StandardCharsets.UTF_8)
			: "";
		if (code != 0) {
			String stderr = Files.isRegularFile(errPath)
				? Files.readString(errPath, StandardCharsets.UTF_8)
				: "";
			throw new IOException("grok log-review exit " + code + " " + clip(stderr, 400));
		}
		return parse(stdout);
	}

	/** 失败时写模块日志备注。 */
	private static void writeFailNote(Minecraft client, String reason) {
		if (client == null || reason == null || reason.isBlank()) return;
		try {
			Path dir = client.gameDirectory.toPath().resolve("config/twob2tkit");
			Files.createDirectories(dir);
			Files.writeString(dir.resolve("log-review-grok.err"), reason + System.lineSeparator(),
				StandardCharsets.UTF_8);
		} catch (IOException ignored) {
		}
	}

	/** 截断过长文本。 */
	private static String clip(String text, int max) {
		if (text == null) return "";
		String trimmed = text.trim();
		if (trimmed.length() <= max) return trimmed;
		return trimmed.substring(0, max);
	}

	/** 读 API Key。 */
	public static String apiKey(Minecraft client) {
		String env = System.getenv("XAI_API_KEY");
		if (env != null && !env.isBlank()) return env.trim();
		if (client == null) return "";
		Path path = client.gameDirectory.toPath().resolve("config/twob2tkit/xai.key");
		if (!Files.isRegularFile(path)) return "";
		try {
			for (String line : Files.readAllLines(path, StandardCharsets.UTF_8)) {
				String trimmed = line.trim();
				if (!trimmed.isEmpty() && !trimmed.startsWith("#")) return trimmed;
			}
		} catch (IOException ignored) {
			return "";
		}
		return "";
	}

	/** 本机 grok CLI 是否可用。 */
	private static boolean grokAvailable() {
		Path home = grokHome();
		return grokBin(home) != null && home != null && Files.isRegularFile(home.resolve("auth.json"));
	}

	/** grok 安装目录。 */
	private static Path grokHome() {
		return dev.twob2tkit.runtime.engine.BorerAreaThinkPolicy.discoverGrokHome(
			System.getenv("GROK_HOME"),
			System.getenv("HOME"),
			System.getProperty("user.home", ""));
	}

	/** grok 可执行文件路径。 */
	private static Path grokBin(Path grokHome) {
		return dev.twob2tkit.runtime.engine.BorerAreaThinkPolicy.discoverGrokBin(
			grokHome, System.getenv("GROK_BIN"));
	}
}
