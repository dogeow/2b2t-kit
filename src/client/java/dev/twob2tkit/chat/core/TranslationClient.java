package dev.twob2tkit.chat.core;

import com.google.gson.JsonElement;
import com.google.gson.JsonObject;
import com.google.gson.JsonParser;

import java.io.IOException;
import java.io.ByteArrayOutputStream;
import java.net.Proxy;
import java.net.ProxySelector;
import java.net.SocketAddress;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.net.http.HttpTimeoutException;
import java.nio.ByteBuffer;
import java.nio.charset.StandardCharsets;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.List;
import java.util.Locale;
import java.util.Map;
import java.util.Objects;
import java.util.concurrent.ArrayBlockingQueue;
import java.util.concurrent.CompletableFuture;
import java.util.concurrent.CompletionStage;
import java.util.concurrent.ExecutionException;
import java.util.concurrent.Flow;
import java.util.concurrent.RejectedExecutionException;
import java.util.concurrent.ThreadPoolExecutor;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.TimeoutException;

/** A bounded, non-blocking facade over a strictly loopback-only translation service. */
public final class TranslationClient implements AutoCloseable {
    public static final class ServiceFailure extends IOException {
        private final String code;
        public ServiceFailure(int status, String code) { super("Translation HTTP " + status + " (" + code + ")"); this.code = code; }
        public String code() { return code; }
    }
    private static final java.util.regex.Pattern DEATH_MESSAGE = java.util.regex.Pattern.compile("(?i)(?<![\\p{L}\\p{N}_])died(?![\\p{L}\\p{N}_])");
    public static final int DEFAULT_PORT = 8765;
    public static final int MAX_REQUESTS = 64;
    public static final int CACHE_SIZE = 256;
    private static final Duration REQUEST_TIMEOUT = Duration.ofSeconds(12);
    private static final Duration MAX_REQUEST_AGE = Duration.ofSeconds(20);
    private static final Duration HEALTH_TIMEOUT = Duration.ofSeconds(3);
    private static final int MAX_RESPONSE_BYTES = 64 * 1024;
    private static final ProxySelector DIRECT = new ProxySelector() {
        @Override
        public List<Proxy> select(URI uri) {
            return List.of(Proxy.NO_PROXY);
        }

        @Override
        public void connectFailed(URI uri, SocketAddress address, IOException failure) {
            // There is no proxy to fail over to, and no remote endpoint is ever selected.
        }
    };

    private final URI translateUri;
    private final URI healthUri;
    private final HttpClient http;
    private final ThreadPoolExecutor worker;
    private final Object lock = new Object();
    private final LinkedHashMap<Key, String> cache = new LinkedHashMap<>(32, 0.75f, true);
    private final Map<Key, CompletableFuture<String>> inFlight = new HashMap<>();
    private CompletableFuture<Boolean> healthRequest;
    private CompletableFuture<String> activeTranslation;
    private boolean closed;
    private long cacheGeneration;

    public TranslationClient() {
        this(DEFAULT_PORT);
    }

    /** The host and paths cannot be configured; only a loopback TCP port is accepted. */
    public TranslationClient(int port) {
        if (port < 1 || port > 65535) {
            throw new IllegalArgumentException("Port must be between 1 and 65535");
        }
        translateUri = URI.create("http://127.0.0.1:" + port + "/translate");
        healthUri = URI.create("http://127.0.0.1:" + port + "/health");
        http = HttpClient.newBuilder()
                .connectTimeout(REQUEST_TIMEOUT)
                .followRedirects(HttpClient.Redirect.NEVER)
                .proxy(DIRECT)
                .version(HttpClient.Version.HTTP_1_1)
                .build();
        worker = new ThreadPoolExecutor(1, 1, 0, TimeUnit.MILLISECONDS,
                new ArrayBlockingQueue<>(MAX_REQUESTS - 1), runnable -> {
                    Thread thread = new Thread(runnable, "minecraft-bilingual-http");
                    thread.setDaemon(true);
                    return thread;
                }, new ThreadPoolExecutor.AbortPolicy());
    }

    /**
     * Returns the original text for empty/already-target-language messages.
     * Transport errors, invalid responses, and a full queue complete exceptionally.
     * Cancelling a returned future does not cancel another caller's shared request.
     */
    public CompletableFuture<String> translate(String text, String from, String to) {
        Objects.requireNonNull(text, "text");
        String source = normalizeLanguage(from);
        String target = normalizeLanguage(to);
        synchronized (lock) {
            if (closed) {
                return CompletableFuture.failedFuture(new IllegalStateException("Translation client is closed"));
            }
            if (shouldSkip(text, source, target)) {
                return CompletableFuture.completedFuture(text);
            }
            Key key = new Key(text, source, target);
            String cached = cache.get(key);
            if (cached != null) {
                return CompletableFuture.completedFuture(cached);
            }
            CompletableFuture<String> existing = inFlight.get(key);
            if (existing != null) {
                return existing.copy();
            }
            CompletableFuture<String> result = new CompletableFuture<>();
            inFlight.put(key, result);
            long generation = cacheGeneration;
            try {
                long deadline = System.nanoTime() + MAX_REQUEST_AGE.toNanos();
                worker.execute(() -> translateNow(key, result, generation, deadline));
            } catch (RejectedExecutionException full) {
                inFlight.remove(key);
                result.completeExceptionally(new RejectedExecutionException("Translation queue is full", full));
            }
            return result.copy();
        }
    }

