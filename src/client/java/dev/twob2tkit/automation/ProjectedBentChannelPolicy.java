package dev.twob2tkit.automation;
import java.util.List;
final class ProjectedBentChannelPolicy {
    private ProjectedBentChannelPolicy() {}
    static int dx(int i){return -Math.min(i,3);}
    static int dz(int i){return Math.max(0,i-3);}
    static int dx(int i,int rows){if(rows!=4&&rows!=9||i<0||i>7)throw new IllegalArgumentException("Exact profiled path required");return -Math.min(i,rows==4?5:3);}
    static int dz(int i,int rows){if(rows!=4&&rows!=9||i<0||i>7)throw new IllegalArgumentException("Exact profiled path required");return Math.max(0,i-(rows==4?5:3));}
    static boolean collectLevels(List<Integer> goal,List<Integer> actual,int index,boolean before){
        if(index!=1&&index!=2||!levels(goal,actual,false))return false;
        return !before||actual.equals(index==2?List.of(0,0,0,1,2,3,4,5):List.of(0,0,1,2,3,4,5,6));
    }
    static boolean exclusive(boolean place,boolean column,boolean drain,boolean channel,boolean sources,boolean supply){
        return place&&!column&&!drain&&!channel&&!sources&&!supply;
    }
    static boolean seedLevels(List<Integer> goal,List<Integer> actual,boolean before){
        return levels(goal,actual,false)&&(before?actual.get(2)==-1:actual.get(2)==0);
    }
    static boolean levels(List<Integer> goal,List<Integer> actual,boolean before){
        if(goal==null||actual==null||goal.size()!=8||actual.size()!=8)return false;
        for(int i=0;i<8;i++){
            if(goal.get(i)==null||actual.get(i)==null||goal.get(i)!=i)return false;
            int v=actual.get(i);
            if(before?v!=-1:v< -1||v>15||i==0&&v!=0)return false;
        }
        return true;
    }
}
