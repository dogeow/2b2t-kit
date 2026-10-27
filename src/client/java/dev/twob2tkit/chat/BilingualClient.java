package dev.twob2tkit.chat;

import com.mojang.authlib.GameProfile;
import com.mojang.brigadier.arguments.StringArgumentType;
import dev.twob2tkit.chat.core.ChatText;
import dev.twob2tkit.chat.core.IgnoreCommandPolicy;
import dev.twob2tkit.chat.core.SpamGuard;
import dev.twob2tkit.chat.core.TranslationClient;
import dev.twob2tkit.chat.core.LocalHelperService;
import dev.twob2tkit.chat.core.TranslationClicks;
import net.fabricmc.api.ClientModInitializer;
import net.fabricmc.fabric.api.client.command.v2.ClientCommandRegistrationCallback;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientLifecycleEvents;
import net.fabricmc.fabric.api.client.event.lifecycle.v1.ClientTickEvents;
import net.fabricmc.fabric.api.client.message.v1.ClientReceiveMessageEvents;
import net.fabricmc.fabric.api.client.message.v1.ClientSendMessageEvents;
import net.fabricmc.fabric.api.client.networking.v1.ClientPlayConnectionEvents;
import net.fabricmc.loader.api.FabricLoader;
import net.minecraft.ChatFormatting;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;
import net.minecraft.client.multiplayer.chat.GuiMessage;
import net.minecraft.client.multiplayer.chat.GuiMessageSource;
import net.minecraft.network.chat.ClickEvent;
import net.minecraft.network.chat.Component;
import net.minecraft.network.chat.HoverEvent;
import net.minecraft.network.chat.MessageSignature;
import net.minecraft.network.chat.Style;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;

import java.nio.file.Path;
import java.util.ArrayDeque;
import java.util.HashSet;
import java.util.Locale;
import java.util.Set;
import java.util.concurrent.CompletableFuture;
import java.util.function.Consumer;
import java.util.regex.Pattern;

import static net.fabricmc.fabric.api.client.command.v2.ClientCommands.argument;
import static net.fabricmc.fabric.api.client.command.v2.ClientCommands.literal;

/** Owns chat only; never captures the screen or participates in gameplay controllers. */
public final class BilingualClient implements ClientModInitializer {
    private static final Logger LOG = LoggerFactory.getLogger("twob2tkit-chat");
    private static final Pattern PLAYER_NAME = Pattern.compile("[A-Za-z0-9_]{1,16}");
    private static final Path CONFIG = FabricLoader.getInstance().getConfigDir()
            .resolve("twob2tkit/chat-translation.json");
    private static final ArrayDeque<Runnable> nextTick = new ArrayDeque<>();
    private static final ArrayDeque<Receipt> receipts = new ArrayDeque<>();
    private static final Set<String> ignoreSent = new HashSet<>();
    private static ModConfig settings;
    private static TranslationClient translator;
    private static final TranslationClicks<ManualMessage> translationClicks = new TranslationClicks<>(256);
    private static final LocalHelperService helperService = new LocalHelperService();
    private static SpamGuard spam;
    private static long generation;
    private static long lastErrorNotice;
    private static String serviceStatus = "尚未检测本地翻译服务";
    private static boolean initialized;
    private static boolean sendingTranslated;
    private static boolean openRequested;
    private static CompletableFuture<Void> outgoingTail = CompletableFuture.completedFuture(null);
    private static int outgoingCount;
    private static Consumer<Screen> settingsOpener;
    private static PendingIgnore pendingIgnore;
    private static boolean ignoreQueriesDisabled;
    private static long lastIgnoreCommand;
    private static final ArrayDeque<String> ignoreQueue = new ArrayDeque<>();

    public static ModConfig config() { return settings; }
    public static String status() { return serviceStatus + " · 本地屏蔽 " + spam.blockedPlayers().size() + " 人"; }
    public static void setSettingsOpener(Consumer<Screen> opener) { settingsOpener = opener; }
    public static void openSettings(Screen parent) {
        if (settingsOpener != null) settingsOpener.accept(parent);
        else Minecraft.getInstance().setScreenAndShow(new BilingualSettingsScreen(parent,
                settings, BilingualClient::saveSettings, BilingualClient::checkHealth, BilingualClient::status));
    }