    /** An independent, deduplicated 3-second probe, unaffected by the translation queue. */
    public CompletableFuture<Boolean> health() {
        synchronized (lock) {
            if (closed) {
                return CompletableFuture.failedFuture(new IllegalStateException("Translation client is closed"));
            }
            if (healthRequest != null) {
                return healthRequest.copy();
            }
            CompletableFuture<Boolean> result = new CompletableFuture<>();
            healthRequest = result;
            try {
                HttpRequest request = HttpRequest.newBuilder(healthUri).timeout(HEALTH_TIMEOUT).GET().build();
                CompletableFuture<HttpResponse<String>> exchange = http.sendAsync(request, limitedBodyHandler());
                exchange.copy().orTimeout(HEALTH_TIMEOUT.toMillis(), TimeUnit.MILLISECONDS).whenComplete((response, failure) -> {
                    synchronized (lock) {
                        if (healthRequest == result) {
                            healthRequest = null;
                        }
                    }
                    if (failure == null) {
                        result.complete(response.statusCode() >= 200 && response.statusCode() < 300);
                    } else {
                        exchange.cancel(true);
                        result.completeExceptionally(failure);
                    }
                });
            } catch (Exception failure) {
                healthRequest = null;
                result.completeExceptionally(failure);
            }
            return result.copy();
        }
    }

    public void clearCache() {
        List<CompletableFuture<String>> superseded = new ArrayList<>();
        synchronized (lock) {
            cache.clear();
            cacheGeneration++;
            worker.getQueue().clear();
            inFlight.entrySet().removeIf(entry -> {
                if (entry.getValue() != activeTranslation) {
                    superseded.add(entry.getValue());
                    return true;
                }
                return false;
            });
        }
        superseded.forEach(future -> future.completeExceptionally(
                new IllegalStateException("Translation request was superseded by cache reset")));
    }

    @Override
    public void close() {
        List<CompletableFuture<?>> pending;
        synchronized (lock) {
            if (closed) {
                return;
            }
            closed = true;
            cache.clear();
            pending = new ArrayList<>(inFlight.values());
            if (healthRequest != null) {
                pending.add(healthRequest);
            }
            inFlight.clear();
            healthRequest = null;
        }
        worker.shutdownNow();
        http.shutdownNow();
        IllegalStateException failure = new IllegalStateException("Translation client is closed");
        pending.forEach(future -> future.completeExceptionally(failure));
    }

    private void translateNow(Key key, CompletableFuture<String> result, long generation, long deadline) {
        synchronized (lock) {
            if (closed || generation != cacheGeneration) {
                inFlight.remove(key, result);
                result.completeExceptionally(new IllegalStateException("Translation request was superseded"));
                return;
            }
            activeTranslation = result;
        }
        String translated = null;
        Exception failure = null;
        CompletableFuture<HttpResponse<String>> exchange = null;
        try {
            long remaining = deadline - System.nanoTime();
            if (remaining <= 0) {
                throw new HttpTimeoutException("Translation request expired while queued");
            }
            Duration timeout = Duration.ofNanos(Math.min(remaining, REQUEST_TIMEOUT.toNanos()));
            JsonObject payload = new JsonObject();
            payload.addProperty("text", key.text());
            payload.addProperty("from", key.from());
            payload.addProperty("to", key.to());
            HttpRequest request = HttpRequest.newBuilder(translateUri)
                    .timeout(timeout)
                    .header("Content-Type", "application/json; charset=utf-8")
                    .header("Accept", "application/json")
                    .POST(HttpRequest.BodyPublishers.ofString(payload.toString(), StandardCharsets.UTF_8))
                    .build();
            exchange = http.sendAsync(request, limitedBodyHandler());
            HttpResponse<String> response = exchange.get(timeout.toNanos(), TimeUnit.NANOSECONDS);
            if (response.statusCode() < 200 || response.statusCode() >= 300) {
                String code = "http_error";
                try {
                    JsonElement body = JsonParser.parseString(response.body());
                    JsonElement value = body.isJsonObject() ? body.getAsJsonObject().get("error") : null;
                    if (value != null && value.isJsonPrimitive() && value.getAsJsonPrimitive().isString()
                            && value.getAsString().matches("[a-z_]{1,48}")) code = value.getAsString();
                } catch (RuntimeException ignored) { /* Keep the HTTP failure; never display an arbitrary body. */ }
                throw new ServiceFailure(response.statusCode(), code);
            }
            JsonElement document = JsonParser.parseString(response.body());
            JsonElement value = document.isJsonObject() ? document.getAsJsonObject().get("translation") : null;
            if (value == null || !value.isJsonPrimitive() || !value.getAsJsonPrimitive().isString()
                    || value.getAsString().isBlank()) {
                throw new IOException("Translation service returned an invalid translation");
            }
            translated = value.getAsString();
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            failure = interrupted;
        } catch (TimeoutException timeout) {
            failure = new HttpTimeoutException("Translation request timed out");
        } catch (ExecutionException exception) {
            failure = exception.getCause() instanceof Exception cause ? cause : exception;
        } catch (Exception exception) {
            failure = exception;
        } finally {
            if (exchange != null && !exchange.isDone()) {
                exchange.cancel(true);
            }
        }
        synchronized (lock) {
            if (activeTranslation == result) {
                activeTranslation = null;
            }
            inFlight.remove(key, result);
            if (!closed && failure == null && generation == cacheGeneration) {
                cache.put(key, translated);
                if (cache.size() > CACHE_SIZE) {
                    cache.remove(cache.keySet().iterator().next());
                }
            }
        }
        if (failure == null) {
            result.complete(translated);
        } else {
            result.completeExceptionally(failure);
        }
    }

