package dev.twob2tkit.chopper;

/** Runtime safety is separate from the conservative whole-cell pathfinding predicate. */
final class ChopperFlightSafety {
    enum Kind { CLEAR, UNLOADED, OUT_OF_WORLD, PENDING, FLUID, FIRE, COBWEB, POWDER_SNOW }
    enum Action { MOVE, WAIT, STOP }
    static Kind classify(boolean loaded,boolean inside,boolean pending,boolean fluid,boolean fire,boolean web,boolean powderSnow) {
        if(!inside)return Kind.OUT_OF_WORLD;
        if(!loaded)return Kind.UNLOADED;
        if(pending)return Kind.PENDING;
        if(fluid)return Kind.FLUID;
        if(fire)return Kind.FIRE;
        if(web)return Kind.COBWEB;
        if(powderSnow)return Kind.POWDER_SNOW;
        return Kind.CLEAR;
    }
    static Action action(Kind kind,int waitTicks) {
        if(kind==Kind.CLEAR)return Action.MOVE;
        if(kind==Kind.PENDING||kind==Kind.UNLOADED)return waitTicks<100?Action.WAIT:Action.STOP;
        return Action.STOP;
    }
}
