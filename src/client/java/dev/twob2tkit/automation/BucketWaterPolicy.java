package dev.twob2tkit.automation;

/** One water-only use needs two independent, post-send server receipts. */
final class BucketWaterPolicy {
    enum Mode { FILL, PLACE }
    private BucketWaterPolicy() {}

    static boolean allowedHand(Mode mode,String item,int count) {
        return count==1 && (mode==Mode.FILL?"minecraft:bucket":"minecraft:water_bucket").equals(item);
    }
    static boolean exactDelta(Mode mode,int emptyBefore,int waterBefore,int emptyAfter,int waterAfter) {
        if(emptyBefore<0||waterBefore<0||emptyAfter<0||waterAfter<0)return false;
        int delta=mode==Mode.FILL?-1:1;
        return emptyAfter-emptyBefore==delta && waterAfter-waterBefore==-delta;
    }
    static boolean selectedPacketSlot(int selected,int containerId,int slot,boolean directInventory) {
        return selected>=0&&selected<9&&(directInventory?slot==selected:containerId==0&&slot==36+selected);
    }
    static boolean source(boolean plainWater,boolean source,int level,boolean blockEntity) {
        return plainWater&&source&&level==0&&!blockEntity;
    }
    static boolean fillResult(boolean air,boolean plainWater) {
        // Infinite/natural sources can refill before their server block update arrives.
        return air||plainWater;
    }
    static boolean boundedHole(boolean air,boolean fluidEmpty,boolean blockEntity,boolean bottom,
                               int dryFullSideCount,boolean evaporates) {
        return air&&fluidEmpty&&!blockEntity&&bottom&&dryFullSideCount==4&&!evaporates;
    }

    static final class Receipt {
        private boolean sent,blockSeen,blockConfirmed,inventorySeen,inventoryConfirmed;
        private long blockTick=-1,inventoryTick=-1;
        private String blockState="";
        void sendOnce() {
            if(sent)throw new IllegalStateException("A bucket use was already sent; no retry is allowed");
            sent=true;
        }
        void block(boolean sameContext,boolean sameTarget,boolean applied,String state,boolean expected,long tick) {
            if(!sent||!sameContext||!sameTarget||!applied)return;
            blockSeen=true;blockState=state;blockConfirmed=expected;blockTick=expected?tick:-1;
        }
        void inventory(boolean sameContext,boolean selectedSlot,boolean applied,boolean expected,long tick) {
            if(!sent||!sameContext||!selectedSlot||!applied)return;
            inventorySeen=true;inventoryConfirmed=expected;inventoryTick=expected?tick:-1;
        }
        boolean done(boolean context,boolean exactInventory,boolean sameCurrentBlock,long tick) {
            return sent&&context&&exactInventory&&sameCurrentBlock&&blockConfirmed&&inventoryConfirmed
                &&blockTick>=0&&inventoryTick>=0&&tick-Math.max(blockTick,inventoryTick)>=8;
        }
        boolean sent(){return sent;}
        boolean blockSeen(){return blockSeen;}
        boolean blockConfirmed(){return blockConfirmed;}
        boolean inventorySeen(){return inventorySeen;}
        boolean inventoryConfirmed(){return inventoryConfirmed;}
        String blockState(){return blockState;}
    }
}