    @Override public void onInitializeClient() {
        if (initialized) return;
        initialized = true;
        settings = ModConfig.load(CONFIG);
        if (settingsOpener == null) settingsOpener = dev.twob2tkit.ChatTranslationPage::open;
        if (settings.loadWarning != null && !settings.loadWarning.isEmpty()) LOG.warn(settings.loadWarning);
        translator = new TranslationClient(settings.helperPort);
        spam = new SpamGuard(settings.spamRepeatThreshold, settings.spamWindowSeconds * 1000L);

        // Filtering happens before vanilla display, narration, and translation work.
        ClientReceiveMessageEvents.ALLOW_CHAT.register((message, signed, sender, type, time) ->
                allowIncoming(message, signed == null ? null : signed.signature(), sender));
        ClientReceiveMessageEvents.ALLOW_GAME.register((message, overlay) ->
                overlay || allowIncoming(message, null, null));
        ClientSendMessageEvents.ALLOW_CHAT.register(BilingualClient::allowOutgoing);
        ClientPlayConnectionEvents.JOIN.register((handler, packetSender, client) -> {
            resetSession();
            if (settings.enabled) startHelper(); else checkHealth();
        });
        ClientPlayConnectionEvents.DISCONNECT.register((handler, client) -> resetSession());
        ClientLifecycleEvents.CLIENT_STOPPING.register(client -> translator.close());
        ClientTickEvents.END_CLIENT_TICK.register(client -> {
            while (!nextTick.isEmpty()) nextTick.removeFirst().run();
            tickIgnoreQuery();
            if (openRequested) { openRequested = false; openSettings(client.gui.screen()); }
        });
        ClientCommandRegistrationCallback.EVENT.register((dispatcher, access) -> dispatcher.register(
                literal("mct")
                    .executes(context -> { openRequested = true; return 1; })
                    .then(literal("status").executes(context -> { checkHealth(); info(status()); return 1; }))
                    .then(literal("on").executes(context -> { settings.enabled = true; saveSettings(); startHelper(); info("聊天翻译已开启"); return 1; }))
                    .then(literal("manual").executes(context -> { settings.enabled = true; settings.onDemandTranslation = true; saveSettings(); info("按需翻译已开启，点击聊天文字或 [翻译]"); return 1; }))
                    .then(literal("auto").executes(context -> { settings.enabled = true; settings.onDemandTranslation = false; saveSettings(); startHelper(); info("自动翻译已开启"); return 1; }))
                    .then(literal("start").executes(context -> { startHelper(); return 1; }))
                    .then(literal("off").executes(context -> { settings.enabled = false; saveSettings(); info("聊天翻译已关闭，防刷屏独立生效"); return 1; }))
                    .then(literal("unblock").then(argument("player", StringArgumentType.word()).executes(context -> {
                        String name = StringArgumentType.getString(context, "player");
                        spam.unblock(name.toLowerCase(Locale.ROOT));
                        info("已解除本地屏蔽：" + name + "。服务器屏蔽请按服务器说明手动解除。"); return 1;
                    })))
                    .then(literal("unblock-all").executes(context -> { unblockAll(); return 1; }))
                    .then(literal("translate").then(argument("text", StringArgumentType.greedyString()).executes(context -> {
                        preview(StringArgumentType.getString(context, "text")); return 1;
                    })))
        ));
    }

    public static void saveSettings() {
        try { settings.save(CONFIG); }
        catch (Exception e) { LOG.warn("Cannot save chat translation settings: {}", e.getMessage()); info("设置未保存：" + e.getMessage()); }
        generation++;
        translationClicks.cancelPending();
        outgoingTail = CompletableFuture.completedFuture(null); outgoingCount = 0;
        translator.close();
        translator = new TranslationClient(settings.helperPort);
        receipts.clear();
        // Preserve existing blocks across ordinary settings edits.
        Set<String> blocked = spam.blockedPlayers();
        spam = new SpamGuard(settings.spamRepeatThreshold, settings.spamWindowSeconds * 1000L);
        for (String name : blocked) spam.block(name);
        for (ManualMessage message : translationClicks.values()) {
            message.loading = false; message.failed = false; renderTranslationMessage(message);
        }
        checkHealth();
    }

