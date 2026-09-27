package dev.twob2tkit.runtime.engine;

import com.google.gson.Gson;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardCopyOption;
import java.nio.file.AtomicMoveNotSupportedException;
import java.io.IOException;
import java.util.Arrays;
import java.util.HexFormat;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import net.minecraft.core.BlockPos;

/** Retain a checkpoint per world and bounds, plus the legacy latest-area pointer. */
final class BorerAreaProgress {
	private static final Gson JSON = new Gson();
	private record Saved(int schema, String world, BorerAreaPlan.Snapshot plan) {}
	static BorerAreaPlan.Snapshot read(Path path, String world) {
		Saved saved=readSaved(path);
		return saved!=null&&world.equals(saved.world)?saved.plan:null;
	}
	static BorerAreaPlan.Snapshot read(Path path,String world,BlockPos min,BlockPos max){
		int[] bounds={min.getX(),min.getY(),min.getZ(),max.getX(),max.getY(),max.getZ()};
		Saved legacy=readSaved(path);
		if(legacy!=null&&world.equals(legacy.world)&&Arrays.equals(bounds,legacy.plan.bounds()))return legacy.plan;
		Saved saved=readSaved(regionPath(path,world,bounds));
		return saved!=null&&world.equals(saved.world)&&Arrays.equals(bounds,saved.plan.bounds())?saved.plan:null;
	}
	private static Saved readSaved(Path path){
		try {
			if (!Files.isRegularFile(path) || Files.size(path) > 1_000_000) return null;
			Saved saved = JSON.fromJson(Files.readString(path), Saved.class);
			return saved != null && saved.schema == 1 && saved.plan!=null ? saved : null;
		} catch (IOException | RuntimeException ignored) { return null; }
	}
	static void write(Path path, String world, BorerAreaPlan.Snapshot plan) throws IOException {
		Saved previous=readSaved(path);
		if(previous!=null&&(!world.equals(previous.world)||!Arrays.equals(plan.bounds(),previous.plan.bounds())))
			writeSaved(regionPath(path,previous.world,previous.plan.bounds()),previous);
		Saved current=new Saved(1,world,plan);
		writeSaved(regionPath(path,world,plan.bounds()),current);
		writeSaved(path,current);
	}
	private static Path regionPath(Path path,String world,int[] bounds){
		try{
			String key=world+"\n"+Arrays.toString(bounds);
			String hash=HexFormat.of().formatHex(MessageDigest.getInstance("SHA-256").digest(key.getBytes(StandardCharsets.UTF_8)));
			return path.resolveSibling(path.getFileName()+".regions").resolve(hash+".json");
		}catch(java.security.NoSuchAlgorithmException impossible){throw new IllegalStateException(impossible);}
	}
	private static void writeSaved(Path path,Saved saved)throws IOException{
		Files.createDirectories(path.getParent());
		Path temp = path.resolveSibling(path.getFileName() + ".new");
		Files.writeString(temp, JSON.toJson(saved));
		try { Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING, StandardCopyOption.ATOMIC_MOVE); }
		catch (AtomicMoveNotSupportedException ignored) { Files.move(temp, path, StandardCopyOption.REPLACE_EXISTING); }
	}
	private BorerAreaProgress() {}
}
