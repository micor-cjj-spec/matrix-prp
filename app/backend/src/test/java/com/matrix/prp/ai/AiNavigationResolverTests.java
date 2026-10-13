package com.matrix.prp.ai;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.tasks.service.TaskService;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class AiNavigationResolverTests {
    private final ObjectMapper json = new ObjectMapper();
    private final AiNavigationResolver resolver = new AiNavigationResolver(mock(TaskService.class));

    @Test void onlyKnownRelativeRoutesAreReturned() throws Exception {
        assertThat(resolver.resolve("finance",json.readTree("{\"month\":\"2026-10\"}")).route())
            .isEqualTo("/finance?month=2026-10");
        assertThat(resolver.resolve("wellness",json.readTree("{\"date\":\"2026-10-12\"}")).route())
            .isEqualTo("/wellness?date=2026-10-12");
        assertThat(resolver.resolve("tasks",json.readTree("{}")).route()).isEqualTo("/tasks");
        assertThatThrownBy(()->resolver.resolve("https://evil.example",json.readTree("{}")))
            .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(()->resolver.resolve("finance",json.readTree("{\"recordId\":42}")))
            .isInstanceOf(ResponseStatusException.class);
    }
}