    private static void resetSession() {
        generation++;
        translationClicks.clear();
        outgoingTail = CompletableFuture.completedFuture(null); outgoingCount = 0;
        translator.close();
        translator = new TranslationClient(settings.helperPort);
        spam = new SpamGuard(settings.spamRepeatThreshold, settings.spamWindowSeconds * 1000L);
        receipts.clear(); nextTick.clear(); ignoreSent.clear(); ignoreQueue.clear(); pendingIgnore = null; ignoreQueriesDisabled = false; lastIgnoreCommand = 0; lastErrorNotice = 0;
        outgoingTail = CompletableFuture.completedFuture(null); outgoingCount = 0;
    }

    public static void unblockAll() {
        spam = new SpamGuard(settings.spamRepeatThreshold, settings.spamWindowSeconds * 1000L);
        info("已清除本次连接的本地屏蔽。服务器 /ignore 状态不变，请按服务器说明手动解除。");
    }

    public static void checkHealth() {
        TranslationClient current = translator;
        serviceStatus = "正在检测 127.0.0.1:" + settings.helperPort;
        current.health().whenComplete((ok, error) -> Minecraft.getInstance().execute(() -> {
            if (current != translator) return;
            serviceStatus = error == null && Boolean.TRUE.equals(ok)
                    ? "本地服务已连接（语言包需在助手中准备）" : "本地服务未连接，请打开翻译助手";
        }));
    }

    private static Path helperApp() {
        return CONFIG.getParent().resolve("chat-helper/Minecraft Bilingual Helper.app");
    }

    public static void startHelper() {
        TranslationClient current = translator;
        serviceStatus = "正在启动本地翻译服务…";
        helperService.start(helperApp(), System.getProperty("os.name", ""), settings.helperPort,
                () -> current.health().exceptionally(error -> false).join())
                .whenComplete((ignored, error) -> Minecraft.getInstance().execute(() -> {
                    if (current != translator) return;
                    if (error == null) {
                        current.clearCache();
                        serviceStatus = "本地服务已连接；语言包可在助手中准备";
                    } else {
                        Throwable cause = error.getCause() == null ? error : error.getCause();
                        serviceStatus = "启动未完成：" + cause.getMessage();
                    }
                }));
    }

    public static void openHelper() {
        helperService.open(helperApp(), System.getProperty("os.name", ""), settings.helperPort)
                .whenComplete((ignored, error) -> Minecraft.getInstance().execute(() -> {
                    if (error != null) serviceStatus = "无法打开助手：" + (error.getCause() == null ? error : error.getCause()).getMessage();
                    else checkHealth();
                }));
    }

