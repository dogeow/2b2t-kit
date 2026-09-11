package dev.twob2tkit.runtime.engine;

import net.minecraft.core.BlockPos;
import java.util.ArrayDeque;
import java.util.HashMap;
import java.util.Map;
import java.util.Set;

/** Shallow-area policy and a bounded route through already cleared body space. Never tunnels outside the selection. */
final class BorerAreaHorizontal {
    static boolean enabled(BlockPos min, BlockPos max) {
        long height = (long)max.getY() - min.getY() + 1;
        return height >= 1 && height <= 6;
    }
    static boolean bodyClear(BorerAreaPlan.World world, BlockPos column, int bottom) {
        return world.cell(new BlockPos(column.getX(), bottom, column.getZ())) == BorerAreaPlan.Cell.AIR
            && world.cell(new BlockPos(column.getX(), bottom + 1, column.getZ())) == BorerAreaPlan.Cell.AIR;
    }
    record Route(boolean found, boolean unknown, BlockPos step) {}
    static Route route(BorerAreaPlan.World world, BlockPos min, BlockPos max, BlockPos from, BlockPos target, Set<Long> visited) {
        if (from.distManhattan(target) <= 1) return new Route(true, false, from);
        var queue = new ArrayDeque<BlockPos>();
        Map<BlockPos, BlockPos> previous = new HashMap<>();
        queue.add(from); previous.put(from, from); boolean unknown = false;
        while (!queue.isEmpty()) {
            BlockPos at = queue.removeFirst();
            if (at.distManhattan(target) <= 1) {
                BlockPos next = at;
                while (!previous.get(next).equals(from)) next = previous.get(next);
                return new Route(true, false, next);
            }
            for (BlockPos next : new BlockPos[]{at.east(), at.south(), at.west(), at.north()}) {
                if (next.getX() < min.getX() || next.getX() > max.getX() || next.getZ() < min.getZ() || next.getZ() > max.getZ()
                    || previous.containsKey(next) || !visited.contains(key(next))) continue;
                var feet = world.cell(new BlockPos(next.getX(), min.getY(), next.getZ()));
                var head = world.cell(new BlockPos(next.getX(), min.getY() + 1, next.getZ()));
                if (feet == BorerAreaPlan.Cell.UNLOADED || head == BorerAreaPlan.Cell.UNLOADED) unknown = true;
                if (feet != BorerAreaPlan.Cell.AIR || head != BorerAreaPlan.Cell.AIR) continue;
                previous.put(next, at); queue.addLast(next);
            }
        }
        return new Route(false, unknown, null);
    }
    static long key(BlockPos p) { return ((long)p.getX() << 32) ^ (p.getZ() & 0xffffffffL); }
    private BorerAreaHorizontal() {}
}
