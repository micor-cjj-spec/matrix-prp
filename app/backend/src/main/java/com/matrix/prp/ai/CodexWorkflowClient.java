package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.time.Duration;
import java.util.List;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.stereotype.Component;

/**
 * Exact repository + workflow allowlist. No user-provided URLs, commands or tokens.
 * A GitHub-hosted ephemeral runner executes Codex; this Spring Boot process never runs shell commands.
 */
@Component
public class CodexWorkflowClient {
    public static final String REPOSITORY = "micor-cjj-spec/matrix-prp";
    public static final String WORKFLOW = "codex-prp-worker.yml";
    private static final String API = "https://api.github.com/repos/" + REPOSITORY;
    public record Run(String status, String conclusion, String url, String pullRequestUrl) {}
    private final ObjectMapper json;
    private final HttpClient http = HttpClient.newBuilder().connectTimeout(Duration.ofSeconds(5))
        .followRedirects(HttpClient.Redirect.NEVER).build();
    private final boolean enabled;
    private final String token;
    private final String repository;

    public CodexWorkflowClient(ObjectMapper json,
        @Value("${matrix-prp.ai.codex.enabled:false}") boolean enabled,
        @Value("${matrix-prp.ai.codex.github-token:}") String token,
        @Value("${matrix-prp.ai.codex.repository:micor-cjj-spec/matrix-prp}") String repository) {
        this.json=json;this.enabled=enabled;this.token=token;this.repository=repository;
    }
    public boolean configured() {
        return enabled && REPOSITORY.equals(repository) && token!=null && token.length()>=20
            && !token.contains("\n") && !token.contains("\r");
    }
    private HttpRequest.Builder authorized(URI url) {
        return HttpRequest.newBuilder(url).timeout(Duration.ofSeconds(15))
            .header("Accept","application/vnd.github+json")
            .header("X-GitHub-Api-Version","2022-11-28")
            .header("Authorization","Bearer " + token);
    }
    public void dispatch(CodexJobStore.Job job) throws Exception {
        if (!configured() || !REPOSITORY.equals(job.repository()))
            throw new IllegalStateException("Codex dispatch is disabled");
        byte[] payload = json.writeValueAsBytes(java.util.Map.of("ref","main",
            "inputs",java.util.Map.of("task_id",job.id(),"task_type",job.taskType(),"task_prompt",job.prompt())));
        HttpRequest req = authorized(URI.create(API+"/actions/workflows/"+WORKFLOW+"/dispatches"))
            .header("Content-Type","application/json")
            .POST(HttpRequest.BodyPublishers.ofByteArray(payload)).build();
        HttpResponse<Void> resp = http.send(req,HttpResponse.BodyHandlers.discarding());
        if (resp.statusCode()!=204)
            throw new IllegalStateException("GitHub workflow dispatch rejected");
    }
    /** Live read-only status; absence of a run is not evidence that dispatch failed. */
    public Run status(CodexJobStore.Job job) {
        if (!configured()) return null;
        try {
            HttpRequest req=authorized(URI.create(API+"/actions/workflows/"+WORKFLOW+
                "/runs?event=workflow_dispatch&per_page=100")).GET().build();
            HttpResponse<String> response=http.send(req,HttpResponse.BodyHandlers.ofString());
            if(response.statusCode()!=200 || response.body().length()>750_000) return null;
            JsonNode runs=json.readTree(response.body()).path("workflow_runs");
            if(!runs.isArray()) return null;
            for(JsonNode run:runs) {
                if (!("PRP-CODEX-"+job.id()).equals(run.path("display_title").asText())) continue;
                String url=run.path("html_url").asText();
                if (!url.startsWith("https://github.com/"+REPOSITORY+"/actions/runs/")) return null;
                String state=run.path("status").asText("unknown");
                String outcome=run.path("conclusion").asText("");
                return new Run(state,outcome,url,pullRequest(job));
            }
        } catch (Exception ignored) {
            // Network error must not cause a second dispatch or expose GitHub credentials.
        }
        return null;
    }
    private String pullRequest(CodexJobStore.Job job) {
        try {
            String branch="codex/prp-"+job.id();
            HttpRequest req=authorized(URI.create(API+"/pulls?state=all&head=micor-cjj-spec:"+
                branch+"&per_page=5")).GET().build();
            HttpResponse<String> response=http.send(req,HttpResponse.BodyHandlers.ofString());
            if(response.statusCode()!=200 || response.body().length()>150_000) return null;
            JsonNode list=json.readTree(response.body());
            if (!list.isArray()) return null;
            for(JsonNode pr:list) {
                String actual=pr.path("head").path("ref").asText();
                String url=pr.path("html_url").asText();
                if (branch.equals(actual) && url.startsWith("https://github.com/"+REPOSITORY+"/pull/"))
                    return url;
            }
        } catch (Exception ignored) { /* Status is best effort, no retries/side effects */ }
        return null;
    }
}
