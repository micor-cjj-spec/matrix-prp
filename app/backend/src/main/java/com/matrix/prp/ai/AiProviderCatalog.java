package com.matrix.prp.ai;

import java.net.URI;
import java.util.List;
import java.util.Map;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Fixed provider allowlist: users cannot configure arbitrary upstream URLs (SSRF prevention). */
public final class AiProviderCatalog {
    private AiProviderCatalog() {}
    public record Provider(String id, String name, URI endpoint, String defaultModel, List<String> models,
                           boolean anthropic) {}
    public static final List<Provider> PROVIDERS = List.of(
        new Provider("deepseek", "DeepSeek", URI.create("https://api.deepseek.com/chat/completions"),
            "deepseek-chat", List.of("deepseek-chat", "deepseek-reasoner"), false),
        new Provider("kimi", "Kimi / Moonshot", URI.create("https://api.moonshot.ai/v1/chat/completions"),
            "kimi-k2.5", List.of("kimi-k2.5", "moonshot-v1-8k"), false),
        new Provider("openai", "ChatGPT / OpenAI", URI.create("https://api.openai.com/v1/chat/completions"),
            "gpt-4.1-mini", List.of("gpt-4.1-mini", "gpt-4.1"), false),
        new Provider("gemini", "Gemini", URI.create("https://generativelanguage.googleapis.com/v1beta/openai/chat/completions"),
            "gemini-2.5-flash", List.of("gemini-2.5-flash", "gemini-2.5-pro"), false),
        new Provider("claude", "Claude / Anthropic", URI.create("https://api.anthropic.com/v1/messages"),
            "claude-sonnet-4-5", List.of("claude-sonnet-4-5", "claude-haiku-4-5"), true),
        new Provider("qwen", "Qwen / Alibaba Cloud", URI.create("https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions"),
            "qwen-plus", List.of("qwen-plus", "qwen-max"), false)
    );
    private static final Map<String, Provider> LOOKUP = PROVIDERS.stream()
        .collect(java.util.stream.Collectors.toUnmodifiableMap(Provider::id, p -> p));

    public static Provider require(String id) {
        Provider provider = LOOKUP.get(id);
        if (provider == null) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported AI provider");
        return provider;
    }
    public static String validateModel(String model) {
        if (model == null || !model.matches("[A-Za-z0-9][A-Za-z0-9._:/-]{0,99}"))
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid model identifier");
        return model;
    }
}
