package dev.twob2tkit.chat.core;

import com.google.gson.JsonObject;
import com.google.gson.JsonParser;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import java.io.IOException;
import java.net.InetSocketAddress;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.net.http.HttpTimeoutException;
import java.nio.charset.StandardCharsets;
import java.util.ArrayList;
import java.util.List;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CountDownLatch;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.concurrent.atomic.AtomicReference;

import static org.junit.jupiter.api.Assertions.*;

class TranslationClientTest {
    private HttpServer server;
    private ExecutorService serverWorkers;
    private TranslationClient client;
    private final AtomicInteger requests = new AtomicInteger();
    private final AtomicReference<JsonObject> received = new AtomicReference<>();
    private final AtomicReference<Reply> reply = new AtomicReference<>(new Reply(200, "{\"translation\":\"你好\"}"));
    private final AtomicReference<CountDownLatch> pause = new AtomicReference<>();
    private final CountDownLatch entered = new CountDownLatch(1);

    @BeforeEach
    void startServer() throws IOException {
        server = HttpServer.create(new InetSocketAddress("127.0.0.1", 0), 0);
        serverWorkers = Executors.newCachedThreadPool();
        server.setExecutor(serverWorkers);
        server.createContext("/translate", exchange -> {
            requests.incrementAndGet();
            received.set(JsonParser.parseString(new String(exchange.getRequestBody().readAllBytes(),
                    StandardCharsets.UTF_8)).getAsJsonObject());
            entered.countDown();
            CountDownLatch gate = pause.get();
            if (gate != null) {
                try {
                    gate.await(30, TimeUnit.SECONDS);
                } catch (InterruptedException interrupted) {
                    Thread.currentThread().interrupt();
                }
            }
            send(exchange, reply.get());
        });
        server.createContext("/health", exchange -> send(exchange, reply.get()));
        server.start();
        client = new TranslationClient(server.getAddress().getPort());
    }

    @AfterEach
    void stopServer() {
        if (client != null) {
            client.close();
        }
        CountDownLatch gate = pause.get();
        if (gate != null) {
            gate.countDown();
        }
        if (server != null) {
            server.stop(0);
        }
        if (serverWorkers != null) {
            serverWorkers.shutdownNow();
        }
    }

    @Test
    void sendsJsonAndCachesByTextAndLanguagePair() throws Exception {
        String text = "你好 \"world\"\nline two";
        assertEquals("你好", client.translate(text, "AUTO", "zh-CN").get(3, TimeUnit.SECONDS));
        assertEquals(text, received.get().get("text").getAsString());
        assertEquals("auto", received.get().get("from").getAsString());
        assertEquals("zh-cn", received.get().get("to").getAsString());
        assertEquals("你好", client.translate(text, "auto", "zh-cn").get(3, TimeUnit.SECONDS));
        assertEquals(1, requests.get());
        client.translate(text, "en", "zh-cn").get(3, TimeUnit.SECONDS);
        client.translate(text, "auto", "en").get(3, TimeUnit.SECONDS);
        assertEquals(3, requests.get(), "Neither source nor target language may leak across cached translations");
        client.clearCache();
        client.translate(text, "auto", "en").get(3, TimeUnit.SECONDS);
        assertEquals(4, requests.get());
    }

    @Test
    void sharesInFlightWorkWithoutSharingCallerCancellation() throws Exception {
        CountDownLatch gate = new CountDownLatch(1);
        pause.set(gate);
        CompletableFuture<String> first = client.translate("hello", "auto", "zh");
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        CompletableFuture<String> second = client.translate("hello", "auto", "zh");
        first.cancel(true);
        gate.countDown();
        assertEquals("你好", second.get(3, TimeUnit.SECONDS));
        assertEquals(1, requests.get());
    }

    @Test
    void limitsPendingWorkAndStillAllowsDuplicateSubscribersAtCapacity() throws Exception {
        CountDownLatch gate = new CountDownLatch(1);
        pause.set(gate);
        List<CompletableFuture<String>> accepted = new ArrayList<>();
        accepted.add(client.translate("message 0", "auto", "zh"));
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        for (int i = 1; i < 64; i++) {
            accepted.add(client.translate("message " + i, "auto", "zh"));
        }
        CompletableFuture<String> overflow = client.translate("overflow", "auto", "zh");
        assertInstanceOf(RejectedExecutionException.class, failureOf(overflow));
        CompletableFuture<String> duplicate = client.translate("message 0", "auto", "zh");
        assertEquals(1, requests.get(), "Queued requests must not run concurrently");
        gate.countDown();
        CompletableFuture.allOf(accepted.toArray(CompletableFuture[]::new)).get(10, TimeUnit.SECONDS);
        assertEquals("你好", duplicate.get(3, TimeUnit.SECONDS));
        assertEquals(64, requests.get());
        assertEquals("你好", client.translate("overflow", "auto", "zh").get(3, TimeUnit.SECONDS));
    }

