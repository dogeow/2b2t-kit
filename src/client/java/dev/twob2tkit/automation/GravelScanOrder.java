package dev.twob2tkit.automation;

/** Visit nearby sea columns before expanding to each outer square ring. */
final class GravelScanOrder {
    private GravelScanOrder() {}
    record Offset(int x,int z,int ring) {}
    static int size(int radius){return (2*radius+1)*(2*radius+1);}
    static Offset at(int index){
        if(index<0)throw new IllegalArgumentException("Negative scan index");
        if(index==0)return new Offset(0,0,0);
        int ring=(int)Math.ceil((Math.sqrt(index+1)-1)/2);
        int offset=index-(2*ring-1)*(2*ring-1);
        int side=2*ring;
        if(offset<side)return new Offset(-ring+offset,-ring,ring);
        offset-=side;
        if(offset<side)return new Offset(ring,-ring+offset,ring);
        offset-=side;
        if(offset<side)return new Offset(ring-offset,ring,ring);
        offset-=side;
        return new Offset(-ring,ring-offset,ring);
    }
}
