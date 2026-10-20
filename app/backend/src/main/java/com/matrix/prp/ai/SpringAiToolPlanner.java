package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.time.Duration;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Map;
import java.util.Objects;
import java.util.Set;
import org.springframework.ai.anthropic.AnthropicChatModel;
import org.springframework.ai.anthropic.AnthropicChatOptions;
import org.springframework.ai.anthropic.api.AnthropicApi;
import org.springframework.ai.chat.messages.AssistantMessage;
import org.springframework.ai.chat.messages.Message;
import org.springframework.ai.chat.messages.SystemMessage;
import org.springframework.ai.chat.messages.UserMessage;
import org.springframework.ai.chat.model.ChatModel;
import org.springframework.ai.chat.prompt.Prompt;
import org.springframework.ai.deepseek.DeepSeekChatModel;
import org.springframework.ai.deepseek.DeepSeekChatOptions;
import org.springframework.ai.deepseek.api.DeepSeekApi;
import org.springframework.ai.openai.OpenAiChatModel;
import org.springframework.ai.openai.OpenAiChatOptions;
import org.springframework.ai.openai.api.OpenAiApi;
import org.springframework.ai.tool.ToolCallback;
import org.springframework.ai.tool.definition.ToolDefinition;
import org.springframework.http.HttpStatus;
import org.springframework.http.HttpStatusCode;
import org.springframework.retry.policy.NeverRetryPolicy;
import org.springframework.retry.support.RetryTemplate;
import org.springframework.stereotype.Component;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.web.client.RestClient;
import org.springframework.web.client.RestClientResponseException;
import org.springframework.web.server.ResponseStatusException;

/**
 * A single Spring AI function-selection turn. Never executes tools.
 * Every requested function is treated as an untrusted proposal; AiService still
 * controls user consent, scopes, owner isolation, tool execution and audit.
 */
@Component
public class SpringAiToolPlanner {
    private static final int MAX_TOOLS = 16;
    private static final int MAX_CALLS = 4;
    private static final int MAX_ARGS_CHARS = 2000;
    private final ObjectMapper mapper;
    private final Map<String, URI> testEndpoints;

    @Autowired
    public SpringAiToolPlanner(ObjectMapper mapper) { this(mapper, Map.of()); }

    /** Test-only endpoint substitutions, rejected for non-loopback hosts. */
    SpringAiToolPlanner(ObjectMapper mapper, Map<String, URI> testEndpoints) {
        this.mapper = Objects.requireNonNull(mapper);
        for (var entry : testEndpoints.entrySet()) {
            AiProviderCatalog.require(entry.getKey());
            URI url = entry.getValue();
            if (!"http".equals(url.getScheme()) || !"127.0.0.1".equals(url.getHost()))
                throw new IllegalArgumentException("Only loopback test endpoints are allowed");
        }
        this.testEndpoints = Map.copyOf(testEndpoints);
    }

    public List<AiToolPlanner.Call> plan(AiSettingsService.Runtime config,
            List<DeepSeekClient.ChatMessage> messages,
            List<AiToolRegistry.Definition> definitions) throws Exception {
        Objects.requireNonNull(config);
        Objects.requireNonNull(messages);
        Objects.requireNonNull(definitions);
        if (definitions.isEmpty()) return List.of();
        if (definitions.size() > MAX_TOOLS)
            throw new IllegalArgumentException("Too many tool definitions");
        String id = config.provider().id();
        var provider = AiProviderCatalog.require(id);
        if (config.apiKey() == null || config.apiKey().isBlank())
            throw new IllegalArgumentException("Provider credentials are missing");
        if (!provider.models().contains(config.model()))
            throw new IllegalArgumentException("Unsupported provider model");

        Set<String> allowed = new HashSet<>();
        List<ToolCallback> callbacks = new ArrayList<>(definitions.size());
        for (var definition : definitions) {
            if (!allowed.add(definition.name()))
                throw new IllegalArgumentException("Duplicate tool definition");
            // A schema-only callback; if an SDK regression attempts to execute
            // tool calls automatically, it fails closed without running business logic.
            ToolDefinition schema = ToolDefinition.builder()
                .name(definition.name()).description(definition.description())
                .inputSchema(mapper.writeValueAsString(definition.parameters())).build();
            callbacks.add(new ToolCallback() {
                @Override public ToolDefinition getToolDefinition() { return schema; }
                @Override public String call(String arguments) {
                    throw new IllegalStateException("Tool auto-execution is forbidden");
                }
            });
        }

        List<Message> promptMessages = new ArrayList<>(messages.size());
        for (var message : messages) {
            switch (message.role()) {
                case "system" -> promptMessages.add(new SystemMessage(message.content()));
                case "user" -> promptMessages.add(new UserMessage(message.content()));
                case "assistant" -> promptMessages.add(new AssistantMessage(message.content()));
                default -> throw new IllegalArgumentException("Invalid tool-planner chat role");
            }
        }

        URI endpoint = testEndpoints.getOrDefault(id, provider.endpoint());
        String base = endpoint.getScheme() + "://" + endpoint.getRawAuthority();
        RetryTemplate oneAttempt = new RetryTemplate();
        oneAttempt.setRetryPolicy(new NeverRetryPolicy());

        var requestFactory = new org.springframework.http.client.JdkClientHttpRequestFactory(
            HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(8))
                .followRedirects(HttpClient.Redirect.NEVER).build());
        requestFactory.setReadTimeout(Duration.ofSeconds(35));
        RestClient.Builder transport = RestClient.builder()
            .requestFactory(requestFactory)
            // Sanitize upstream status before Spring AI may include a raw body
            // in an exception; no prompt, key, or user data in error messages.
            .defaultStatusHandler(HttpStatusCode::isError, (request, response) -> {
                int code = response.getStatusCode().value();
                HttpStatus status = code == 429 ? HttpStatus.TOO_MANY_REQUESTS :
                    code == 503 ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
                throw new ResponseStatusException(status, "AI provider request failed");
            });

