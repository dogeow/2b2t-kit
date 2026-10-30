package dev.twob2tkit.automation;
import java.util.List;
final class ProjectedTrapdoorRowPolicy {
    record Bounds(int minX,int y,int z,int maxX){boolean valid(){return (long)maxX-minX==28&&minX>-30000000&&maxX<30000000&&Math.abs((long)z)<30000000&&y> -64&&y<319;}}
    record Cell(boolean originalClosedBottom,boolean unchangedStructure,boolean floorSeal,boolean backSeal,boolean inwardSeal,boolean priorWetPreserved,boolean quietWire){}
    private ProjectedTrapdoorRowPolicy(){}
    static boolean exclusive(boolean place,boolean falling,boolean drain,boolean channel,boolean sources,boolean supply,boolean bent){return place&&!falling&&!drain&&!channel&&!sources&&!supply&&!bent;}
    static String rejection(Bounds bounds,List<Cell> cells,int index,boolean before,boolean targetDry,boolean targetValid,boolean ends){
        if(bounds==null||!bounds.valid()||cells==null||cells.size()!=29||index<0||index>=29)return "Exact original29-cell trapdoor row required";
        if(!ends)return "Both original dry full row caps required";
        for(var c:cells){
            if(c==null||!c.originalClosedBottom||!c.unchangedStructure)return "Only original closed unpowered bottom trapdoors may be filled";
            if(!c.floorSeal||!c.backSeal||!c.inwardSeal)return "Trapdoor row does not contain its source water";
            if(!c.priorWetPreserved)return "An existing waterlogged row source changed";
            if(!c.quietWire)return "Spawn-floor control wire must remain unpowered during filling";
        }
        if(before?!targetDry:!targetValid)return "Target already waterlogged or state changed";
        return null;
    }
}
