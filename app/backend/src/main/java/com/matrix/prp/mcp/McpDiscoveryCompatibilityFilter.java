package com.matrix.prp.mcp;

import com.fasterxml.jackson.core.JsonFactory;
import com.fasterxml.jackson.core.StreamReadConstraints;
import com.fasterxml.jackson.core.StreamReadFeature;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import io.modelcontextprotocol.spec.McpSchema;
import jakarta.servlet.*;
import jakarta.servlet.http.*;
import java.io.*;
import java.nio.charset.StandardCharsets;
import java.util.*;
import java.util.function.Supplier;
import org.springframework.http.MediaType;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.filter.OncePerRequestFilter;

/** A discovery bridge for the SDK's real legacy versions, never a claim of MCP 2.0 support.
 * Installed after AuthorizationFilter in the existing OAuth-only security chain.
 */
final class McpDiscoveryCompatibilityFilter extends OncePerRequestFilter {
    static final int MAX_BODY = 32768;
    private static final String VERSION_META = "io.modelcontextprotocol/protocolVersion";
    private static final Set<String> LEGACY_METHODS = Set.of("initialize", "notifications/initialized",
        "ping", "tools/list", "tools/call", "resources/list", "resources/read", "resources/templates/list",
        "prompts/list", "prompts/get", "completion/complete", "logging/setLevel");
    private final ObjectMapper mapper = new ObjectMapper(JsonFactory.builder()
        .enable(StreamReadFeature.STRICT_DUPLICATE_DETECTION)
        .streamReadConstraints(StreamReadConstraints.builder().maxNestingDepth(24)
            .maxStringLength(MAX_BODY).maxNumberLength(32).build()).build())
        .enable(com.fasterxml.jackson.databind.DeserializationFeature.FAIL_ON_TRAILING_TOKENS);
    private final Supplier<Map<String, Object>> discovery;
    private final String metadataUri;

    McpDiscoveryCompatibilityFilter(Supplier<Map<String, Object>> discovery, String metadataUri) {
        this.discovery = discovery; this.metadataUri = metadataUri;
    }

    @Override protected void doFilterInternal(HttpServletRequest request, HttpServletResponse response,
                                              FilterChain chain) throws ServletException, IOException {
        if (!"POST".equals(request.getMethod())) { chain.doFilter(request, response); return; }
        var auth = SecurityContextHolder.getContext().getAuthentication();
        if (auth == null || !auth.isAuthenticated() || !(auth.getPrincipal() instanceof UserProfile)) {
            response.setStatus(401);
            response.setHeader("WWW-Authenticate", "Bearer resource_metadata=\"" + metadataUri + "\"");
            return;
        }
        try {
            if (request.getContentType() == null || !MediaType.APPLICATION_JSON.isCompatibleWith(
                    MediaType.parseMediaType(request.getContentType()))) {
                error(response, null, 415, -32600, "JSON content type required"); return;
            }
        } catch (IllegalArgumentException e) {
            error(response, null, 415, -32600, "JSON content type required"); return;
        }
        byte[] body = request.getInputStream().readNBytes(MAX_BODY + 1);
        if (body.length > MAX_BODY) { error(response, null, 413, -32600, "Request too large"); return; }
        JsonNode node;
        try { node = mapper.readTree(body); }
        catch (IOException e) { error(response, null, 400, -32700, "Parse error"); return; }
        JsonNode id = node == null ? null : node.get("id");
        if (node == null || !node.isObject() || !"2.0".equals(node.path("jsonrpc").asText())
                || !node.path("method").isTextual()
                || node.path("method").asText().length() > 128
                || (id != null && !(id.isTextual() && id.asText().length() <= 128
                    || id.isIntegralNumber() && id.bigIntegerValue().bitLength() <= 53))
                || (node.hasNonNull("params") && !node.get("params").isObject())) {
            error(response, null, 400, -32600, "Invalid request"); return;
        }
        String method = node.path("method").asText();
        JsonNode version = node.path("params").path("_meta").path(VERSION_META);
        String header = request.getHeader("MCP-Protocol-Version");
        if (!version.isMissingNode() && !version.isTextual()) {
            error(response, id, 400, -32602, "Invalid protocol version"); return;
        }
        if (header != null && version.isTextual() && !header.equals(version.asText())) {
            error(response, id, 400, -32020, "Protocol version header mismatch"); return;
        }
        if ("server/discover".equals(method)) {
            if (id == null) { error(response, null, 400, -32600, "Discovery requires a request ID"); return; }
            String accept = request.getHeader("Accept");
            boolean json;
            try { json = accept != null && MediaType.parseMediaTypes(accept).stream()
                .anyMatch(t -> t.isCompatibleWith(MediaType.APPLICATION_JSON) && t.getQualityValue() > 0); }
            catch (IllegalArgumentException e) { json = false; }
            if (!json) { error(response, id, 406, -32600, "JSON response must be accepted"); return; }
            // Legacy SDK: never return a modern success for a version it cannot serve.
            // A non-modern HTTP error lets a dual-era client initialize the legacy SDK.
            error(response, id, 400, -32601, "Method not found"); return;
        }

        String requested = version.isTextual() ? version.asText() : header;
        if (requested != null && requested.matches("\\d{4}-\\d{2}-\\d{2}")
                && requested.compareTo(McpSchema.LATEST_PROTOCOL_VERSION) > 0) {
            error(response, id, 400, -32601, "Method not found"); return;
        }
        if (!LEGACY_METHODS.contains(method)) {
            error(response, id, 404, -32601, "Method not found"); return;
        }
        chain.doFilter(new HttpServletRequestWrapper(request) {
            @Override public ServletInputStream getInputStream() {
                var stream = new ByteArrayInputStream(body);
                return new ServletInputStream() {
                    public int read() { return stream.read(); }
                    public boolean isFinished() { return stream.available() == 0; }
                    public boolean isReady() { return true; }
                    public void setReadListener(ReadListener listener) { throw new UnsupportedOperationException(); }
                };
            }
            @Override public BufferedReader getReader() {
                return new BufferedReader(new InputStreamReader(getInputStream(), StandardCharsets.UTF_8));
            }
        }, response);
    }

    private com.fasterxml.jackson.databind.node.ObjectNode errorNode(JsonNode id, int code, String message) {
        var reply = mapper.createObjectNode().put("jsonrpc", "2.0");
        reply.set("id", id == null ? mapper.getNodeFactory().nullNode() : id);
        reply.putObject("error").put("code", code).put("message", message); return reply;
    }
    private void error(HttpServletResponse response, JsonNode id, int status, int code, String message) throws IOException {
        write(response, status, errorNode(id, code, message));
    }
    private void write(HttpServletResponse response, int status, JsonNode body) throws IOException {
        response.setStatus(status); response.setContentType("application/json");
        response.setHeader("Cache-Control", "no-store");
        mapper.writeValue(response.getOutputStream(), body);
    }
}
