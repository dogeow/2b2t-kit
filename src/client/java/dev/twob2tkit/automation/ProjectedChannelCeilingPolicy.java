package dev.twob2tkit.automation;

/** One declared ceiling opening, above fluid level; walls and floor stay exact. */
final class ProjectedChannelCeilingPolicy {
    private ProjectedChannelCeilingPolicy() {}
    static boolean allowedOffset(long x,long y,long z){
        return y==1&&z==0&&(x==0||x==-1);
    }
    static boolean roof(boolean originalCobblestone,boolean same,boolean air,int cell,int serviceCell){
        return originalCobblestone&&(same||air&&cell==serviceCell);
    }
}
