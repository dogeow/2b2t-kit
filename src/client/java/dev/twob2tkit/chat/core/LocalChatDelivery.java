package dev.twob2tkit.chat.core;

/** Tracks synchronous delivery of a client-generated system message. */
public final class LocalChatDelivery {
    private static final ThreadLocal<Boolean> ACTIVE = new ThreadLocal<>();

    private LocalChatDelivery() {}

    public static boolean isActive() {
        return Boolean.TRUE.equals(ACTIVE.get());
    }

    public static void run(Runnable delivery) {
        if (isActive()) {
            delivery.run();
            return;
        }
        ACTIVE.set(true);
        try {
            delivery.run();
        } finally {
            ACTIVE.remove();
        }
    }
}
