package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.Mockito.*;

import com.matrix.prp.auth.model.UserProfile;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.core.task.TaskExecutor;
import org.springframework.core.task.TaskRejectedException;
import org.springframework.http.HttpStatus;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;

class AiWorkerAdmissionTests {
    @AfterEach
    void clearIdentity() {
        SecurityContextHolder.clearContext();
    }

    @Test
    void saturatedWorkerPoolDoesNotChargeQuotaOrWriteConversation() {
        long userId = 42L;
        UserProfile profile = new UserProfile(userId, "test-user", "Test User");
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(profile, null, List.of()));
        AiStore store = mock(AiStore.class);
        AiModelGateway gateway = mock(AiModelGateway.class);
        AiSettingsService settings = mock(AiSettingsService.class);
        when(gateway.legacyModel()).thenReturn("deepseek-chat");
        when(settings.selection(userId)).thenReturn(
            new AiSettingsStore.Selection("deepseek", "deepseek-chat"));
        TaskExecutor rejecting = task -> { throw new TaskRejectedException("worker queue full"); };
        AiService service = new AiService(store, gateway, settings,
            mock(AiContextConsentService.class), mock(AiToolPlanner.class),
            mock(AiToolRegistry.class), mock(AiToolAudit.class),
            new com.fasterxml.jackson.databind.ObjectMapper(),
            new org.springframework.mock.env.MockEnvironment(),
            rejecting, 1024, 200, 1000, 250000L, 1000000L);

        assertThatThrownBy(() -> service.chat(null, "hello"))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                .isEqualTo(HttpStatus.SERVICE_UNAVAILABLE));
        verifyNoInteractions(store);
    }
}
