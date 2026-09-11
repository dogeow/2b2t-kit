package dev.twob2tkit.automation;

/** Leave time for the native printer queue and multiplayer inventory/block updates. */
public final class PrinterPulse {
    private PrinterPulse() {}
    public static boolean allowProposal(int elapsedTicks){return elapsedTicks%20==0;}
}
