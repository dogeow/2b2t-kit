package dev.twob2tkit.map;

/** A map click selects coordinates in the currently connected dimension. */
public final class MapCruiseTarget {
    private MapCruiseTarget(){}
    public static boolean allowed(String current,String selected,double x,double z){
        return current!=null&&current.equals(selected)&&Double.isFinite(x)&&Double.isFinite(z)
            &&Math.abs(x)<29_999_984&&Math.abs(z)<29_999_984;
    }
}
