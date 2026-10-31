package dev.twob2tkit.automation;

final class SourceColumnSupplyPolicy {
    private SourceColumnSupplyPolicy(){}
    static boolean exclusiveFill(boolean fill,boolean falling,boolean drain,boolean channel,boolean place){
        return fill&&!falling&&!drain&&!channel&&!place;
    }
    static boolean completedChamber(java.util.List<Integer> levels,int excludedMiddle){
        return completedChamber(levels,excludedMiddle,27);
    }
    static boolean completedChamber(java.util.List<Integer> levels,int excludedMiddle,int count){
        if((count!=12&&count!=27)||levels==null||levels.size()!=count||excludedMiddle< -1||excludedMiddle>=count||excludedMiddle>=0&&excludedMiddle%3!=1)return false;
        for(int i=0;i<count;i++){
            Integer value=levels.get(i);if(value==null||value< -1||value>15||i!=excludedMiddle&&value!=0)return false;
        }
        return true;
    }
    static boolean completedTop(java.util.List<Integer> goals,java.util.List<Integer> actual){return java.util.List.of(2,1,0).equals(goals)&&goals.equals(actual);}
    static boolean ready(boolean middle,int left,int center,int right,boolean supported){
        return middle&&left==0&&center==0&&right==0&&supported;
    }
    static boolean entityBlocks(boolean fill,boolean verifiedSupply,boolean localPlayer){
        return !(fill&&verifiedSupply&&localPlayer);
    }
}
