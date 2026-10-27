package dev.twob2tkit;

import java.util.ArrayList;
import java.util.List;

import dev.twob2tkit.chat.BilingualClient;
import dev.twob2tkit.chat.ModConfig;
import net.minecraft.client.Minecraft;
import net.minecraft.client.gui.screens.Screen;

/** Translation preferences embedded in Kit's existing native settings UI. */
public final class ChatTranslationPage {
    private ChatTranslationPage() {}

    public static void open(Screen parent) {
        ModConfig config = BilingualClient.config();
        KitFormScreen page = new KitFormScreen(parent, "聊天翻译与防刷屏",
                "默认原文 + 译文；开关即时保存，数值点“应用数值”后生效。")
                .bind(KitClient.config()).id("chat-translation")
                .footerHint("开关与语言即时保存 · 数值应用后生效")
                .status(BilingualClient::status);
        page.submit("应用数值", () -> {
            BilingualClient.saveSettings();
            page.message("翻译设置已应用", 0x77DDCC);
        });

        page.section("收到消息 · 默认双语");
        page.bool("聊天翻译", "开启聊天翻译；翻译不可用时保留原文。", () -> config.enabled,
                value -> { config.enabled = value; BilingualClient.saveSettings(); if (value) BilingualClient.startHelper(); });
        page.bool("按需翻译", "开启后不自动调用翻译，点击聊天文字或 [翻译] 只处理这一条；原有链接照常可点。",
                () -> config.onDemandTranslation,
                value -> { config.onDemandTranslation = value; BilingualClient.saveSettings(); });
        page.bool("原文 + 译文", "默认开启双语；关闭后只显示译文。失败时保留原文。", () -> config.bilingual,
                value -> { config.bilingual = value; BilingualClient.saveSettings(); });
        Languages target = Languages.forCurrent(config.targetLanguage, false);
        page.cycle("译成语言", "收到的消息翻译为此语言。", target.labels(),
                () -> target.indexOf(config.targetLanguage),
                value -> { config.targetLanguage = target.codes()[value]; BilingualClient.saveSettings(); });
        Languages source = Languages.forCurrent(config.sourceLanguage, true);
        page.cycle("原文语言", "默认自动检测；已知原文语言时可手动指定。", source.labels(),
                () -> source.indexOf(config.sourceLanguage),
                value -> { config.sourceLanguage = source.codes()[value]; BilingualClient.saveSettings(); });
        page.bool("服务器与插件消息", "翻译服务器通知及插件聊天消息；不翻译快捷栏提示。",
                () -> config.translateSystemMessages,
                value -> { config.translateSystemMessages = value; BilingualClient.saveSettings(); });
        page.bool("自己的聊天消息", "翻译服务器返回的本人消息；默认关闭，避免重复翻译。",
                () -> config.translateOwnMessages,
                value -> { config.translateOwnMessages = value; BilingualClient.saveSettings(); });

        page.section("发送消息 · 默认关闭");
        page.bool("翻译后发送", "开启后，普通聊天先翻译再发给服务器；命令不翻译。",
                () -> config.outgoingTranslation,
                value -> { config.outgoingTranslation = value; BilingualClient.saveSettings(); });
        Languages outgoing = Languages.forCurrent(config.outgoingTargetLanguage, false);
        page.cycle("发送目标语言", "仅在“翻译后发送”开启时使用。", outgoing.labels(),
                () -> outgoing.indexOf(config.outgoingTargetLanguage),
                value -> { config.outgoingTargetLanguage = outgoing.codes()[value]; BilingualClient.saveSettings(); });
        page.liveLine(() -> config.outgoingTranslation
                ? "发送翻译已开启：翻译结果将作为聊天发给服务器。"
                : "发送翻译未开启：输入内容照常发送。");

        page.section("重复刷屏过滤");
        page.bool("过滤重复刷屏", "按玩家、重复内容和时间窗口识别刷屏。",
                () -> config.antiSpamEnabled,
                value -> { config.antiSpamEnabled = value; BilingualClient.saveSettings(); });
        page.slider("重复次数阈值", "同一玩家在时间窗口内重复达到此次数后处理；默认 3 次。", 2, 100,
                () -> config.spamRepeatThreshold, value -> config.spamRepeatThreshold = value);
        page.slider("统计窗口（秒）", "统计重复消息的时间窗口；默认 15 秒。", 1, 3600,
                () -> config.spamWindowSeconds, value -> config.spamWindowSeconds = value);
        page.bool("自动发送 /ignore", "仅在服务器明确支持 /ignore 且玩家名有效时发送；否则只在本地屏蔽。",
                () -> config.sendIgnoreCommand,
                value -> { config.sendIgnoreCommand = value; BilingualClient.saveSettings(); });
        page.action("清空本地屏蔽记录", "恢复本地显示；不改变服务器上的忽略名单。", () -> {
            BilingualClient.unblockAll();
            page.message("本地屏蔽记录已清空；服务器忽略名单需手动恢复", 0x77DDCC);
        });
        page.note("清空只影响本地屏蔽。已经发送的服务器忽略需要手动输入 /ignore 玩家名，按服务器说明恢复。");

        page.section("本地翻译服务");
        page.action("启动翻译服务", "直接启动本机助手；已连接时复用服务，不重复启动。", BilingualClient::startHelper);
        page.action("打开助手 / 准备语言包", "在助手中完成 Apple 语言包下载与系统确认。", BilingualClient::openHelper);
        page.liveNote(() -> "服务状态：" + BilingualClient.status());
        page.liveLine(() -> "连接地址：127.0.0.1:" + config.helperPort);
        page.slider("助手端口", "与本地翻译助手使用相同端口；默认 8765。", 1, 65535,
                () -> config.helperPort, value -> config.helperPort = value);
        page.action("应用数值并检测连接", "保存本页数值，再检测翻译助手和模型是否可用。", () -> {
            if (page.finishEdits()) BilingualClient.checkHealth();
        });

        if (parent instanceof ClickGuiScreen gui) {
            gui.showDetail(page);
        } else {
            Minecraft.getInstance().gui.setScreen(page);
        }
    }

    /** Preserve a manually configured language tag instead of displaying the wrong language. */
    private record Languages(String[] labels, String[] codes) {
        static Languages forCurrent(String current, boolean includeAuto) {
            List<String> labels = new ArrayList<>();
            List<String> codes = new ArrayList<>();
            if (includeAuto) { labels.add("自动检测"); codes.add("auto"); }
            labels.addAll(List.of("简体中文", "繁體中文", "英语", "日语", "韩语"));
            codes.addAll(List.of("zh-Hans", "zh-Hant", "en", "ja", "ko"));
            if (current != null && !current.isBlank() && !codes.contains(current)) {
                labels.add("自定义：" + current);
                codes.add(current);
            }
            return new Languages(labels.toArray(String[]::new), codes.toArray(String[]::new));
        }

        int indexOf(String code) {
            for (int index = 0; index < codes.length; index++) {
                if (codes[index].equals(code)) return index;
            }
            return 0;
        }
    }
}
