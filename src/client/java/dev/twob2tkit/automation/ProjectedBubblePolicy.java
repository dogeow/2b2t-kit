package dev.twob2tkit.automation;
import java.util.List;
/** Bottom-up source conversion; 0 is a transient source, 1 is an upward bubble. */
final class ProjectedBubblePolicy {
 private ProjectedBubblePolicy(){}
 static boolean stage(List<Integer> states,int index,boolean before){
  if(states==null||states.size()!=7||index<0||index>=7)return false;
  for(int i=0;i<7;i++){
   Integer v=states.get(i);if(v==null)return false;
   if(i<index?v!=1:i>index?v!=-1:before?v!=-1:v!=0&&v!=1)return false;
  }return true;
 }
 static boolean exclusive(boolean place,boolean... other){if(!place)return false;for(boolean v:other)if(v)return false;return true;}
 static int outletDx(int index){if(index<1||index>7)throw new IllegalArgumentException("Outlet index1..7 required");return -Math.min(index,6);}
 static int outletDz(int index){if(index<1||index>7)throw new IllegalArgumentException("Outlet index1..7 required");return index==7?-1:0;}
}
