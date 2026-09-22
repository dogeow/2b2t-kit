package dev.twob2tkit.runtime.engine;
import java.util.*;
import net.minecraft.core.*;

/** Search only nearby safe air; an unseen threat never authorizes digging a wall. */
final class CombatPeekPath {
 interface World {boolean clear(BlockPos p);boolean edge(BlockPos a,BlockPos b);boolean visible(BlockPos p);}
 static List<BlockPos> find(World world,BlockPos start,int radius,int budget){
  if(!world.clear(start))return List.of();
  var queue=new ArrayDeque<BlockPos>();var parents=new HashMap<BlockPos,BlockPos>();
  queue.add(start);parents.put(start,null);int expanded=0;
  while(!queue.isEmpty()&&expanded++<budget){
   var p=queue.remove();
   if(!p.equals(start)&&world.visible(p)){
    var path=new LinkedList<BlockPos>();for(var n=p;n!=null;n=parents.get(n))path.addFirst(n);
    return path.size()<=32?List.copyOf(path):List.of();
   }
   for(var direction:Direction.values()){
    var q=p.relative(direction);
    if(parents.containsKey(q)||Math.abs(q.getX()-start.getX())>radius||Math.abs(q.getZ()-start.getZ())>radius||Math.abs(q.getY()-start.getY())>8||!world.clear(q)||!world.edge(p,q))continue;
    parents.put(q,p);queue.add(q);
   }
  }
  return List.of();
 }
 private CombatPeekPath(){}
}