    private static boolean allowIncoming(Component message, MessageSignature signature, GameProfile sender) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.getConnection() == null) return true;
        String text = message.getString();
        if (signature == null && sender == null) acceptIgnoreReply(text);
        ChatText parsed = ChatText.parse(text);
        String name = sender == null ? rosterName(parsed, mc) : sender.name();
        boolean self = name != null && mc.player != null && name.equalsIgnoreCase(mc.player.getGameProfile().name());
        if (settings.antiSpamEnabled && name != null && !self) {
            String key = name.toLowerCase(Locale.ROOT);
            SpamGuard.Decision decision = spam.inspect(key, parsed.translationInput(), System.currentTimeMillis());
            if (decision.newlyBlocked()) {
                // Defer the feedback until after this event finishes; no event recursion.
                var connection = mc.getConnection();
                long epoch = generation;
                nextTick.addLast(() -> {
                    if (generation == epoch && connection == mc.getConnection()) blockNoticeAndCommand(name);
                });
            }
            if (decision.suppress()) return false;
        }
        receipts.addLast(new Receipt(signature, text, name, self));
        while (receipts.size() > 64) receipts.removeFirst();
        return true;
    }

    /** Server-formatted messages count as players only when a simple name matches the player list. */
    private static String rosterName(ChatText parsed, Minecraft mc) {
        String prefix = ChatText.stripFormatting(parsed.prefix()).trim();
        String name = prefix.startsWith("<") && prefix.endsWith(">")
                ? prefix.substring(1, prefix.length() - 1)
                : prefix.replaceFirst("[:：]$", "").trim();
        if (!PLAYER_NAME.matcher(name).matches()) return null;
        return mc.getConnection().getOnlinePlayers().stream().map(p -> p.getProfile().name())
                .filter(n -> n.equalsIgnoreCase(name)).findFirst().orElse(null);
    }

    private static void blockNoticeAndCommand(String name) {
        Minecraft mc = Minecraft.getInstance();
        info(name + " 连续重复刷屏，已本地屏蔽。解除：/mct unblock " + name);
        if (!settings.sendIgnoreCommand || !PLAYER_NAME.matcher(name).matches()
                || !ignoreSent.add(name.toLowerCase(Locale.ROOT)) || mc.getConnection() == null) return;
        if (ignoreQueue.size() < 16) {
            ignoreQueue.addLast(name);
            tickIgnoreQuery();
        } else suggestIgnore(name, "屏蔽命令队列已满，仅本地屏蔽");
    }

    private static boolean commandAvailable(String command) {
        var connection = Minecraft.getInstance().getConnection();
        if (connection == null) return false;
        var parsed = connection.getCommands().parse(command, connection.getSuggestionsProvider());
        return parsed.getExceptions().isEmpty() && !parsed.getReader().canRead();
    }

    private static void tickIgnoreQuery() {
        var connection = Minecraft.getInstance().getConnection();
        if (pendingIgnore != null && System.nanoTime() >= pendingIgnore.deadline()) {
            suggestIgnore(pendingIgnore.name(), "未收到可识别的服务器屏蔽名单，仅本地屏蔽");
            pendingIgnore = null;
            // Without request IDs a late list response must never be reused for another query.
            ignoreQueriesDisabled = true;
        }
        if (pendingIgnore != null || ignoreQueue.isEmpty() || connection == null
                || System.nanoTime() - lastIgnoreCommand < 2_000_000_000L) return;
        String name = ignoreQueue.removeFirst();
        if (!settings.sendIgnoreCommand || !settings.antiSpamEnabled || !spam.blocked(name.toLowerCase(Locale.ROOT))) return;
        lastIgnoreCommand = System.nanoTime();
        var root = connection.getCommands().getRoot().getChild("ignore");
        if (root != null && root.getChild("add") instanceof com.mojang.brigadier.tree.LiteralCommandNode<?>
                && commandAvailable("ignore add " + name)) {
            connection.sendCommand("ignore add " + name);
            info("已发送 /ignore add " + name + "（以服务器回复为准）");
        } else if (!ignoreQueriesDisabled && connection.getCommands().getRoot().getChild("essentials:ignore") != null
                && commandAvailable("essentials:ignore")) {
            pendingIgnore = new PendingIgnore(name, System.nanoTime() + 3_000_000_000L);
            connection.sendCommand("essentials:ignore");
        } else suggestIgnore(name, "未能确认服务器屏蔽命令的状态，仅本地屏蔽");
    }

    private static void acceptIgnoreReply(String serverText) {
        if (pendingIgnore == null || System.nanoTime() >= pendingIgnore.deadline()) return;
        var names = IgnoreCommandPolicy.parseIgnoredList(serverText);
        if (names.isEmpty()) return;
        String name = pendingIgnore.name();
        pendingIgnore = null;
        if (!settings.sendIgnoreCommand || !settings.antiSpamEnabled || !spam.blocked(name.toLowerCase(Locale.ROOT))) return;
        if (names.get().contains(name.toLowerCase(Locale.ROOT))) {
            nextTick.addLast(() -> info(name + " 已在服务器忽略名单中，保持屏蔽"));
            return;
        }
        long epoch = generation;
        var connection = Minecraft.getInstance().getConnection();
        nextTick.addLast(() -> {
            if (generation != epoch || connection == null || connection != Minecraft.getInstance().getConnection()
                    || !settings.sendIgnoreCommand || !spam.blocked(name.toLowerCase(Locale.ROOT))) return;
            String command = "essentials:ignore " + name;
            if (commandAvailable(command)) {
                connection.sendCommand(command);
                info("已发送 /" + command + "（以服务器回复为准）");
            }
        });
    }

    private static void suggestIgnore(String name, String reason) {
        Minecraft.getInstance().gui.hud.getChat().addClientSystemMessage(
                Component.literal("[双语] " + reason + "。点击填入 /ignore " + name)
                    .withStyle(style -> style.withColor(ChatFormatting.GRAY)
                        .withClickEvent(new ClickEvent.SuggestCommand("/ignore " + name))));
    }
    private record PendingIgnore(String name, long deadline) {}

    private static final class ManualMessage {
        final GuiMessage original;
        final String input, prefix, senderKey;
        GuiMessage display;
        String token, translation;
        boolean loading, failed, unchanged, showOriginal = true;
        ManualMessage(GuiMessage original, ChatText parsed, String senderKey) {
            this.original = original; this.display = original;
            this.input = parsed.translationInput().trim(); this.prefix = parsed.prefix(); this.senderKey = senderKey;
        }
    }

    public static void onDisplayedMessage(GuiMessage original) {
        if (!initialized || original.source() == GuiMessageSource.SYSTEM_CLIENT) return;
        Receipt receipt = null;
        for (var it = receipts.iterator(); it.hasNext();) {
            Receipt item = it.next();
            if (original.signature() != null ? original.signature().equals(item.signature())
                    : item.text().equals(original.content().getString())) {
                receipt = item; it.remove(); break;
            }
        }
        if (!settings.enabled) return;
        ChatText parsed = ChatText.parse(original.content().getString());
        String input = parsed.translationInput().trim();
        if (input.isBlank() || input.length() > 4096 || TranslationClient.excludedByPreference(input)) return;
        Minecraft mc = Minecraft.getInstance(); var connection = mc.getConnection();
        if (connection == null) return;
        String senderKey = receipt == null || receipt.name() == null ? null : receipt.name().toLowerCase(Locale.ROOT);
        ManualMessage message = new ManualMessage(original, parsed, senderKey);
        message.token = translationClicks.register(message, connection);
        boolean own = receipt != null && receipt.self();
        nextTick.addLast(() -> {
            if (connection != mc.getConnection() || !settings.enabled
                    || translationClicks.get(message.token, connection) != message) return;
            if (!((ChatHistory) mc.gui.hud.getChat()).mcbilingual$contains(original)) {
                translationClicks.remove(message.token); return;
            }
            if (settings.onDemandTranslation || own && !settings.translateOwnMessages
                    || original.source() == GuiMessageSource.SYSTEM_SERVER && !settings.translateSystemMessages) {
                renderTranslationMessage(message);
            } else requestMessageTranslation(message, true);
        });
    }

    /** Consumed in ChatScreen before vanilla clipboard/command handling. Never sends a chat or command. */
    public static boolean handleTranslationClick(ClickEvent event) {
        if (!(event instanceof ClickEvent.CopyToClipboard copy) || !TranslationClicks.isToken(copy.value())) return false;
        Minecraft mc = Minecraft.getInstance();
        ManualMessage message = translationClicks.get(copy.value(), mc.getConnection());
        if (message == null) { serviceStatus = "这条聊天已过期，请选择当前连接中的消息"; return true; }
        if (settings.enabled) requestMessageTranslation(message, false);
        return true; // Even expired local tokens must not change the clipboard or chat draft.
    }

    private static void requestMessageTranslation(ManualMessage message, boolean automatic) {
        Minecraft mc = Minecraft.getInstance(); var connection = mc.getConnection();
        ChatHistory history = (ChatHistory) mc.gui.hud.getChat();
        if (!settings.enabled || connection == null || !history.mcbilingual$contains(message.display)) return;
        if (message.senderKey != null && settings.antiSpamEnabled && spam.blocked(message.senderKey)) return;
        var claim = translationClicks.claim(message.token, connection);
        if (claim == null) return;
        long epoch = generation;
        message.loading = true; message.failed = false;
        message.showOriginal = !automatic || settings.bilingual;
        if (!automatic) renderTranslationMessage(message);
        serviceStatus = automatic ? "正在自动翻译" : "正在翻译选中的聊天";
        TranslationClient current = translator;
        String source = settings.sourceLanguage, target = settings.targetLanguage;
        CompletableFuture<String> request = automatic ? current.translate(message.input, source, target)
                : helperService.start(helperApp(), System.getProperty("os.name", ""), settings.helperPort,
                        () -> current.health().exceptionally(error -> false).join())
                        .thenCompose(ignored -> current.translate(message.input, source, target));
        request
                .whenComplete((result, error) -> mc.execute(() -> {
                    if (!translationClicks.finish(claim)) return;
                    message.loading = false;
                    if (connection != mc.getConnection() || generation != epoch) return;
                    if (!history.mcbilingual$contains(message.display)) { translationClicks.remove(message.token); return; }
                    if (message.senderKey != null && settings.antiSpamEnabled && spam.blocked(message.senderKey)) return;
                    if (error != null) { message.failed = true; translationError(error); }
                    else {
                        message.translation = result == null || result.isBlank() || result.trim().equalsIgnoreCase(message.input) ? null : result;
                        message.unchanged = message.translation == null;
                        serviceStatus = "本地翻译正常";
                    }
                    renderTranslationMessage(message);
                }));
    }

    private static void renderTranslationMessage(ManualMessage message) {
        Minecraft mc = Minecraft.getInstance();
        if (mc.getConnection() == null || translationClicks.get(message.token, mc.getConnection()) != message) return;
        ChatHistory history = (ChatHistory) mc.gui.hud.getChat();
        if (!history.mcbilingual$contains(message.display)) { translationClicks.remove(message.token); return; }
        var original = message.original.content().copy();
        ClickEvent localClick = new ClickEvent.CopyToClipboard(message.token);
        if (settings.enabled && settings.onDemandTranslation && original.getStyle().getClickEvent() == null)
            original.withStyle(style -> style.withClickEvent(localClick));
        Component body = original;
        if (message.translation != null) {
            Component line = Component.literal("↳ " + (message.showOriginal ? "" : message.prefix) + message.translation)
                    .setStyle(Style.EMPTY.withColor(ChatFormatting.AQUA)
                            .withHoverEvent(new HoverEvent.ShowText(message.original.content())));
            body = message.showOriginal ? Component.empty().append(original).append("\n").append(line) : line;
        }
        if (settings.enabled) {
            String label = message.loading ? " [翻译中]" : message.failed ? " [重试]" : message.unchanged ? " [保留原文]" : message.translation == null ? " [翻译]" : " [重译]";
            Component button = Component.literal(label).setStyle(Style.EMPTY
                    .withColor(message.loading ? ChatFormatting.GRAY : ChatFormatting.DARK_AQUA)
                    .withClickEvent(localClick).withHoverEvent(new HoverEvent.ShowText(Component.literal("点击只翻译这一条；不发送聊天，不改变输入框"))));
            body = Component.empty().append(body).append(button);
        }
        GuiMessage replaced = history.mcbilingual$replaceTracked(message.display, body);
        if (replaced != null) message.display = replaced;
    }

    private static void translationError(Throwable error) {
        while ((error instanceof java.util.concurrent.CompletionException || error instanceof java.util.concurrent.ExecutionException)
                && error.getCause() != null) error = error.getCause();
        String detail;
        if (error instanceof TranslationClient.ServiceFailure failure) {
            detail = switch (failure.code()) {
                case "language_not_installed" -> "本地服务已连接；当前消息缺对应语言包，请在助手中准备";
                case "unsupported_language_pair", "language_check_failed", "language_undetermined" -> "当前消息的语言无法识别或不支持；可在 Kit 中指定原文语言";
                case "queue_full", "translation_timeout" -> "翻译繁忙或超时，请稍后重试";
                default -> "本条翻译失败；可在助手中查看状态";
            };
        } else if (error instanceof java.net.http.HttpTimeoutException) {
            detail = "翻译等待超时，请稍后重试";
        } else {
            detail = "本地助手未连接，请在 Kit 聊天翻译中启动服务";
        }
        serviceStatus = detail;
        long now = System.currentTimeMillis();
        if (now - lastErrorNotice > 60_000) {
            lastErrorNotice = now;
            info(detail + "。原文已保留。");
        }
    }

    private static boolean allowOutgoing(String text) {
        if (sendingTranslated || !settings.enabled || !settings.outgoingTranslation || text.startsWith("/")) return true;
        if (text.codePoints().noneMatch(cp -> Character.UnicodeScript.of(cp) == Character.UnicodeScript.HAN)) return true;
        Minecraft mc = Minecraft.getInstance();
        var connection = mc.getConnection();
        if (connection == null) return true;
        if (outgoingCount >= 8) { info("待翻译发送消息过多，本条未发送。请稍后再试。"); return false; }
        long epoch = generation;
        outgoingCount++;
        var translated = translator.translate(text, "zh-Hans", settings.outgoingTargetLanguage);
        outgoingTail = outgoingTail.handle((v, e) -> null).thenCompose(v -> translated.handle((result, error) -> {
            CompletableFuture<Void> delivered = new CompletableFuture<>();
            mc.execute(() -> {
                try {
                    if (connection != mc.getConnection()) return;
                    if (epoch != generation || !settings.outgoingTranslation) {
                        unsent(text, "设置变化，已取消发送"); return;
                    }
                    if (error != null || result == null || result.isBlank()) { unsent(text, "翻译失败，未发送"); return; }
                    String clean = result.replaceAll("[\\p{Cntrl}§]", " ").strip();
                    if (clean.isBlank() || clean.length() > 256 || clean.startsWith("/")) {
                        unsent(text, "译文为空、超过聊天长度或包含命令前缀，未发送"); return;
                    }
                    sendingTranslated = true;
                    try { connection.sendChat(clean); }
                    finally { sendingTranslated = false; }
                } finally {
                    if (epoch == generation) outgoingCount--;
                    delivered.complete(null);
                }
            });
            return delivered;
        }).thenCompose(v2 -> v2));
        return false;
    }

    private static void unsent(String original, String reason) {
        Minecraft.getInstance().gui.hud.getChat().addClientSystemMessage(Component.literal("[双语] " + reason + "，点击恢复原输入")
                .withStyle(s -> s.withColor(ChatFormatting.YELLOW)
                        .withClickEvent(new ClickEvent.SuggestCommand(original))
                        .withHoverEvent(new HoverEvent.ShowText(Component.literal(original)))));
    }

    private static void preview(String text) {
        long epoch = generation;
        translator.translate(text, "auto", settings.outgoingTargetLanguage).whenComplete((result, error) ->
                Minecraft.getInstance().execute(() -> {
                    if (generation != epoch) return;
                    if (error != null) { translationError(error); return; }
                    Minecraft.getInstance().gui.hud.getChat().addClientSystemMessage(
                            Component.literal("[翻译预览 · 点击填入] " + result)
                                    .withStyle(s -> s.withColor(ChatFormatting.AQUA)
                                            .withClickEvent(new ClickEvent.SuggestCommand(result))));
                }));
    }

    private static void info(String text) {
        Minecraft.getInstance().gui.hud.getChat().addClientSystemMessage(
                Component.literal("[双语] " + text).withStyle(ChatFormatting.GRAY));
    }
    private record Receipt(MessageSignature signature, String text, String name, boolean self) {}
}
