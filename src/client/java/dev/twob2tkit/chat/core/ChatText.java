package dev.twob2tkit.chat.core;

import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/** Splits familiar chat envelopes without discarding their original spelling or formatting. */
public record ChatText(String prefix, String body) {
    private static final String FORMAT = "(?:§[0-9a-fk-orx])";
    private static final Pattern FORMATTING = Pattern.compile(FORMAT, Pattern.CASE_INSENSITIVE);
    private static final Pattern ANGLE_NAME = Pattern.compile(
            "^(" + FORMAT + "*<[^<>\\r\\n]{1,96}>" + FORMAT + "*[ \\t]*)([\\s\\S]*)$",
            Pattern.CASE_INSENSITIVE);
    private static final Pattern SIMPLE_NAME = Pattern.compile(
            "^(" + FORMAT + "*[\\p{L}\\p{N}_~.\\-]{1,32}" + FORMAT
                    + "*[:：]" + FORMAT + "*[ \\t]+)([\\s\\S]*)$",
            Pattern.CASE_INSENSITIVE);

    public ChatText {
        Objects.requireNonNull(prefix, "prefix");
        Objects.requireNonNull(body, "body");
    }

    public static ChatText parse(String message) {
        Objects.requireNonNull(message, "message");
        Matcher matcher = ANGLE_NAME.matcher(message);
        if (matcher.matches()) {
            return new ChatText(matcher.group(1), matcher.group(2));
        }
        matcher = SIMPLE_NAME.matcher(message);
        if (matcher.matches()) {
            return new ChatText(matcher.group(1), matcher.group(2));
        }
        return new ChatText("", message);
    }

    /** Only the string sent for translation loses Minecraft's legacy formatting codes. */
    public String translationInput() {
        return stripFormatting(body);
    }

    public String withTranslation(String translation) {
        return prefix + Objects.requireNonNull(translation, "translation");
    }

    public static String stripFormatting(String text) {
        return FORMATTING.matcher(Objects.requireNonNull(text, "text")).replaceAll("");
    }
}
