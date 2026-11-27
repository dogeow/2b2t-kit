package dev.twob2tkit.combat;

/**
 * Names health loss that has no attacker. Poison from a bee sting or wither ticks about once a second;
 * those ticks used to be logged and announced as "被打：未知".
 */
final class CombatDamageLabel {
    static final String UNKNOWN = "未知";
    /** Effect damage repeats every second; announce it once per window instead of every tick. */
    static final long EFFECT_CHAT_QUIET_MILLIS = 10_000;

    private CombatDamageLabel() {}

    /** @param msgId the last damage source's message id, or null when the client saw none */
    static String fallback(String msgId, boolean poisoned, boolean withered) {
        if ("wither".equals(msgId) || msgId == null && withered) return "凋零";
        if (poisoned && (msgId == null || "magic".equals(msgId) || "indirectMagic".equals(msgId))) return "中毒";
        if ("magic".equals(msgId) || "indirectMagic".equals(msgId)) return "魔法";
        if ("starve".equals(msgId)) return "饥饿";
        return UNKNOWN;
    }

    static boolean effectTick(String label) {
        return "中毒".equals(label) || "凋零".equals(label);
    }

    /** True when this hurt should not post another chat line: the same effect announced moments ago. */
    static boolean quietChat(String label, String lastLabel, long now, long lastAt) {
        return effectTick(label) && label.equals(lastLabel) && now - lastAt < EFFECT_CHAT_QUIET_MILLIS;
    }
}
