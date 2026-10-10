package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.delete;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.put;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import java.nio.charset.StandardCharsets;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("video-integration")
class VideoDatabaseIT {
    @Autowired private MockMvc mvc;
    @Autowired private ObjectMapper mapper;

    private MockHttpServletRequestBuilder auth(MockHttpServletRequestBuilder request, String token) {
        return request.header(HttpHeaders.AUTHORIZATION, "Bearer " + token);
    }

    private JsonNode postJson(String url, String token, Object body) throws Exception {
        MockHttpServletRequestBuilder request = post(url).contentType(MediaType.APPLICATION_JSON)
                .content(mapper.writeValueAsBytes(body));
        if (token != null) request = auth(request, token);
        return mapper.readTree(mvc.perform(request).andExpect(status().isOk())
                .andReturn().getResponse().getContentAsString()).path("data");
    }

    private String login(String username, String password) throws Exception {
        return postJson("/api/auth/login", null, Map.of("username", username, "password", password))
                .path("token").asText();
    }

    @Test
    void uploadPlaybackRangeProgressAndTenantIsolationWorkAgainstRealMySql() throws Exception {
        String admin = login("video_admin", "video-test-admin-password-2026");
        long folderId = postJson("/api/video/folders", admin, Map.of("name", "Course"))
                .path("id").asLong();

        byte[] content = new byte[] {0, 0, 0, 20, 102, 116, 121, 112, 105, 115, 111, 109,
                0, 0, 0, 0, 0, 0, 0, 0};
        String uploadId = postJson("/api/video/uploads", admin,
                Map.of("folderId", folderId, "title", "Lesson 01.mp4", "sizeBytes", content.length))
                .path("uploadId").asText();


        mvc.perform(auth(put("/api/video/uploads/{id}/parts/0", uploadId)
                .contentType(MediaType.APPLICATION_OCTET_STREAM).content(content), admin))
                .andExpect(status().isOk());
        JsonNode uploadState = mapper.readTree(mvc.perform(
                auth(get("/api/video/uploads/{id}", uploadId), admin))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString())
                .path("data");
        assertThat(uploadState.path("receivedParts").get(0).asInt()).isEqualTo(0);

        long videoId = Long.parseLong(postJson("/api/video/uploads/" + uploadId + "/complete", admin, Map.of())
                .path("id").asText());
        JsonNode results = mapper.readTree(mvc.perform(auth(
                get("/api/video/items").param("folderId", Long.toString(folderId)), admin))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data");
        assertThat(results.size()).isEqualTo(1);
        assertThat(results.get(0).path("id").asLong()).isEqualTo(videoId);

        mvc.perform(auth(put("/api/video/items/{id}/progress", videoId)
                .contentType(MediaType.APPLICATION_JSON)
                .content("{\"positionSeconds\":8.5,\"durationSeconds\":20}"), admin))
                .andExpect(status().isOk());
        JsonNode afterProgress = mapper.readTree(mvc.perform(auth(get("/api/video/items"), admin))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data");
        assertThat(afterProgress.get(0).path("positionSeconds").asDouble()).isEqualTo(8.5);

        String url = mapper.readTree(mvc.perform(auth(
                get("/api/video/items/{id}/playback", videoId), admin))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString())
                .path("data").path("url").asText();
        String ticket = url.substring(url.indexOf("ticket=") + 7);
        var ranged = mvc.perform(get("/api/video/media/{id}", videoId).param("ticket", ticket)
                .header(HttpHeaders.RANGE, "bytes=4-7"))
                .andExpect(status().isPartialContent()).andReturn().getResponse();
        assertThat(new String(ranged.getContentAsByteArray(), StandardCharsets.US_ASCII)).isEqualTo("ftyp");
        assertThat(ranged.getHeader("Content-Range")).isEqualTo("bytes 4-7/20");
        mvc.perform(get("/api/video/media/{id}", videoId).param("ticket", ticket + "bad"))
                .andExpect(status().isForbidden());

        String invite = postJson("/api/auth/invitations", admin, Map.of()).path("code").asText();
        String friend = postJson("/api/auth/register", null, Map.of(
                "username", "video_friend_case", "password", "friend-password-2026",
                "displayName", "Friend", "invitationCode", invite)).path("token").asText();
        JsonNode friendVideos = mapper.readTree(mvc.perform(auth(get("/api/video/items"), friend))
                .andExpect(status().isOk()).andReturn().getResponse().getContentAsString()).path("data");
        assertThat(friendVideos.size()).isZero();
        mvc.perform(auth(get("/api/video/items").param("folderId", Long.toString(folderId)), friend))
                .andExpect(status().isNotFound());
        mvc.perform(auth(get("/api/video/items/{id}/playback", videoId), friend))
                .andExpect(status().isNotFound());
        mvc.perform(auth(put("/api/video/items/{id}", videoId).contentType(MediaType.APPLICATION_JSON)
                .content("{\"title\":\"stolen\"}"), friend)).andExpect(status().isNotFound());
        mvc.perform(auth(delete("/api/video/items/{id}", videoId), friend))
                .andExpect(status().isNotFound());
        mvc.perform(auth(post("/api/video/uploads").contentType(MediaType.APPLICATION_JSON).content(
                mapper.writeValueAsBytes(Map.of("folderId", folderId,
                        "title", "forbidden.mp4", "sizeBytes", content.length))), friend))
                .andExpect(status().isNotFound());
        mvc.perform(auth(delete("/api/video/folders/{id}", folderId), friend))
                .andExpect(status().isNotFound());
    }
}
