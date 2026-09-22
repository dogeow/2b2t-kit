package dev.twob2tkit.automation;
/** Local collector ownership expires on manual control changes or a different defense mode. */
final class MaterialControlPolicy {
    private MaterialControlPolicy(){}
    static boolean owned(long leaseRevision,long currentRevision,boolean pve){return leaseRevision==currentRevision&&pve;}
}