        ChatModel model;
        Prompt prompt;
        if (id.equals("deepseek")) {
            DeepSeekApi api = DeepSeekApi.builder().baseUrl(base)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .restClientBuilder(transport).build();
            DeepSeekChatOptions options = DeepSeekChatOptions.builder()
                .model(config.model()).maxTokens(768).toolCallbacks(callbacks)
                .internalToolExecutionEnabled(false).build();
            model = DeepSeekChatModel.builder().deepSeekApi(api)
                .defaultOptions(options).retryTemplate(oneAttempt).build();
            prompt = new Prompt(promptMessages, options);
        } else if (provider.anthropic()) {
            AnthropicApi api = AnthropicApi.builder().baseUrl(base)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .restClientBuilder(transport).build();
            AnthropicChatOptions options = AnthropicChatOptions.builder()
                .model(config.model()).maxTokens(768).toolCallbacks(callbacks)
                .internalToolExecutionEnabled(false).build();
            model = AnthropicChatModel.builder().anthropicApi(api)
                .defaultOptions(options).retryTemplate(oneAttempt).build();
            prompt = new Prompt(promptMessages, options);
        } else {
            OpenAiApi api = OpenAiApi.builder().baseUrl(base)
                .completionsPath(endpoint.getRawPath()).apiKey(config.apiKey())
                .restClientBuilder(transport).build();
            OpenAiChatOptions options = OpenAiChatOptions.builder()
                .model(config.model()).maxTokens(768).toolCallbacks(callbacks)
                .internalToolExecutionEnabled(false).build();
            model = OpenAiChatModel.builder().openAiApi(api)
                .defaultOptions(options).retryTemplate(oneAttempt).build();
            prompt = new Prompt(promptMessages, options);
        }

        org.springframework.ai.chat.model.ChatResponse response;
        try {
            // No model-controlled iteration, retries or tool execution.
            response = model.call(prompt);
        } catch (ResponseStatusException e) {
            throw e;
        } catch (RestClientResponseException e) {
            int code = e.getStatusCode().value();
            HttpStatus status = code == 429 ? HttpStatus.TOO_MANY_REQUESTS :
                code == 503 ? HttpStatus.SERVICE_UNAVAILABLE : HttpStatus.BAD_GATEWAY;
            throw new ResponseStatusException(status, "AI provider request failed");
        } catch (RuntimeException error) {
            throw new ResponseStatusException(HttpStatus.BAD_GATEWAY,
                "AI provider tool selection unavailable");
        }
        if (response == null || response.getResults() == null ||
                response.getResults().isEmpty())
            throw new IllegalStateException("AI provider returned no tool-plan response");
        // Anthropic 1.1 creates separate generations for text/thinking and
        // for tool_use. getResult() returns only the first (possibly text-only)
        // generation; collect approved proposals from ALL generations.
        List<AssistantMessage.ToolCall> proposals = new ArrayList<>();
        for (var generation : response.getResults()) {
            if (generation.getOutput() != null && generation.getOutput().getToolCalls() != null)
                proposals.addAll(generation.getOutput().getToolCalls());
            if (proposals.size() > MAX_CALLS)
                throw new IllegalArgumentException("Too many proposed tool calls");
        }
        return validateProposals(proposals, allowed);
    }

    List<AiToolPlanner.Call> validateProposals(
            List<AssistantMessage.ToolCall> proposals, Set<String> allowed) throws Exception {
        if (proposals == null || proposals.isEmpty()) return List.of();
        if (proposals.size() > MAX_CALLS)
            throw new IllegalArgumentException("Too many proposed tool calls");
        List<AiToolPlanner.Call> result = new ArrayList<>(proposals.size());
        for (var call : proposals) {
            if (call == null || !"function".equals(call.type()) || !allowed.contains(call.name()))
                throw new IllegalArgumentException("Unapproved AI tool proposal");
            String args = call.arguments();
            if (args == null || args.length() > MAX_ARGS_CHARS)
                throw new IllegalArgumentException("Invalid tool arguments");
            JsonNode tree = mapper.readTree(args);
            if (tree == null || !tree.isObject() || tree.size() > 5)
                throw new IllegalArgumentException("Invalid tool arguments object");
            result.add(new AiToolPlanner.Call(call.name(), tree));
        }
        return List.copyOf(result);
    }
}
