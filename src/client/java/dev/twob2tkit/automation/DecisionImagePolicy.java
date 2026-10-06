package dev.twob2tkit.automation;

/** Only a bounded game frame, never a desktop or arbitrary file. */
public final class DecisionImagePolicy {
    private DecisionImagePolicy() {}
    public static boolean validId(String id){return id!=null&&id.matches("[A-Za-z0-9_-]{1,96}");}
    public record Size(int width,int height) {}
    public static Size boundedSize(int width,int height){
        if(width<1||height<1)throw new IllegalArgumentException("Invalid game framebuffer");
        double scale=Math.min(1,Math.min(640.0/width,360.0/height));
        return new Size(Math.max(1,(int)Math.floor(width*scale)),Math.max(1,(int)Math.floor(height*scale)));
    }
    public static boolean scope(boolean sameWorld,boolean player,boolean screenClosed,long expected,long actual,double movement){
        return sameWorld&&player&&screenClosed&&expected==actual&&Double.isFinite(movement)&&movement<=2;
    }
}
