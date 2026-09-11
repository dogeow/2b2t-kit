package dev.twob2tkit.concrete;

/** Only server block updates can complete a cycle; client prediction cannot create a result. */
public final class ConcreteConfirmation {
    private boolean solid, mining, removed;
    public void reset(boolean existingSolid){solid=existingSolid;mining=false;removed=false;}
    public void observe(boolean serverSolid,boolean serverEmpty){
        if(serverSolid){solid=true;removed=false;}
        else if(serverEmpty && solid && mining)removed=true;
    }
    public boolean canMine(){return solid && !removed;}
    public void beginMining(){if(solid)mining=true;}
    public boolean removed(){return removed;}
}
