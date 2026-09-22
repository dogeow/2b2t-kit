package dev.twob2tkit.runtime.engine;

import java.lang.reflect.Field;
import it.unimi.dsi.fastutil.longs.Long2ObjectMap;
import net.minecraft.client.multiplayer.ClientLevel;
import net.minecraft.client.multiplayer.prediction.BlockStatePredictionHandler;
import net.minecraft.core.BlockPos;

/** Vanilla owns prediction correction and acknowledgements. Area clicks also open its prediction scope. */
public final class BorerMiningConfirmation {
	private final Field handler, states;
	private final java.lang.reflect.Method syncSelected;
	private int waiting;
	public BorerMiningConfirmation() {
		try {
			handler = ClientLevel.class.getDeclaredField("blockStatePredictionHandler");
			states = BlockStatePredictionHandler.class.getDeclaredField("serverVerifiedStates");
			handler.setAccessible(true); states.setAccessible(true);
			syncSelected = net.minecraft.client.multiplayer.MultiPlayerGameMode.class.getDeclaredMethod("ensureHasSentCarriedItem");
			syncSelected.setAccessible(true);
		} catch (ReflectiveOperationException e) { throw new IllegalStateException("Cannot read vanilla block confirmation state", e); }
	}
	private Long2ObjectMap<?> pending(ClientLevel level) {
		try { return (Long2ObjectMap<?>) states.get(handler.get(level)); }
		catch (IllegalAccessException e) { throw new IllegalStateException("Cannot read pending block predictions", e); }
	}
	public boolean pending(ClientLevel level, BlockPos pos) { return pending(level).containsKey(pos.asLong()); }
	/** Meteor's instamine deletes locally BEFORE its own packet prediction scopes. Opening the
	 * normal vanilla scope here lets ClientLevel retain the pre-click state for server correction. */
	boolean startObservedBreak(net.minecraft.client.Minecraft client, BlockPos pos, net.minecraft.core.Direction face) {
		try {
			var prediction = (BlockStatePredictionHandler) handler.get(client.level);
			if (prediction.isPredicting()) throw new IllegalStateException("另一挖掘预测尚未结束，已暂停区域挖");
			syncSelected.invoke(client.gameMode);
			try (var scope = prediction.startPredicting()) {
				return client.gameMode.startDestroyBlock(pos, face);
			}
		} catch (ReflectiveOperationException e) { throw new IllegalStateException("无法登记区域挖服务器确认", e); }
	}
	int count(ClientLevel level) { return pending(level).size(); }
	int update(int pending) { waiting = pending > 0 ? waiting + 1 : 0; return waiting; }
	boolean expired() { return waiting >= 100; }
	void reset() { waiting = 0; }
}
