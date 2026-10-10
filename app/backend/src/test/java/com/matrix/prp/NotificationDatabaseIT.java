package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.*;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.notification.NotificationService;
import java.time.Instant;
import java.time.LocalDateTime;
import java.time.ZoneOffset;
import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.autoconfigure.web.servlet.AutoConfigureMockMvc;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.http.HttpHeaders;
import org.springframework.http.MediaType;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.context.ActiveProfiles;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.request.MockHttpServletRequestBuilder;

@SpringBootTest
@AutoConfigureMockMvc
@ActiveProfiles("video-integration")
class NotificationDatabaseIT {
 @Autowired MockMvc mvc;
 @Autowired ObjectMapper mapper;
 @Autowired JdbcTemplate jdbc;
 @Autowired NotificationService rules;

 private MockHttpServletRequestBuilder auth(MockHttpServletRequestBuilder req,String jwt) {
   return jwt == null ? req : req.header(HttpHeaders.AUTHORIZATION,"Bearer "+jwt);
 }
 private JsonNode json(MockHttpServletRequestBuilder req) throws Exception {
   return mapper.readTree(mvc.perform(req).andExpect(status().isOk())
       .andReturn().getResponse().getContentAsString()).path("data");
 }
 private JsonNode postJson(String path,String jwt,Object payload) throws Exception {
   return json(auth(post(path).contentType(MediaType.APPLICATION_JSON).content(mapper.writeValueAsBytes(payload)),jwt));
 }
 @Test void scheduledRemindersAreSingleFireAndTenantIsolated() throws Exception {
   String admin=postJson("/api/auth/login",null,Map.of("username","video_admin","password","video-test-admin-password-2026")).path("token").asText();
   var tomorrow=Instant.now().plusSeconds(7200);
   var reminder=Map.of("title","Integration reminder","body","Private schedule test","category","STUDY",
       "scheduleType","ONCE","timezone","Asia/Shanghai","onceAt",tomorrow.toString());
   long id=postJson("/api/notification-rules",admin,reminder).asLong();
   String friendToken;
   var invite=postJson("/api/auth/invitations",admin,Map.of()).path("code").asText();
   friendToken=postJson("/api/auth/register",null,Map.of("username","notification_friend","password","friend-test-password-2026","displayName","Notification friend","invitationCode",invite)).path("token").asText();

   JsonNode own=json(auth(get("/api/notification-rules"),admin));
   assertThat(own.toString()).contains("Integration reminder");
   JsonNode other=json(auth(get("/api/notification-rules"),friendToken));
   assertThat(other.toString()).doesNotContain("Integration reminder");
   mvc.perform(auth(delete("/api/notification-rules/"+id),friendToken)).andExpect(status().isNotFound());

   // Simulate scheduler crossing the due threshold, twice; only one event may be enqueued.
   var due=LocalDateTime.ofInstant(Instant.now().minusSeconds(20),ZoneOffset.UTC);
   jdbc.update("UPDATE prp_notification_rules SET next_fire_at=? WHERE id=?",due,id);
   rules.fire(id);
   rules.fire(id);
   Integer messageCount=jdbc.queryForObject("SELECT count(*) FROM prp_notification_messages WHERE rule_id=?",Integer.class,id);
   assertThat(messageCount).isEqualTo(1);
   JsonNode inbox=json(auth(get("/api/notifications"),admin));
   assertThat(inbox.toString()).contains("Private schedule test");
   assertThat(json(auth(get("/api/notifications"),friendToken)).toString()).doesNotContain("Private schedule test");
   long msgId=jdbc.queryForObject("SELECT id FROM prp_notification_messages WHERE rule_id=?",Long.class,id);
   mvc.perform(auth(patch("/api/notifications/"+msgId+"/read"),friendToken)).andExpect(status().isNotFound());
   mvc.perform(auth(patch("/api/notifications/"+msgId+"/read"),admin)).andExpect(status().isOk());
 }
}

