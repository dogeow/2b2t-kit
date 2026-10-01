package dev.twob2tkit.runtime.engine;

import org.junit.jupiter.api.Test;
import org.objectweb.asm.ClassReader;
import org.objectweb.asm.Opcodes;
import org.objectweb.asm.tree.*;
import java.util.*;
import static org.junit.jupiter.api.Assertions.*;

/** Real compiled control flow verifies that combat preempts mining and never competes with Meteor swings. */
class BorerMiningDefenseWiringTest {
    private ClassNode node(String type) throws Exception {
        var node = new ClassNode();
        try (var input = getClass().getResourceAsStream("/dev/twob2tkit/runtime/engine/" + type + ".class")) {
            assertNotNull(input); new ClassReader(input).accept(node, 0);
        }
        return node;
    }
    private MethodNode method(String type, String name) throws Exception {
        return node(type).methods.stream().filter(m -> m.name.equals(name)).findFirst().orElseThrow();
    }
    private List<String> calls(MethodNode method) {
        var result = new ArrayList<String>();
        for (var i : method.instructions) if (i instanceof MethodInsnNode call) result.add(call.name);
        return result;
    }
    @Test void oreLootAndTunnelInputsArePreemptedInTheSameTick() throws Exception {
        var tick = method("DefaultTunnelBorerEngine", "tick");
        int combat = -1, index = 0;
        var work = new ArrayList<Integer>();
        for (var i : tick.instructions) {
            if (i instanceof MethodInsnNode call) {
                if (call.owner.endsWith("/BorerRangedCombat") && call.name.equals("tick")) combat = index;
                if (Set.of("updateTarget", "updateSideTarget", "handleLootCollection", "handleFallingSand").contains(call.name)) work.add(index);
            }
            index++;
        }
        assertTrue(combat >= 0);
        assertFalse(work.isEmpty());
        for (int action : work) assertTrue(combat < action, "defense must precede ore/loot/tunnel input");
        var combatCalls = calls(method("BorerRangedCombat", "tick"));
        assertTrue(combatCalls.indexOf("releaseMine") < combatCalls.indexOf("engageMiningThreat"));
        assertTrue(combatCalls.indexOf("observe") < combatCalls.indexOf("engageMiningThreat"));
    }
    @Test void contactRescuePreemptsCombatAndOnlyReleasesMiningWhenActuallyInContact() throws Exception {
        var tick = method("DefaultTunnelBorerEngine", "tick");
        assertTrue(index(tick, "handleMiningContactRescue") < index(tick, "tick", "/BorerRangedCombat"));
        assertTrue(index(tick, "handleMiningContactRescue") < index(tick, "pauseForMeteorFood"),
            "Existing food pause must not suppress physical contact escape");
        assertTrue(index(tick, "findImminentCreeper") < index(tick, "pauseForMeteorFood"),
            "A hidden imminent blast must bypass the existing food pause");
        var rescue = method("DefaultTunnelBorerEngine", "handleMiningContactRescue");
        var rescueCalls = calls(rescue);
        assertTrue(rescueCalls.indexOf("pause") >= 0 && rescueCalls.indexOf("pause") < rescueCalls.indexOf("releaseMine"),
            "Contact escape must release combat movement before applying escape input");
        for (String handler : List.of("handleLavaContact", "handleWaterContact", "handleMagmaBurn")) {
            assertTrue(rescueCalls.contains(handler), "Existing contact rescue must remain wired: " + handler);
            assertTrue(rescueCalls.indexOf("releaseMine") < rescueCalls.indexOf(handler),
                "Mining must release before contact escape input: " + handler);
        }
        var predicates = Set.of("playerTouchedLava", "isInWater", "playerOnMagma");
        var none = reachableCalls(rescue.instructions.getFirst(), Map.of(),
            Map.of("playerTouchedLava", false, "isInWater", false, "playerOnMagma", false));
        assertFalse(none.contains("releaseMine"), "A normal mining tick must keep its attack progress");
        assertFalse(none.contains("pause"), "No contact must leave existing combat controls alone");
        for (String contact : predicates) {
            var values = new HashMap<String, Boolean>();
            for (String predicate : predicates) values.put(predicate, predicate.equals(contact));
            var contacted = reachableCalls(rescue.instructions.getFirst(), Map.of(), values);
            assertTrue(contacted.contains("releaseMine"), "Contact must release mining: " + contact);
            assertTrue(contacted.contains("pause"), "Contact rescue must take movement from combat: " + contact);
        }
    }
    @Test void separatedLavaEncountersResetTheirEscapeBudgetBeforeAnyEarlyReturn() throws Exception {
        var rescue = method("DefaultTunnelBorerEngine", "handleMiningContactRescue");
        for (var nextContact : List.of(
                Map.of("playerTouchedLava", false, "isInWater", false, "playerOnMagma", false),
                Map.of("playerTouchedLava", false, "isInWater", true, "playerOnMagma", false),
                Map.of("playerTouchedLava", false, "isInWater", false, "playerOnMagma", true))) {
            assertTrue(reachableCalls(rescue.instructions.getFirst(), Map.of(), nextContact).contains("write:lavaContactTicks"),
                "Leaving lava must reset its budget even when water or magma has rescue priority");
        }
        assertFalse(reachableCalls(rescue.instructions.getFirst(), Map.of(),
            Map.of("playerTouchedLava", true, "isInWater", false, "playerOnMagma", false)).contains("write:lavaContactTicks"),
            "A continuous lava contact must retain its timeout");
        int reset = -1, firstReturn = -1, index = 0;
        for (var i : rescue.instructions) {
            if (i instanceof FieldInsnNode field && i.getOpcode() == Opcodes.PUTFIELD && field.name.equals("lavaContactTicks")) reset = index;
            if (firstReturn < 0 && i.getOpcode() == Opcodes.IRETURN) firstReturn = index;
            index++;
        }
        assertTrue(reset >= 0 && reset < firstReturn, "Reset must precede the no-contact early exit");
    }
    @Test void imminentCreeperPreemptsAllTargetSelectionIncludingHiddenMinerThreats() throws Exception {
        var tick = method("BorerRangedCombat", "tick");
        assertTrue(index(tick, "findImminentCreeper") < index(tick, "choose"));
        assertTrue(index(tick, "findImminentCreeper") < index(tick, "meleeTarget"));
        var finder = node("BorerMobs").methods.stream()
            .filter(m -> m.name.equals("findImminentCreeper") || m.name.startsWith("lambda$findImminentCreeper$"))
            .flatMap(m -> calls(m).stream()).toList();
        assertTrue(finder.contains("creeperImminent"));
        assertFalse(finder.contains("hasLineOfSight"), "A corner must not hide an imminent blast");
        var emergency = reachableCalls(afterNonNullGuardBeforeCall(tick, "handleCreeper"), Map.of(), Map.of());
        assertTrue(emergency.contains("handleCreeper"));
        for (String action : List.of("choose", "meleeTarget", "acquire", "engageMiningThreat", "selectBow"))
            assertFalse(emergency.contains(action), "Imminent blast must return before " + action);
    }
    @Test void minerMeleeChoicePreservesTheExistingBowPathForRangedThreats() throws Exception {
        var tick = method("BorerRangedCombat", "tick");
        var melee = reachableCalls(afterBooleanCheck(tick, "meleeTarget", true), Map.of(), Map.of());
        assertTrue(melee.contains("engageMiningThreat"));
        assertFalse(melee.contains("selectBow"), "A chosen melee target must not also draw a bow");
        var bow = reachableCalls(afterBooleanCheck(tick, "meleeTarget", false), Map.of(), Map.of());
        assertTrue(bow.contains("selectBow"), "Flying/bow foes must retain normal ranged defense");
        assertFalse(bow.contains("acquire"), "Ranged foes must not acquire a miner melee target lease");
        assertFalse(bow.contains("engageMiningThreat"));
    }
    @Test void latchedMeleeFallbackDoesNotToggleAuraOrReacquireItsTargetEveryTick() throws Exception {
        var tick = method("BorerRangedCombat", "tick");
        var fallback = reachableCalls(afterBooleanCheck(tick, "meleeTarget", true),
            Map.of("miningMeleeFallback", true), Map.of());
        assertTrue(fallback.contains("engageMiningThreat"), "The latched fallback must continue real melee");
        assertFalse(fallback.contains("acquire"), "A failed Aura lease stays latched until target switch or release");
        assertFalse(fallback.contains("rangedMode"), "A failed Aura must not toggle off/on every mining tick");
        var reset = calls(method("BorerRangedCombat", "resetMiningMelee"));
        assertTrue(reset.contains("releaseMiningMelee"));
        assertTrue(reset.contains("clear"));
    }
    @Test void miningMeleeReusesFlightAndAltitudeWithoutArmingUnscopedAutoProtect() throws Exception {
        var melee = calls(method("BorerMobs", "engageMiningThreat"));
        assertTrue(melee.containsAll(List.of("enableMeteorFlight", "resolveCombatFeetY", "maintainCombatAltitude")));
        assertTrue(melee.indexOf("enableMeteorFlight") < melee.indexOf("maintainCombatAltitude"));
        assertTrue(melee.indexOf("resolveCombatFeetY") < melee.indexOf("maintainCombatAltitude"));
        assertFalse(melee.contains("armAutoProtectIfEnabled"), "Miner combat must use its scoped Aura target lease");
    }
    @Test void nativeAuraOwnsSwingsAndOldHostFallbackUsesRealAttackRangeAndDurableSword() throws Exception {
        var melee = method("BorerMobs", "engageMiningThreat");
        var calls = calls(melee);
        assertTrue(calls.indexOf("releaseMine") < calls.indexOf("selectWeapon"));
        assertTrue(calls.indexOf("isSwordWithReserve") < calls.indexOf("attack"));
        assertTrue(calls.indexOf("isWithinAttackRange") < calls.indexOf("attack"));
        assertTrue(calls.indexOf("getAttackStrengthScale") < calls.indexOf("attack"));
        assertTrue(reachableCalls(melee, false).contains("attack"));
        assertFalse(reachableCalls(melee, true).contains("attack"), "native aura and Kit must never both swing");
        for (String name : List.of("acquire", "release"))
            assertTrue(method("BorerMeteorThreatLease", name).tryCatchBlocks.stream()
                .anyMatch(c -> "java/lang/LinkageError".equals(c.type)), "old installed hosts retain normal melee");
    }
    @Test void combatApproachChecksCollisionChunkLiquidAndDropWithoutMiningAWall() throws Exception {
        var calls = calls(method("BorerMobs", "safeCombatApproach"));
        assertTrue(calls.containsAll(List.of("noCollision", "hasChunkAt", "isLavaFluid", "canWalkOrFallInto")));
        assertFalse(calls.contains("startDestroyBlock"));
        assertFalse(calls.contains("continueDestroyBlock"));
    }
    @Test void stopMenuPauseAndConfirmedClearRestoreScopedAuraBeforeTargetSelection() throws Exception {
        for (String entry : List.of("end", "pause"))
            assertTrue(calls(method("BorerRangedCombat", entry)).contains("releaseControls"));
        var release = calls(method("BorerRangedCombat", "releaseControls"));
        assertTrue(release.indexOf("rangedMode") < release.indexOf("releaseMiningMelee"));
        assertTrue(calls(method("BorerRangedCombat", "releaseMiningMelee")).contains("release"));
        assertTrue(calls(method("DefaultTunnelBorerEngine", "stop")).contains("handoff"));
        assertTrue(calls(method("BorerRangedCombat", "handoff")).contains("end"));
    }
    @Test void heldGoldIsNotCountedAsWornArmor() throws Exception {
        var slots = new HashSet<String>();
        for (var i : method("BorerThreats", "wearingGold").instructions)
            if (i instanceof FieldInsnNode f && f.owner.equals("net/minecraft/world/entity/EquipmentSlot")) slots.add(f.name);
        assertEquals(Set.of("HEAD", "CHEST", "LEGS", "FEET"), slots);
    }
    private int index(MethodNode method, String name) {
        int index = calls(method).indexOf(name);
        assertTrue(index >= 0, "Missing call: " + name);
        return index;
    }
    private int index(MethodNode method, String name, String ownerSuffix) {
        int index = 0;
        for (var instruction : method.instructions) {
            if (instruction instanceof MethodInsnNode call) {
                if (call.name.equals(name) && call.owner.endsWith(ownerSuffix)) return index;
                index++;
            }
        }
        fail("Missing call: " + ownerSuffix + "." + name);
        return -1;
    }
    private MethodInsnNode call(MethodNode method, String name) {
        for (var instruction : method.instructions)
            if (instruction instanceof MethodInsnNode call && call.name.equals(name)) return call;
        throw new AssertionError("Missing call: " + name);
    }
    private AbstractInsnNode nextCode(AbstractInsnNode instruction) {
        do { instruction = instruction.getNext(); } while (instruction != null && instruction.getOpcode() < 0);
        assertNotNull(instruction);
        return instruction;
    }
    private AbstractInsnNode afterBooleanCheck(MethodNode method, String predicate, boolean value) {
        var instruction = nextCode(call(method, predicate));
        if (instruction instanceof VarInsnNode stored && stored.getOpcode() == Opcodes.ISTORE) {
            int slot = stored.var;
            do { instruction = nextCode(instruction); }
            while (!(instruction instanceof VarInsnNode loaded && loaded.getOpcode() == Opcodes.ILOAD && loaded.var == slot));
            instruction = nextCode(instruction);
        }
        assertInstanceOf(JumpInsnNode.class, instruction, "Consume the policy result in a branch: " + predicate);
        var branch = (JumpInsnNode) instruction;
        assertTrue(branch.getOpcode() == Opcodes.IFEQ || branch.getOpcode() == Opcodes.IFNE);
        boolean jump = branch.getOpcode() == Opcodes.IFNE ? value : !value;
        return jump ? branch.label : branch.getNext();
    }
    private AbstractInsnNode afterNonNullGuardBeforeCall(MethodNode method, String name) {
        // The finder result is cached before enabled/observation logic. The last
        // reference check before handleCreeper controls the global emergency block.
        for (var instruction = call(method, name).getPrevious(); instruction != null; instruction = instruction.getPrevious()) {
            if (instruction instanceof JumpInsnNode branch
                    && (branch.getOpcode() == Opcodes.IFNULL || branch.getOpcode() == Opcodes.IFNONNULL)) {
                return branch.getOpcode() == Opcodes.IFNONNULL ? branch.label : branch.getNext();
            }
        }
        throw new AssertionError("Missing imminent-creeper null guard before " + name);
    }
    private record FlowState(AbstractInsnNode instruction, Map<Integer, Boolean> locals, Boolean value) {}

