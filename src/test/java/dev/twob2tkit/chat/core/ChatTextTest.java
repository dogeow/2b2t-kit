package dev.twob2tkit.chat.core;

import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;

class ChatTextTest {
    @Test
    void preservesSpeakerAndOriginalFormattingWhileCleaningOnlyTranslationInput() {
        String original = "§a<小明>§r  §lHello §bworld§r!";
        ChatText message = ChatText.parse(original);
        assertEquals("§a<小明>§r  ", message.prefix());
        assertEquals("§lHello §bworld§r!", message.body());
        assertEquals("Hello world!", message.translationInput());
        assertEquals(original, message.prefix() + message.body());
        assertEquals("§a<小明>§r  你好，世界！", message.withTranslation("你好，世界！"));
    }

    @Test
    void acceptsSimpleNamesButDoesNotTreatUrlsOrTimestampsAsSpeakerNames() {
        assertEquals(new ChatText("Alex: ", "Hello there"), ChatText.parse("Alex: Hello there"));
        assertEquals(new ChatText("小明： ", "Hello"), ChatText.parse("小明： Hello"));
        assertEquals(new ChatText("", "https://example.test/chat"), ChatText.parse("https://example.test/chat"));
        assertEquals(new ChatText("", "12:30 let's go"), ChatText.parse("12:30 let's go"));
        assertEquals(new ChatText("", "[Server] Welcome"), ChatText.parse("[Server] Welcome"));
    }

    @Test
    void keepsMultilineBodiesAndNonFormattingSectionSigns() {
        ChatText message = ChatText.parse("<Alex> Hello\nthere §g!");
        assertEquals("Hello\nthere §g!", message.translationInput());
        assertEquals("Red", ChatText.stripFormatting("§x§f§f§0§0§0§0Red§r"));
        assertEquals(new ChatText("", ""), ChatText.parse(""));
    }
}