    @Test
    void failuresAreVisibleAndRetriedInsteadOfCached() throws Exception {
        for (Reply invalid : List.of(new Reply(503, "unavailable"), new Reply(200, "not json"),
                new Reply(200, "{\"translation\":17}"), new Reply(200, "{\"translation\":null}"),
                new Reply(200, "{\"translation\":\"  \"}"), new Reply(200, "{}"))) {
            reply.set(invalid);
            assertNotNull(failureOf(client.translate("retry me", "auto", "zh")));
        }
        reply.set(new Reply(200, "{\"translation\":\"重试成功\"}"));
        assertEquals("重试成功", client.translate("retry me", "auto", "zh").get(3, TimeUnit.SECONDS));
        assertEquals(7, requests.get());
    }

    @Test
    void skipsOnlyKnownTargetLanguageCases() throws Exception {
        for (String text : List.of("你好，世界！123", "§a中文§r", "", "  ", "123 ! 🐱")) {
            assertEquals(text, client.translate(text, "auto", "zh").get(3, TimeUnit.SECONDS));
        }
        for (String text : List.of("Hello world", "Just English 123")) {
            assertEquals(text, client.translate(text, "en", "en").get(3, TimeUnit.SECONDS));
        }
        assertEquals(0, requests.get());
        for (String text : List.of("中文 English", "日本語です", "한국어", "中文 Привет", "Привет")) {
            client.translate(text, "auto", "zh").get(3, TimeUnit.SECONDS);
        }
        client.translate("中文", "auto", "en").get(3, TimeUnit.SECONDS);
        client.translate("ひらがな", "auto", "en").get(3, TimeUnit.SECONDS);
        assertEquals(7, requests.get(), "Mixed non-Latin text must not be mistaken for pure Chinese");
    }

    @Test
    void deathMessagesNeverNeedHelperButPlayerNameSubstringsStillTranslate() throws Exception {
        for (String text : List.of("Steve died", "BBblock225 died to polar bear", "Steve DIED.", "[died]"))
            assertEquals(text, client.translate(text, "auto", "zh-Hans").get(3, TimeUnit.SECONDS));
        assertEquals(0, requests.get());
        client.translate("Diedrich found a village", "auto", "zh-Hans").get(3, TimeUnit.SECONDS);
        assertEquals(1, requests.get());
    }

    @Test
    void autoToEnglishDoesNotMistakeOtherScriptsOrLatinLanguagesForEnglish() throws Exception {
        for (String text : List.of("Привет мир", "Hola mundo", "مرحبا بالعالم", "Hello world")) {
            assertEquals("你好", client.translate(text, "auto", "en").get(3, TimeUnit.SECONDS));
        }
        assertEquals(4, requests.get());
        client.translate("Hello world", "en-US", "en-GB").get(3, TimeUnit.SECONDS);
        assertEquals(5, requests.get(), "An explicit different language tag must not be silently collapsed");
        client.translate("汉语", "zh-Hans", "zh-Hant").get(3, TimeUnit.SECONDS);
        assertEquals(6, requests.get(), "Explicit Chinese script conversion must reach the helper");
    }

    @Test
    void evictsLeastRecentlyUsedTranslations() throws Exception {
        for (int i = 0; i < 256; i++) {
            client.translate("message " + i, "auto", "zh").get(3, TimeUnit.SECONDS);
        }
        client.translate("message 0", "auto", "zh").get(3, TimeUnit.SECONDS);
        client.translate("message 256", "auto", "zh").get(3, TimeUnit.SECONDS);
        client.translate("message 0", "auto", "zh").get(3, TimeUnit.SECONDS);
        assertEquals(257, requests.get(), "Recently read entries should survive eviction");
        client.translate("message 1", "auto", "zh").get(3, TimeUnit.SECONDS);
        assertEquals(258, requests.get());
    }

    @Test
    void clearingCacheDoesNotRepopulateItFromOldPendingRequests() throws Exception {
        CountDownLatch gate = new CountDownLatch(1);
        pause.set(gate);
        CompletableFuture<String> pending = client.translate("hello", "auto", "zh");
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        client.clearCache();
        gate.countDown();
        pending.get(3, TimeUnit.SECONDS);
        client.translate("hello", "auto", "zh").get(3, TimeUnit.SECONDS);
        assertEquals(2, requests.get());
    }

    @Test
    void reportsHealthAndRejectsRedirectsWithoutFollowingThem() throws Exception {
        assertTrue(client.health().get(3, TimeUnit.SECONDS));
        reply.set(new Reply(503, "unavailable"));
        assertFalse(client.health().get(3, TimeUnit.SECONDS));
        AtomicInteger redirectedRequests = new AtomicInteger();
        server.createContext("/unexpected", exchange -> {
            redirectedRequests.incrementAndGet();
            send(exchange, new Reply(200, "{\"translation\":\"unexpected\"}"));
        });
        reply.set(new Reply(302, "redirect"));
        assertInstanceOf(IOException.class, failureOf(client.translate("hello", "auto", "zh")));
        assertFalse(client.health().get(3, TimeUnit.SECONDS));
        assertEquals(0, redirectedRequests.get());
    }

