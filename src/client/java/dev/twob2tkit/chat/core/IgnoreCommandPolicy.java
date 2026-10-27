package dev.twob2tkit.chat.core;

import java.util.LinkedHashSet;
import java.util.Locale;
import java.util.Optional;
import java.util.Set;
import java.util.regex.Pattern;

/**
 * Strict support for EssentialsX's stock ignore-list replies.
 * The caller must also establish a pending query and a server-system message origin;
 * matching text alone does not authenticate a command response.
 */
public final class IgnoreCommandPolicy {
    private static final Pattern FORMATTING = Pattern.compile("§[0-9a-fk-orx]", Pattern.CASE_INSENSITIVE);
    private static final Pattern PLAYER_NAME = Pattern.compile("[A-Za-z0-9_]{1,16}");
    private static final Pattern NAME_LIST = Pattern.compile("[A-Za-z0-9_]{1,16}(?: [A-Za-z0-9_]{1,16})*");
    private static final int MAX_REPLY_LENGTH = 32768;

    private IgnoreCommandPolicy() {}

    /**
     * Returns a known list (possibly empty), or empty Optional for every unknown reply.
     * Names are normalized to lowercase. No chat prefixes, inferred punctuation,
     * comma-separated lists, custom locale strings or partial matches are accepted.
     *
     * Sources: EssentialsX/Essentials, branch 2.x:
     * Essentials/src/main/resources/messages.properties and messages_zh.properties;
     * Essentials/src/main/java/com/earth2me/essentials/commands/Commandignore.java.
     */
    public static Optional<Set<String>> parseIgnoredList(String text) {
        if (text == null || text.length() > MAX_REPLY_LENGTH) return Optional.empty();
        String plain = FORMATTING.matcher(text).replaceAll("");
        if (plain.equals("You are not ignoring anyone.") || plain.equals("你没有屏蔽任何人。")) {
            return Optional.of(Set.of());
        }
        String names;
        if (plain.startsWith("Ignored: ")) {
            names = plain.substring("Ignored: ".length());
        } else if (plain.startsWith("已屏蔽的玩家：")) {
            names = plain.substring("已屏蔽的玩家：".length());
        } else {
            return Optional.empty();
        }
        if (!NAME_LIST.matcher(names).matches()) return Optional.empty();
        Set<String> ignored = new LinkedHashSet<>();
        for (String name : names.split(" ")) ignored.add(name.toLowerCase(Locale.ROOT));
        return Optional.of(Set.copyOf(ignored));
    }

    public static boolean isValidPlayerName(String name) {
        return name != null && PLAYER_NAME.matcher(name).matches();
    }

    public static boolean alreadyIgnored(Set<String> ignored, String playerName) {
        return ignored != null && isValidPlayerName(playerName)
                && ignored.stream().anyMatch(playerName::equalsIgnoreCase);
    }

    /** A toggle is proposed only after a complete known list excludes the player. */
    public static Optional<String> commandForUnignoredPlayer(String playerName, Set<String> confirmedIgnored) {
        if (!isValidPlayerName(playerName) || confirmedIgnored == null
                || confirmedIgnored.stream().anyMatch(name -> !isValidPlayerName(name))
                || alreadyIgnored(confirmedIgnored, playerName)) {
            return Optional.empty();
        }
        return Optional.of("essentials:ignore " + playerName);
    }
}
