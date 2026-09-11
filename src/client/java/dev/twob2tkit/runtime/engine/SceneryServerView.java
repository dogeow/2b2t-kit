package dev.twob2tkit.runtime.engine;

import java.lang.reflect.Field;

/** Read the server's chunk-radius packet state, not Bobby's expanded client display distance. */
final class SceneryServerView {
	record Limits(int server, int client, int scan) {}
	private Field field;
	Limits read(Object connection, int clientDisplay) {
		if (connection == null) throw new IllegalStateException("服务器连接尚未就绪");
		try {
			if (field == null || !field.getDeclaringClass().isInstance(connection)) {
				field = null;
				for (Class<?> type = connection.getClass(); type != null; type = type.getSuperclass()) try {
					field = type.getDeclaredField("serverChunkRadius"); field.setAccessible(true); break;
				} catch (NoSuchFieldException ignored) {}
				if (field == null) throw new NoSuchFieldException("serverChunkRadius");
			}
			return limits(field.getInt(connection), clientDisplay);
		} catch (ReflectiveOperationException error) { throw new IllegalStateException("无法读取服务器下发视距，未按客户端大视距盲目跑图", error); }
	}
	static Limits limits(int server, int client) {
		if (server < 1 || client < 1) throw new IllegalStateException("尚未收到有效服务器视距，请稍后重试");
		return new Limits(server, client, Math.min(32, Math.min(server, client)));
	}
}
