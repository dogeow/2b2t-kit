package dev.twob2tkit.automation;
final class ProjectedObserverPlacementPolicy {
    record Angles(float yaw,float pitch){}
    private ProjectedObserverPlacementPolicy(){}
    static Angles look(String facing){return switch(facing){
        case "north"->new Angles(180,0);case "south"->new Angles(0,0);
        case "west"->new Angles(90,0);case "east"->new Angles(-90,0);
        case "up"->new Angles(0,-90);case "down"->new Angles(0,90);
        default->throw new IllegalArgumentException("A normal six-direction observer face is required");
    };}
}
