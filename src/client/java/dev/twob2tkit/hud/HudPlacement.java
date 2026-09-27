package dev.twob2tkit.hud;

public final class HudPlacement {
    private HudPlacement() {}
    public record Rect(double x,double y,double width,double height) {
        public boolean valid(){return Double.isFinite(x)&&Double.isFinite(y)&&Double.isFinite(width)&&Double.isFinite(height)&&width>0&&height>0;}
    }
    /** Jade rectangles already include its UI scale. Never clamp back into its occupied area. */
    public static int below(int x,int width,int height,int screenHeight,Rect... occupied) {
        int y=8;
        for(Rect r:occupied)if(r!=null&&r.valid()&&x<r.x+r.width&&x+width>r.x)
            y=Math.max(y,(int)Math.ceil(r.y+r.height)+6);
        return y+height<=screenHeight/2-16?y:-1;
    }
}
