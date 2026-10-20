package com.matrix.prp.ai;

import com.matrix.prp.auth.security.CurrentUser;
import java.net.http.HttpTimeoutException;
import java.time.Clock;
import java.time.LocalDateTime;
import java.util.List;
import java.util.Objects;
import java.util.concurrent.TimeUnit;
import java.util.concurrent.atomic.AtomicLong;
import java.util.function.Consumer;
import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.context.annotation.Primary;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

/** Records safe model-invocation metadata. Telemetry failures never affect user requests. */
@Component
@Primary
public class ObservedAiModelGateway implements AiModelGateway {
    private static final Logger LOG = LoggerFactory.getLogger(ObservedAiModelGateway.class);
    private final DefaultAiModelGateway delegate;
    private final AiInvocationAudit audit;

    public ObservedAiModelGateway(DefaultAiModelGateway delegate, AiInvocationAudit audit) {
        this.delegate = delegate; this.audit = audit;
    }

    @Override public String legacyModel() { return delegate.legacyModel(); }
    @Override public void requireLegacyConfigured() { delegate.requireLegacyConfigured(); }

    @Override public DeepSeekClient.Result stream(Target target, List<DeepSeekClient.ChatMessage> messages,
                                                  int outputLimit, Consumer<String> delta) throws Exception {
        Objects.requireNonNull(target, "AI model target is required");
        long started = System.nanoTime();
        AtomicLong first = new AtomicLong(-1L);
        boolean legacy = target.useLegacyDeepSeek();
        String provider = legacy ? "deepseek" : target.provider().provider().id();
        String model = legacy ? legacyModel() : target.provider().model();
        String source = legacy ? "SERVER" : target.provider().legacy() ? "SERVER" : "PERSONAL";
        try {
            DeepSeekClient.Result result = delegate.stream(target, messages, outputLimit, part -> {
                if (part != null && !part.isEmpty())
                    first.compareAndSet(-1L, Math.max(0, System.nanoTime() - started));
                delta.accept(part);
            });
            // Providers that omit usage report zeros in the pre-existing adapter.
            // Unknown consumption must never be presented as zero or a priced estimate.
            boolean reported = result.inputTokens() > 0 || result.outputTokens() > 0;
            safeRecord(provider,model,source,"SUCCESS",null,started,first.get(),
                reported ? result.inputTokens() : null,
                reported ? result.outputTokens() : null);
            return result;
        } catch (Exception error) {
            safeRecord(provider,model,source,"FAILURE",category(error),started,first.get(),null,null);
            throw error;
        }
    }

    static String category(Exception error) {
        if (error instanceof HttpTimeoutException || error instanceof java.net.SocketTimeoutException)
            return "TIMEOUT";
        if (error instanceof InterruptedException) return "INTERRUPTED";
        if (error instanceof ResponseStatusException http) {
            if (http.getStatusCode().value()==429) return "PROVIDER_RATE_LIMIT";
            if (http.getStatusCode().value()==503) return "PROVIDER_UNAVAILABLE";
            return "PROVIDER_HTTP_ERROR";
        }
        if (error instanceof IllegalStateException) return "INCOMPLETE_RESPONSE";
        return "MODEL_CALL_FAILED";
    }

    private void safeRecord(String provider,String model,String source,String status,String failure,
                            long started,long firstNanos,Long input,Long output) {
        try {
            long userId = CurrentUser.id();
            audit.record(new AiInvocationAudit.Entry(userId,provider,model,source,status,failure,
                Math.max(0,TimeUnit.NANOSECONDS.toMillis(System.nanoTime()-started)),
                firstNanos<0?null:TimeUnit.NANOSECONDS.toMillis(firstNanos),
                input,output,LocalDateTime.now(Clock.systemUTC())));
        } catch (RuntimeException error) {
            // Never emit prompts, credentials, output, stack traces or even provider error bodies.
            LOG.warn("AI invocation metadata could not be recorded");
        }
    }
}