    /** Follow compiled branches with only contact predicates or the fallback field fixed.
     * Boolean locals preserve short-circuit contact expressions through ISTORE/ILOAD. */
    private Set<String> reachableCalls(AbstractInsnNode start, Map<String, Boolean> fields,
            Map<String, Boolean> predicates) {
        var queue = new ArrayDeque<FlowState>();
        var visited = new HashSet<FlowState>();
        var calls = new HashSet<String>();
        queue.add(new FlowState(start, Map.of(), null));
        while (!queue.isEmpty()) {
            var state = queue.removeFirst();
            if (!visited.add(state)) continue;
            var instruction = state.instruction();
            var locals = state.locals();
            Boolean value = state.value();
            int opcode = instruction.getOpcode();
            if (instruction instanceof MethodInsnNode call) {
                calls.add(call.name);
                value = predicates.get(call.name);
            } else if (instruction instanceof FieldInsnNode field && opcode == Opcodes.PUTFIELD) {
                calls.add("write:" + field.name);
            } else if (opcode == Opcodes.ICONST_0 || opcode == Opcodes.ICONST_1) {
                value = opcode == Opcodes.ICONST_1;
            } else if (instruction instanceof FieldInsnNode field && opcode == Opcodes.GETFIELD) {
                value = fields.get(field.name);
            } else if (instruction instanceof VarInsnNode variable) {
                if (opcode == Opcodes.ILOAD) value = locals.get(variable.var);
                else if (opcode == Opcodes.ISTORE) {
                    var next = new HashMap<>(locals);
                    if (value == null) next.remove(variable.var); else next.put(variable.var, value);
                    locals = Map.copyOf(next);
                    value = null;
                }
            }
            if (opcode >= Opcodes.IRETURN && opcode <= Opcodes.RETURN || opcode == Opcodes.ATHROW) continue;
            if (instruction instanceof JumpInsnNode branch) {
                if (opcode == Opcodes.GOTO) {
                    queue.add(new FlowState(branch.label, locals, value));
                    continue;
                }
                if (value != null && (opcode == Opcodes.IFEQ || opcode == Opcodes.IFNE)) {
                    boolean jump = opcode == Opcodes.IFNE ? value : !value;
                    queue.add(new FlowState(jump ? branch.label : instruction.getNext(), locals, null));
                    continue;
                }
                queue.add(new FlowState(branch.label, locals, null));
                value = null;
            }
            if (instruction.getNext() != null) queue.add(new FlowState(instruction.getNext(), locals, value));
        }
        return calls;
    }
    private Set<String> reachableCalls(MethodNode method, boolean meteorOwnsAttack) {
        var queue = new ArrayDeque<AbstractInsnNode>();
        var visited = new HashSet<AbstractInsnNode>();
        var calls = new HashSet<String>();
        queue.add(method.instructions.getFirst());
        while (!queue.isEmpty()) {
            var i = queue.removeFirst();
            if (!visited.add(i)) continue;
            if (i instanceof MethodInsnNode c) calls.add(c.name);
            int opcode = i.getOpcode();
            if (opcode >= Opcodes.IRETURN && opcode <= Opcodes.RETURN || opcode == Opcodes.ATHROW) continue;
            if (i instanceof JumpInsnNode branch) {
                if (opcode == Opcodes.GOTO) { queue.add(branch.label); continue; }
                var value = i.getPrevious();
                while (value != null && value.getOpcode() < 0) value = value.getPrevious();
                if (value instanceof VarInsnNode load && load.getOpcode() == Opcodes.ILOAD && load.var == 4) {
                    assertTrue(opcode == Opcodes.IFEQ || opcode == Opcodes.IFNE);
                    boolean jump = opcode == Opcodes.IFNE ? meteorOwnsAttack : !meteorOwnsAttack;
                    queue.add(jump ? branch.label : i.getNext()); continue;
                }
                queue.add(branch.label);
            }
            if (i.getNext() != null) queue.add(i.getNext());
        }
        return calls;
    }
}
