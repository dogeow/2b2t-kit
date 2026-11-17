package dev.twob2tkit.runtime.engine;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.StandardOpenOption;
import java.util.UUID;
import net.minecraft.client.Minecraft;
import net.minecraft.world.InteractionHand;
import net.minecraft.world.entity.monster.Enemy;
import net.minecraft.world.item.Items;
import net.minecraft.world.level.GameType;
import net.minecraft.world.phys.Vec3;

/** One ordinary bottle use from an explicitly owned, grounded work position. */
final class ExperienceBottleUse {
    private UUID last;

    void tick(Minecraft client, Path root, long now) {
        Path input = root.resolve("experience-bottle-intent.json");
        if (!Files.isRegularFile(input) || client.player == null || client.level == null || client.gameMode == null) return;
        UUID id = null;
        try {
            if (Files.size(input) > 4096) return;
            var request = JsonParser.parseString(Files.readString(input)).getAsJsonObject();
            id = UUID.fromString(request.get("id").getAsString());
            if (id.equals(last)) return;
            last = id;
            var statusFile = root.resolve("status.json");
            if (Files.size(statusFile) > 2_000_000) return;
            var state = JsonParser.parseString(Files.readString(statusFile)).getAsJsonObject();
            var player = client.player;
            var lease = state.get("supervision_lease");
            if (request.get("protocol").getAsInt() != 1 || lease == null || !lease.isJsonObject()
                || !owned(request, state, lease.getAsJsonObject(), now, player.getUUID().toString())
                || !state.get("server").getAsString().equals(client.getCurrentServer().ip)
                || !state.get("dimension").getAsString().equals(client.level.dimension().identifier().toString())) return;
            if (client.gameMode.getPlayerMode() != GameType.SURVIVAL || client.gui.screen() != null
                || client.getCameraEntity() != player || player.containerMenu != player.inventoryMenu
                || !player.containerMenu.getCarried().isEmpty() || player.getHealth() != 20
                || player.hurtTime > 0 || player.isInWater() || player.isInLava() || player.isOnFire()
                || player.isUsingItem() || !player.onGround() || player.getXRot() < 80
                || player.getDeltaMovement().horizontalDistanceSqr() > .0016
                || BorerAreaRunner.physicalMovementHeld(client, client.options.keyUp, client.options.keyDown,
                    client.options.keyLeft, client.options.keyRight, client.options.keyJump, client.options.keyShift,
                    client.options.keyAttack, client.options.keyUse)
                || client.options.keyAttack.isDown() || client.options.keyUse.isDown()) return;
            var point = request.getAsJsonArray("player_pos");
            if (point.size() != 3) return;
            var expected = new Vec3(point.get(0).getAsDouble(), point.get(1).getAsDouble(), point.get(2).getAsDouble());
            if (!(player.position().distanceToSqr(expected) <= .15 * .15)) return;
            if (!client.level.getEntities(player, player.getBoundingBox().inflate(12),
                entity -> entity.isAlive() && entity instanceof Enemy).isEmpty()) return;
            var hand = player.getMainHandItem();
            if (!hand.is(Items.EXPERIENCE_BOTTLE) || hand.getCount() != request.get("expected_count").getAsInt()
                || player.getCooldowns().isOnCooldown(hand)) return;

            Path claims = root.resolve("experience-bottle-claims");
            Files.createDirectories(claims);
            var claim = request.deepCopy();
            claim.addProperty("claimed_at", now);
            claim.addProperty("use_may_have_been_sent", true);
            Files.writeString(claims.resolve(id + ".json"), claim.toString(), StandardOpenOption.CREATE_NEW);
            client.gameMode.useItem(player, InteractionHand.MAIN_HAND);
        } catch (Exception ignored) {
            // The caller reconciles a claimed use against actual inventory. Never replay it.
        }
    }

    static boolean owned(JsonObject request, JsonObject state, JsonObject lease, long now, String player) {
        long revision = state.get("control_revision").getAsLong();
        return player.equals(request.get("player_uuid").getAsString())
            && state.get("world_session").equals(request.get("world_session"))
            && lease.get("world_session").equals(request.get("world_session"))
            && lease.get("id").equals(request.get("lease_id"))
            && lease.get("job_session").equals(request.get("task_session"))
            && lease.get("kind").getAsString().equals("materials")
            && revision == request.get("control_revision").getAsLong()
            && revision == lease.get("revision").getAsLong()
            && state.get("phase").getAsString().equals("done")
            && state.get("runtime_version").getAsString().equals(EngineBuildVersion.VALUE)
            && state.getAsJsonObject("game_interaction").get("interaction_serial").equals(request.get("input_serial"))
            && flag(state, "connected") && flag(state, "guard_armed") && flag(state, "guard_pve_only") && flag(state, "auto_log")
            && !flag(state, "guard_busy") && !flag(state, "manual_movement") && !flag(state, "navigating")
            && !flag(state, "native_material_busy") && !flag(state, "borer_active") && !flag(state, "fisher_active")
            && !flag(state, "pending_scan") && !flag(state, "flight")
            && !flag(state.getAsJsonObject("safety_hold"), "active")
            && !flag(state.getAsJsonObject("build_job"), "active")
            && !flag(state.getAsJsonObject("professional_printer"), "owned")
            && ResidentPotionPolicy.fresh(now, request.get("issued_at").getAsLong(),
                request.get("expires_at").getAsLong(), state.get("time").getAsLong());
    }

    private static boolean flag(JsonObject state, String key) {
        if (state == null) return false;
        var value = state.get(key);
        return value != null && !value.isJsonNull() && value.getAsBoolean();
    }
}
