package dev.twob2tkit.map;

import dev.twob2tkit.borer.BorerAreaMarks;
import dev.twob2tkit.borer.AreaDrafts;

/** Convert an Xaero viewport gesture into an inclusive pair of mining draft corners. */
public final class MapAreaSelection {
    private MapAreaSelection() {}

    public record Point(int x, int z) {}

    public static int blockAt(double pointer, int pixels, double camera, double scale) {
        return (int)Math.floor(camera+((int)pointer-pixels/2)/scale);
    }

    public static boolean dragged(double startX,double startY,double x,double y) {
        return Math.hypot(x-startX,y-startY)>=4;
    }

    public static boolean fits(Point a, Point b) {
        return Math.abs((long)a.x()-b.x())<BorerAreaMarks.MAX_SPAN
            && Math.abs((long)a.z()-b.z())<BorerAreaMarks.MAX_SPAN;
    }

    public static AreaDrafts.Draft fill(AreaDrafts.Draft draft, Point a, Point b, int upperY, int lowerY) {
        if (!fits(a,b)) throw new IllegalArgumentException("区域超出 "+BorerAreaMarks.MAX_SPAN+"×"+BorerAreaMarks.MAX_SPAN+" 格");
        int[] coords=new int[3];
        boolean hasA=BorerAreaMarks.parse(draft.a(),coords);
        int aY=hasA ? coords[1] : upperY;
        boolean hasB=BorerAreaMarks.parse(draft.b(),coords);
        int bY=hasB ? coords[1] : lowerY;
        // Equal corner heights have a special deep-excavation meaning in Kit.
        if (aY==bY && !hasB) bY=upperY;
        if (aY==bY && !hasA) aY=lowerY;
        return draft.edit(draft.name(),a.x()+" "+aY+" "+a.z(),b.x()+" "+bY+" "+b.z(),
            draft.length(),draft.width(),draft.height());
    }
}
