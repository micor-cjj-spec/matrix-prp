package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;
import static org.mockito.ArgumentMatchers.*;
import static org.mockito.Mockito.*;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import java.time.LocalDateTime;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

/** One-message opt-in knowledge extraction with synthetic providers and owners only. */
class PersonalOsChatExtractionServiceTest {
    private static final String CONV="00000000-0000-0000-0000-000000000007";
    private static final String TEXT="我正在学习 RAG，也希望转型 AI FDE。";
    private final AiStore store=mock(AiStore.class);
    private final AiSettingsService settings=mock(AiSettingsService.class);
    private final AiModelGateway gateway=mock(AiModelGateway.class);
    private final PersonalOsChatExtractionService service=
        new PersonalOsChatExtractionService(store,settings,gateway,new ObjectMapper(),
            true,2000,12_000_000,10_000,60_000_000);
    private final PersonalOsChatExtractionService disabled=
        new PersonalOsChatExtractionService(store,settings,gateway,new ObjectMapper(),
            false,2000,12_000_000,10_000,60_000_000);

    private void as(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Synthetic"),null,List.of()));
    }
    @AfterEach void clean() { SecurityContextHolder.clearContext(); }

    @BeforeEach void setup() {
        as(7);
        when(store.owns(7L,CONV)).thenReturn(true);
        when(store.messages(7L,CONV,92L,1)).thenReturn(
            List.of(new AiStore.Message(91L,"user",TEXT,LocalDateTime.now())));
        when(settings.selection(7L)).thenReturn(
            new AiSettingsStore.Selection("deepseek","deepseek-chat"));
        when(settings.resolve(7L,"deepseek","deepseek-chat")).thenReturn(
            new AiSettingsService.Runtime(
                AiProviderCatalog.require("deepseek"),"deepseek-chat","synthetic-secret",false));
    }
    private String token() {
        var preview=service.preview(CONV,91L);
        return service.confirm(preview.previewId()).extractionToken();
    }

    @Test void disabledFeatureCannotReadMessagesOrSendModelData() {
        assertThatThrownBy(() -> disabled.preview(CONV,91L))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verifyNoInteractions(gateway);
        verify(store,never()).messages(anyLong(),anyString(),any(),anyInt());
    }

    @Test void previewDoesNotTransmitAndConfirmDoesNotTransmit() {
        var preview=service.preview(CONV,91L);
        assertThat(preview.messageText()).isEqualTo(TEXT);
        assertThat(preview.model()).isEqualTo("deepseek-chat");
        verifyNoInteractions(gateway);
        var grant=service.confirm(preview.previewId());
        assertThat(grant.extractionToken()).isNotBlank();
        assertThatThrownBy(() -> service.confirm(preview.previewId()))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(gateway);
    }

    @Test void crossUserCannotConfirmOrConsumeAnotherOwnersApproval() throws Exception {
        var preview=service.preview(CONV,91L);
        as(8);
        assertThatThrownBy(() -> service.confirm(preview.previewId()))
            .isInstanceOf(ResponseStatusException.class);
        as(7);
        String grant=service.confirm(preview.previewId()).extractionToken();
        as(8);
        assertThatThrownBy(() -> service.extract(grant))
            .isInstanceOf(ResponseStatusException.class);
        as(7);
        when(gateway.stream(any(),anyList(),anyInt(),any())).thenReturn(
            new DeepSeekClient.Result("""
                {"candidates":[{"predicate":"DECLARES_SKILL","value":"学习 RAG",
                 "evidenceQuote":"我正在学习 RAG"}]}
                """,5,9));
        var result=service.extract(grant);
        assertThat(result.saved()).isFalse();
        assertThat(result.candidates()).hasSize(1);
        assertThat(result.candidates().getFirst().sensitivity().name()).isEqualTo("RESTRICTED");
        verify(gateway,times(1)).stream(any(),anyList(),anyInt(),any());
        assertThatThrownBy(() -> service.extract(grant))
            .isInstanceOf(ResponseStatusException.class);
    }

    @Test void changedOrDeletedChatBlocksOutflowEvenAfterOwnerApproval() {
        String grant=token();
        when(store.owns(7L,CONV)).thenReturn(false);
        assertThatThrownBy(() -> service.extract(grant))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.NOT_FOUND));
        verifyNoInteractions(gateway);
        verify(store,never()).completed(anyLong(),anyString(),anyLong(),anyLong());
    }

    @Test void changedMessageTextInvalidatesConsentBeforeExternalModelCall() {
        String grant=token();
        when(store.messages(7L,CONV,92L,1)).thenReturn(
            List.of(new AiStore.Message(91L,"user","已更新消息",LocalDateTime.now())));
        assertThatThrownBy(() -> service.extract(grant))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.CONFLICT));
        verifyNoInteractions(gateway);
    }

    @Test void fabricatedEvidenceOrAdditionalActionFieldRejectsEntireResponse() throws Exception {
        String grant=token();
        when(gateway.stream(any(),anyList(),anyInt(),any())).thenReturn(
            new DeepSeekClient.Result("""
                {"candidates":[{"predicate":"DECLARES_SKILL","value":"我会驾驶飞机",
                  "evidenceQuote":"我会驾驶飞机"}]}
                """,1,1));
        assertThatThrownBy(() -> service.extract(grant))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(e -> assertThat(((ResponseStatusException)e).getStatusCode())
                .isEqualTo(HttpStatus.BAD_GATEWAY));
        assertThatThrownBy(() -> service.extract(grant))
            .isInstanceOf(ResponseStatusException.class);
        verify(gateway,times(1)).stream(any(),anyList(),anyInt(),any());
    }

    @Test void modelReceivesExactlySelectedUserMessageAsUntrustedDataOnly() throws Exception {
        String grant=token();
        when(gateway.stream(any(),anyList(),anyInt(),any()))
            .thenReturn(new DeepSeekClient.Result("""
                {"candidates":[]}
                """,0,1));
        var extracted=service.extract(grant);
        assertThat(extracted.candidates()).isEmpty();
        verify(gateway).stream(any(),argThat(messages ->
                messages.size()==2
                && messages.get(0).role().equals("system")
                && messages.get(1).role().equals("user")
                && messages.get(1).content().contains("UNTRUSTED_USER_MESSAGE_BEGIN")
                && messages.get(1).content().contains(TEXT)
                && !messages.get(1).content().contains("PRIVATE_CHAT_HISTORY")),
            eq(900),any());
        verify(store).completed(eq(7L),anyString(),eq(0L),eq(1L));
    }

    @Test void unownedOrAssistantMessagesCannotBeReviewed() {
        when(store.owns(7L,CONV)).thenReturn(false);
        assertThatThrownBy(() -> service.preview(CONV,91L))
            .isInstanceOf(ResponseStatusException.class);
        when(store.owns(7L,CONV)).thenReturn(true);
        when(store.messages(7L,CONV,92L,1)).thenReturn(
            List.of(new AiStore.Message(91L,"assistant",TEXT,LocalDateTime.now())));
        assertThatThrownBy(() -> service.preview(CONV,91L))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(gateway);
    }

    @Test void modelSelectionChangeInvalidatesOneTimePreview() {
        var review=service.preview(CONV,91L);
        when(settings.selection(7L)).thenReturn(new AiSettingsStore.Selection(
            "openai","gpt-4o-mini"));
        assertThatThrownBy(() -> service.confirm(review.previewId()))
            .isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(gateway);
    }
}
