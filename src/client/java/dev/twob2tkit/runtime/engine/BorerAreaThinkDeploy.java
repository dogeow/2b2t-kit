package dev.twob2tkit.runtime.engine;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.AtomicMoveNotSupportedException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.util.Map;
import java.util.concurrent.TimeUnit;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** 把 Grok 改过的引擎源码编成 jar 并原子复制到热加载目录。不在游戏线程里跑。 */
final class BorerAreaThinkDeploy {
	private static final Logger LOGGER = LoggerFactory.getLogger("2b2t-kit/Borer");
	private static final int GRADLE_TIMEOUT_SECONDS = 180;
	private static final Pattern RUNTIME_VERSION = Pattern.compile("(?m)^runtime_engine_version=(.+)$");
	private static final Pattern ENGINE_CONST = Pattern.compile(
		"RUNTIME_VERSION\\s*=\\s*\"([^\"]+)\"");

	/** 一次编译部署结果：是否成功、新版本号、错误信息。 */
	public static final class Result {
		final boolean ok;
		final String version;
		final String error;

		Result(boolean ok, String version, String error) {
			this.ok = ok;
			this.version = version == null ? "" : version;
			this.error = error == null ? "" : error;
		}
	}

	private BorerAreaThinkDeploy() {
	}

	/** 版本号末位加一。 */
	static String nextPatchVersion(String version) {
		if (version == null || version.isBlank()) return "1.6.1";
		int dot = version.lastIndexOf('.');
		if (dot < 0 || dot == version.length() - 1) return version + ".1";
		try {
			int patch = Integer.parseInt(version.substring(dot + 1));
			return version.substring(0, dot + 1) + (patch + 1);
		} catch (NumberFormatException ignored) {
			return version + ".1";
		}
	}

	/** 读 gradle 里的引擎版本。 */
	static String readRuntimeEngineVersion(Path sourceRoot) throws IOException {
		Path props = sourceRoot.resolve("gradle.properties");
		Matcher matcher = RUNTIME_VERSION.matcher(Files.readString(props, StandardCharsets.UTF_8));
		if (!matcher.find()) throw new IOException("gradle.properties 没有 runtime_engine_version");
		return matcher.group(1).trim();
	}

	/** 同步改源码与 gradle 版本号。 */
	static void bumpEngineVersion(Path sourceRoot, String from, String to) throws IOException {
		if (from == null || to == null || from.equals(to)) return;
		replaceFile(sourceRoot.resolve("gradle.properties"),
			"runtime_engine_version=" + from, "runtime_engine_version=" + to);
		Path engine = sourceRoot.resolve(
			"src/client/java/dev/twob2tkit/runtime/engine/DefaultTunnelBorerEngine.java");
		String text = Files.readString(engine, StandardCharsets.UTF_8);
		Matcher matcher = ENGINE_CONST.matcher(text);
		if (matcher.find() && from.equals(matcher.group(1))) {
			Files.writeString(engine, matcher.replaceFirst("RUNTIME_VERSION = \"" + to + "\""),
				StandardCharsets.UTF_8);
		}
	}

	/** 解析编译用 JAVA_HOME。 */
	static Path javaHome(Path sourceRoot, String javaHomeEnv, String processJavaHome) {
		Path bundled = sourceRoot == null ? null : sourceRoot.resolve("../jdk25/Contents/Home").normalize();
		if (bundled != null && Files.isRegularFile(bundled.resolve("bin/java"))) return bundled;
		Path env = parse(javaHomeEnv);
		if (env != null && Files.isRegularFile(env.resolve("bin/java"))) return env;
		Path process = parse(processJavaHome);
		if (process != null && Files.isRegularFile(process.resolve("bin/java"))) return process;
		return process;
	}

	/** 编译并安装热加载引擎 jar。 */
	static Result deploy(Path sourceRoot, Path javaHome, Path destJar, String runningVersion) {
		if (sourceRoot == null || destJar == null) {
			return new Result(false, "", "没有源码目录");
		}
		try {
			String version = readRuntimeEngineVersion(sourceRoot);
			if (version.equals(runningVersion)) {
				String next = nextPatchVersion(runningVersion);
				bumpEngineVersion(sourceRoot, runningVersion, next);
				version = next;
			}
			int code = runGradle(sourceRoot, javaHome);
			if (code != 0) return new Result(false, version, "gradle exit " + code);
			Path built = sourceRoot.resolve("build/runtime-engine/2b2t-kit-engine.jar");
			if (!Files.isRegularFile(built)) return new Result(false, version, "没有编出引擎 jar");
			atomicInstall(built, destJar);
			return new Result(true, version, "");
		} catch (Exception exception) {
			LOGGER.warn("area-think deploy failed: {}", exception.toString());
			return new Result(false, "", exception.toString());
		}
	}

	/** 跑 gradle 打引擎包。 */
	private static int runGradle(Path sourceRoot, Path javaHome) throws IOException, InterruptedException {
		Path gradlew = sourceRoot.resolve("gradlew");
		ProcessBuilder builder = new ProcessBuilder(
			gradlew.toAbsolutePath().toString(),
			"-p", sourceRoot.toAbsolutePath().toString(),
			"--offline",
			"test",
			"jar"
		);
		builder.directory(sourceRoot.toFile());
		BorerAreaThinkPolicy.discardStdin(builder);
		Path log = sourceRoot.resolve("build/area-think-deploy.log");
		Files.createDirectories(log.getParent());
		builder.redirectOutput(log.toFile());
		builder.redirectErrorStream(true);
		Map<String, String> env = builder.environment();
		if (javaHome != null) env.put("JAVA_HOME", javaHome.toAbsolutePath().toString());
		Process process = builder.start();
		boolean finished = process.waitFor(GRADLE_TIMEOUT_SECONDS, TimeUnit.SECONDS);
		if (!finished) {
			process.destroyForcibly();
			process.waitFor(5, TimeUnit.SECONDS);
			return 124;
		}
		return process.exitValue();
	}

	/** 原子替换目标 jar。 */
	private static void atomicInstall(Path built, Path destJar) throws IOException {
		Files.createDirectories(destJar.getParent());
		Path prev = destJar.resolveSibling("2b2t-kit-engine.prev.jar");
		if (Files.isRegularFile(destJar)) {
			Files.copy(destJar, prev, StandardCopyOption.REPLACE_EXISTING);
		}
		Path temp = destJar.resolveSibling("2b2t-kit-engine.jar.new");
		Files.copy(built, temp, StandardCopyOption.REPLACE_EXISTING);
		try {
			Files.move(temp, destJar, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE);
		} catch (AtomicMoveNotSupportedException ignored) {
			Files.move(temp, destJar, StandardCopyOption.REPLACE_EXISTING);
		}
	}

	/** 文件内字符串替换。 */
	private static void replaceFile(Path path, String from, String to) throws IOException {
		String text = Files.readString(path, StandardCharsets.UTF_8);
		if (!text.contains(from)) return;
		Files.writeString(path, text.replace(from, to), StandardCharsets.UTF_8);
	}

	/** 解析文本为结构化结果。 */
	private static Path parse(String text) {
		if (text == null || text.isBlank()) return null;
		try {
			return Path.of(text);
		} catch (RuntimeException ignored) {
			return null;
		}
	}
}
