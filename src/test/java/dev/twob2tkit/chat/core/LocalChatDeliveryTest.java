package dev.twob2tkit.chat.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.*;

class LocalChatDeliveryTest {
    @Test void localDeliveryIsMarkedOnlyForTheSynchronousScope() {
        assertFalse(LocalChatDelivery.isActive());
        LocalChatDelivery.run(() -> {
            assertTrue(LocalChatDelivery.isActive());
            LocalChatDelivery.run(() -> assertTrue(LocalChatDelivery.isActive()));
            assertTrue(LocalChatDelivery.isActive());
        });
        assertFalse(LocalChatDelivery.isActive());
    }

    @Test void failedLocalDeliveryDoesNotExcludeSubsequentServerMessages() {
        assertThrows(IllegalStateException.class, () -> LocalChatDelivery.run(() -> {
            throw new IllegalStateException("delivery failed");
        }));
        assertFalse(LocalChatDelivery.isActive());
    }
}