    private static String normalizeLanguage(String language) {
        String normalized = Objects.requireNonNull(language, "language").strip().toLowerCase(Locale.ROOT);
        if (normalized.isEmpty()) {
            throw new IllegalArgumentException("Language cannot be empty");
        }
        return normalized;
    }

    private static boolean shouldSkip(String text, String source, String target) {
        String plain = ChatText.stripFormatting(text);
        if (DEATH_MESSAGE.matcher(plain).find()) return true;
        if (plain.isBlank() || source.equals(target)) {
            return true;
        }
        boolean han = false;
        boolean latin = false;
        boolean japaneseOrKorean = false;
        boolean otherLetter = false;
        for (int offset = 0; offset < plain.length();) {
            int codePoint = plain.codePointAt(offset);
            offset += Character.charCount(codePoint);
            Character.UnicodeScript script = Character.UnicodeScript.of(codePoint);
            switch (script) {
                case HAN -> han = true;
                case LATIN -> latin = true;
                case HIRAGANA, KATAKANA, HANGUL -> japaneseOrKorean = true;
                default -> {
                    if (Character.isLetter(codePoint)) {
                        otherLetter = true;
                    }
                }
            }
        }
        if (!han && !latin && !japaneseOrKorean && !otherLetter) {
            return true;
        }
        String baseTarget = target.split("[-_]", 2)[0];
        return switch (baseTarget) {
            // Han mixed with Cyrillic/Arabic/etc. still needs translation.
            case "zh" -> source.equals("auto") && han && !latin && !japaneseOrKorean && !otherLetter;
            // Latin, Cyrillic, and Arabic scripts cannot establish that text is English.
            // Leave auto-detection to the helper instead of silently skipping other languages.
            default -> false;
        };
    }

    public static boolean excludedByPreference(String text) { return DEATH_MESSAGE.matcher(ChatText.stripFormatting(text)).find(); }

    private record Key(String text, String from, String to) { }

    private static HttpResponse.BodyHandler<String> limitedBodyHandler() {
        return responseInfo -> new LimitedBodySubscriber();
    }

    /** Rejects oversized UTF-8 responses before allocating an unbounded JSON document. */
    private static final class LimitedBodySubscriber implements HttpResponse.BodySubscriber<String> {
        private final CompletableFuture<String> body = new CompletableFuture<>();
        private final ByteArrayOutputStream bytes = new ByteArrayOutputStream();
        private Flow.Subscription subscription;

        @Override
        public CompletionStage<String> getBody() {
            return body;
        }

        @Override
        public void onSubscribe(Flow.Subscription subscription) {
            this.subscription = subscription;
            subscription.request(1);
        }

        @Override
        public void onNext(List<ByteBuffer> buffers) {
            for (ByteBuffer buffer : buffers) {
                int count = buffer.remaining();
                if (count > MAX_RESPONSE_BYTES - bytes.size()) {
                    subscription.cancel();
                    body.completeExceptionally(new IOException("Translation service response exceeds 64 KiB"));
                    return;
                }
                byte[] chunk = new byte[count];
                buffer.get(chunk);
                bytes.writeBytes(chunk);
            }
            subscription.request(1);
        }

        @Override
        public void onError(Throwable failure) {
            body.completeExceptionally(failure);
        }

        @Override
        public void onComplete() {
            body.complete(bytes.toString(StandardCharsets.UTF_8));
        }
    }
}
