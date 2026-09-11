package dev.twob2tkit.concrete;

/** Pure decisions: the locked cell may contain only air/water or the selected color. */
public final class ConcretePolicy {
    private ConcretePolicy() {}
    public enum Cell { EMPTY, POWDER, CONCRETE, FOREIGN }
    public enum Action { PLACE, WAIT_WATER, MINE, VERIFY_BREAK, STOP }
    public static String solidId(String powder) {
        if (powder == null || !powder.matches("minecraft:(white|orange|magenta|light_blue|yellow|lime|pink|gray|light_gray|cyan|purple|blue|brown|green|red|black)_concrete_powder")) return null;
        return powder.substring(0, powder.length()-7);
    }
    public static Action action(Cell cell, boolean breaking, boolean submitted) {
        return switch(cell) {
            case FOREIGN -> Action.STOP;
            case POWDER -> Action.WAIT_WATER;
            case CONCRETE -> Action.MINE;
            case EMPTY -> breaking ? Action.VERIFY_BREAK : submitted ? Action.WAIT_WATER : Action.PLACE;
        };
    }
    public static boolean usableTool(boolean correct, boolean damageable, int max, int damage, int reservePercent) {
        return correct && (!damageable || max-damage>8 && (long)(max-damage)*100>=(long)max*Math.clamp(reservePercent,1,100));
    }
    public static boolean reached(int completed,int limit) { return limit>0 && completed>=limit; }
}
