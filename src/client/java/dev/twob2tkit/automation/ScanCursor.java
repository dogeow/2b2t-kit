package dev.twob2tkit.automation;

import java.util.function.Consumer;
import java.util.function.LongSupplier;

/** Ordered inclusive scan cursor; only the client tick supplies world reads. */
final class ScanCursor {
    static final int MAX_CELLS=50_000,DETAILS_PER_TICK=512,PLAIN_PER_TICK=2048;
    static final long TICK_NANOS=2_000_000;
    record Cell(int x,int y,int z) {}
    private final int x1,y1,z1,ys,zs,total;
    private int read;
    ScanCursor(int x1,int y1,int z1,int x2,int y2,int z2) {
        long xs=(long)x2-x1+1,ys=(long)y2-y1+1,zs=(long)z2-z1+1;
        if(xs<=0||ys<=0||zs<=0||xs>MAX_CELLS||ys>MAX_CELLS||zs>MAX_CELLS
                ||xs*ys*zs>MAX_CELLS)throw new IllegalArgumentException("Invalid scan volume");
        this.x1=x1;this.y1=y1;this.z1=z1;this.ys=(int)ys;this.zs=(int)zs;this.total=(int)(xs*ys*zs);
    }
    int advance(boolean details,LongSupplier nanoTime,Consumer<Cell> reader) {
        int limit=details?DETAILS_PER_TICK:PLAIN_PER_TICK,count=0;long start=nanoTime.getAsLong();
        while(read<total&&count<limit&&(count==0||nanoTime.getAsLong()-start<TICK_NANOS)) {
            int column=read/ys;reader.accept(new Cell(x1+column/zs,y1+read%ys,z1+column%zs));
            read++;count++;
        }
        return count;
    }
    boolean done(){return read==total;}
    int read(){return read;}
    int total(){return total;}
}
