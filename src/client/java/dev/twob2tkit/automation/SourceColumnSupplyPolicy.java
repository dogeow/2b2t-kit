package dev.twob2tkit.automation;

final class SourceColumnSupplyPolicy {
    private SourceColumnSupplyPolicy(){}
    static boolean exclusiveFill(boolean fill,boolean falling,boolean drain,boolean channel,boolean place){
        return fill&&!falling&&!drain&&!channel&&!place;
    }
    static boolean ready(boolean middle,int left,int center,int right,boolean supported){
        return middle&&left==0&&center==0&&right==0&&supported;
    }
    static boolean entityBlocks(boolean fill,boolean verifiedSupply,boolean localPlayer){
        return !(fill&&verifiedSupply&&localPlayer);
    }
}
