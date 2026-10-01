package dev.twob2tkit.automation;

import net.minecraft.core.BlockPos;

import java.util.HashSet;
import java.util.Set;

/** A matching server block-update packet, not a predicted client block state, completes one stage. */
final class TerrainServerConfirmation {
    private static final String SCOPE = "matched_server_block_update_after_native_send";
    private final Set<String> spentStages = new HashSet<>();
    private Intent pending;

    static BlockPos target(String stage,BlockPos foundation) {
        return switch(stage) {
            case "lift_grass","restore_grass" -> foundation.above();
            case "mine_stone","place_dirt" -> foundation;
            default -> throw new IllegalArgumentException("Unknown terrain server confirmation stage");
        };
    }

    static String expectedState(String stage,String originalGrass) {
        return switch(stage) {
            case "lift_grass","mine_stone" -> "Block{minecraft:air}";
            case "place_dirt" -> "Block{minecraft:dirt}";
            case "restore_grass" -> originalGrass;
            default -> throw new IllegalArgumentException("Unknown terrain server confirmation stage");
        };
    }

    private static final class Intent {
        final String world, requestId, stage, expected;
        final BlockPos target;
        boolean sent, confirmed, serverUpdateSeen;
        String serverObservedState;

        Intent(String world,String requestId,String stage,BlockPos target,String expected) {
            this.world=world;this.requestId=requestId;this.stage=stage;
            this.target=target.immutable();this.expected=expected;
        }
    }

    void begin(String world,String requestId,String stage,BlockPos target,String expected) {
        if (world.isBlank() || requestId.isBlank() || stage.isBlank() || expected.isBlank())
            throw new IllegalArgumentException("Terrain server confirmation needs an exact stage identity");
        if (pending!=null && pending.world.equals(world))
            throw new IllegalStateException("Another terrain confirmation is still pending");
        // A different desired state must not reopen an uncertain action at the same cell.
        String key=world+'|'+stage+'|'+target.toShortString();
        if (!spentStages.add(key))
            throw new IllegalStateException("A terrain stage at this cell was already attempted in this world session");
        pending=new Intent(world,requestId,stage,target,expected);
    }

    void sent(String world,String requestId,String stage,BlockPos target) {
        if (!matches(world,requestId,stage,target))
            throw new IllegalStateException("Terrain send no longer owns the registered stage");
        pending.sent=true;
    }

    boolean serverBlock(String world,String requestId,String stage,BlockPos target,String actual,
                        boolean clientAppliedSameState) {
        if (!matches(world,requestId,stage,target) || !pending.sent || !clientAppliedSameState)
            return false;
        pending.serverUpdateSeen=true;
        pending.serverObservedState=actual;
        // A later corrective packet invalidates an earlier positive update.
        pending.confirmed=pending.expected.equals(actual);
        return pending.confirmed;
    }

    boolean confirmed(String world,String requestId,String stage,BlockPos target) {
        return matches(world,requestId,stage,target) && pending.sent && pending.confirmed;
    }

    boolean serverUpdateSeen(String world,String requestId,String stage,BlockPos target) {
        return matches(world,requestId,stage,target) && pending.sent && pending.serverUpdateSeen;
    }

    String serverObservedState(String world,String requestId,String stage,BlockPos target) {
        return serverUpdateSeen(world,requestId,stage,target) ? pending.serverObservedState : null;
    }

    String scope() { return SCOPE; }

    void close(String requestId) {
        if (pending!=null && pending.requestId.equals(requestId))pending=null;
    }

    void clear() { pending=null; }

    private boolean matches(String world,String requestId,String stage,BlockPos target) {
        return pending!=null && pending.world.equals(world) && pending.requestId.equals(requestId)
            && pending.stage.equals(stage) && pending.target.equals(target);
    }
}
