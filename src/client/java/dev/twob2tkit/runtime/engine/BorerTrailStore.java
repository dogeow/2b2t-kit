package dev.twob2tkit.runtime.engine;

import java.io.IOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.*;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.util.*;

/** Per-world route files; replacement is atomic and explicit resets retain an archive. */
final class BorerTrailStore {
	private final Path root;
	BorerTrailStore(Path root) { this.root = root; }
	Path file(String scope) { return root.resolve("journeys").resolve(key(scope) + ".txt"); }
	static String header(String scope) {
		return "scope " + Base64.getUrlEncoder().withoutPadding().encodeToString(scope.getBytes(StandardCharsets.UTF_8)) + "\n";
	}
	static String scopeOf(String text) {
		for (String line : text.lines().toList()) if (line.startsWith("scope ")) {
			return new String(Base64.getUrlDecoder().decode(line.substring(6)), StandardCharsets.UTF_8);
		}
		return null;
	}
	String read(String scope) throws IOException {
		Path p = file(scope);
		if (!Files.isRegularFile(p)) return null;
		String text = Files.readString(p);
		if (!scope.equals(scopeOf(text))) throw new IOException("Route belongs to another world");
		return text;
	}
	void write(String scope, String snapshot) throws IOException {
		if (!scope.equals(scopeOf(snapshot))) throw new IOException("Missing or mismatched route world");
		atomicWrite(file(scope), snapshot);
	}
	Path archive(String scope, String snapshot) throws IOException {
		Path dir = root.resolve("journeys").resolve("archive");
		Files.createDirectories(dir);
		Path p = dir.resolve(key(scope) + "-" + System.currentTimeMillis() + "-" + UUID.randomUUID() + ".txt");
		Files.writeString(p, snapshot, StandardCharsets.UTF_8, StandardOpenOption.CREATE_NEW);
		return p;
	}
	/** Legacy files have no world identity. Claim once, keeping the original untouched. */
	String migrateLegacy(String scope, String activeSnapshot) throws IOException {
		Path claim = root.resolve("journeys").resolve("legacy-owner.txt");
		if (Files.exists(claim)) return null;
		String legacy = activeSnapshot;
		if (legacy == null || legacy.isBlank()) {
			Path old = root.resolve("borer-trail.txt");
			if (!Files.isRegularFile(old)) return null;
			legacy = Files.readString(old);
		}
		archive(scope, legacy);
		// The legacy portal had no dimension/server identity; never attach it to
		// an overworld journey or silently reuse it in another world.
		String adopted = header(scope) + legacy.lines()
			.filter(line -> !line.startsWith("scope ") && !line.startsWith("portal "))
			.collect(java.util.stream.Collectors.joining("\n", "", "\n"));
		write(scope, adopted);
		atomicWrite(claim, scope);
		return adopted;
	}
	private static void atomicWrite(Path target, String text) throws IOException {
		Files.createDirectories(target.getParent());
		Path tmp = Files.createTempFile(target.getParent(), ".route-", ".tmp");
		try {
			Files.writeString(tmp, text, StandardCharsets.UTF_8);
			try { Files.move(tmp, target, StandardCopyOption.ATOMIC_MOVE, StandardCopyOption.REPLACE_EXISTING); }
			catch (AtomicMoveNotSupportedException e) { Files.move(tmp, target, StandardCopyOption.REPLACE_EXISTING); }
		} finally { Files.deleteIfExists(tmp); }
	}
	private static String key(String scope) {
		try { return HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(scope.getBytes(StandardCharsets.UTF_8))); }
		catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
	}
}