    @Test
    void languagePackFailureRetainsMachineCodeWithoutExposingResponseBody() {
        reply.set(new Reply(503, "{\"error\":\"language_not_installed\",\"message\":\"private response text\"}"));
        var error = assertInstanceOf(TranslationClient.ServiceFailure.class, failureOf(client.translate("hello", "auto", "zh")));
        assertEquals("language_not_installed", error.code());
        assertFalse(error.getMessage().contains("private response text"));
    }

    @Test
    void healthDoesNotWaitBehindTranslationRequests() throws Exception {
        pause.set(new CountDownLatch(1));
        client.translate("waiting", "auto", "zh");
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        assertTrue(client.health().get(2, TimeUnit.SECONDS));
    }

    @Test
    void rejectsOversizedResponsesAndRecovers() throws Exception {
        reply.set(new Reply(200, "{\"translation\":\"" + "中".repeat(24_000) + "\"}"));
        assertInstanceOf(IOException.class, failureOf(client.translate("hello", "auto", "zh")));
        reply.set(new Reply(200, "{\"translation\":\"你好\"}"));
        assertEquals("你好", client.translate("hello", "auto", "zh").get(3, TimeUnit.SECONDS));
    }

    @Test
    void clearingCacheSupersedesQueuedWork() throws Exception {
        CountDownLatch gate = new CountDownLatch(1);
        pause.set(gate);
        CompletableFuture<String> active = client.translate("active", "auto", "zh");
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        CompletableFuture<String> queued = client.translate("queued", "auto", "zh");
        client.clearCache();
        assertInstanceOf(IllegalStateException.class, failureOf(queued));
        gate.countDown();
        assertEquals("你好", active.get(3, TimeUnit.SECONDS));
        assertEquals(1, requests.get());
    }

    @Test
    void bypassesTheSystemProxySelector() throws Exception {
        ProxySelector original = ProxySelector.getDefault();
        AtomicInteger proxyLookups = new AtomicInteger();
        try {
            ProxySelector.setDefault(new ProxySelector() {
                @Override public List<Proxy> select(URI uri) {
                    proxyLookups.incrementAndGet();
                    return List.of(new Proxy(Proxy.Type.HTTP, new InetSocketAddress("127.0.0.1", 1)));
                }
                @Override public void connectFailed(URI uri, SocketAddress address, IOException error) { }
            });
            client.close();
            client = new TranslationClient(server.getAddress().getPort());
            assertEquals("你好", client.translate("hello", "auto", "zh").get(3, TimeUnit.SECONDS));
            assertEquals(0, proxyLookups.get());
        } finally {
            ProxySelector.setDefault(original);
        }
    }

    @Test
    void timesOutAnUnresponsiveServiceAndExpiresQueuedMessages() throws Exception {
        pause.set(new CountDownLatch(1));
        CompletableFuture<String> pending = client.translate("please respond", "auto", "zh");
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        CompletableFuture<String> second = client.translate("second", "auto", "zh");
        CompletableFuture<String> third = client.translate("third", "auto", "zh");
        ExecutionException failure = assertThrows(ExecutionException.class, () -> pending.get(15, TimeUnit.SECONDS));
        assertInstanceOf(HttpTimeoutException.class, failure.getCause());
        ExecutionException secondFailure = assertThrows(ExecutionException.class, () -> second.get(10, TimeUnit.SECONDS));
        assertInstanceOf(HttpTimeoutException.class, secondFailure.getCause());
        assertInstanceOf(HttpTimeoutException.class, failureOf(third));
        assertEquals(2, requests.get(), "Old queued messages must expire before starting another HTTP request");
    }

    @Test
    void closingSettlesActiveQueuedAndFutureCalls() throws Exception {
        pause.set(new CountDownLatch(1));
        CompletableFuture<String> active = client.translate("active", "auto", "zh");
        assertTrue(entered.await(3, TimeUnit.SECONDS));
        CompletableFuture<String> queued = client.translate("queued", "auto", "zh");
        client.close();
        assertNotNull(failureOf(active));
        assertNotNull(failureOf(queued));
        assertInstanceOf(IllegalStateException.class, failureOf(client.translate("new", "auto", "zh")));
        assertInstanceOf(IllegalStateException.class, failureOf(client.health()));
        client.close();
    }

    private static Throwable failureOf(CompletableFuture<?> future) {
        return assertThrows(ExecutionException.class, () -> future.get(3, TimeUnit.SECONDS)).getCause();
    }

    private static void send(HttpExchange exchange, Reply response) throws IOException {
        byte[] bytes = response.body().getBytes(StandardCharsets.UTF_8);
        exchange.getResponseHeaders().set("Content-Type", "application/json; charset=utf-8");
        exchange.getResponseHeaders().set("Connection", "close");
        if (response.status() == 302) {
            exchange.getResponseHeaders().set("Location", "/unexpected");
        }
        exchange.sendResponseHeaders(response.status(), bytes.length);
        try (var body = exchange.getResponseBody()) {
            body.write(bytes);
        }
    }

    private record Reply(int status, String body) { }
}
