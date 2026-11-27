package dev.twob2tkit.combat;

import java.util.List;

/** What the player was doing when hurt; earlier logs called every material job or external command "空闲". */
final class CombatActivity {
    static final String IDLE = "空闲";
    private CombatActivity() {}

    /**
     * @param module      the legacy single-module label, or {@link #IDLE}
     * @param running     titles of every toolbox feature currently running
     * @param externalOp  the bridge operation in progress for kit_cli / agents, or empty
     */
    static String describe(String module, List<String> running, String externalOp) {
        if (!IDLE.equals(module)) return module;
        if (!running.isEmpty()) return String.join("+", running);
        if (externalOp != null && !externalOp.isBlank()) return "外部控制:" + externalOp;
        return IDLE;
    }
}
