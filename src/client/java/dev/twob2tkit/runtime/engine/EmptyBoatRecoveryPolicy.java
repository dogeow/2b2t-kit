package dev.twob2tkit.runtime.engine;

/** Empty-vehicle recovery has no disembarking passengers; walls are not a landing failure. */
final class EmptyBoatRecoveryPolicy {
    static boolean allowed(boolean currentOwner,boolean idle,boolean healthy,boolean ordinary,
                           boolean unnamed,boolean empty,boolean ownOrNoLeash,boolean groundedDry,
                           boolean visible,boolean axe,boolean capacity,boolean quiet,double distance,double reach){
        return currentOwner&&idle&&healthy&&ordinary&&unnamed&&empty&&ownOrNoLeash&&groundedDry
            &&visible&&axe&&capacity&&quiet&&Double.isFinite(distance)&&distance>=0
            &&Double.isFinite(reach)&&reach>.2&&distance<=reach-.2;
    }
    static boolean fresh(long now,long issued,long expires,long observed){
        return issued<=now&&now-issued<=1000&&expires>now&&expires-issued>0&&expires-issued<=5000
            &&observed<=now&&now-observed<=1000;
    }
}
