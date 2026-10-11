package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.modules.service.ModuleService;
import java.util.Set;
import java.util.stream.Collectors;
import org.junit.jupiter.api.Test;

class ModuleRegistryTests {
    private final ModuleService modules = new ModuleService(new ObjectMapper());

    @Test
    void listsAllShippedUserFacingModules() {
        assertThat(modules.listFeatures()).extracting("code")
                .containsExactly("dashboard", "records", "tasks", "finance", "reviews", "tags",
                        "knowledge", "videos", "notifications");
        assertThat(modules.listDomains()).extracting("code")
                .containsExactly("life", "learning", "work", "interests", "social", "finance");
    }

    @Test
    void moduleIdentifiersRemainUniqueWithinType() {
        Set<String> keys = modules.list().stream()
                .map(module -> module.type() + ":" + module.code())
                .collect(Collectors.toSet());
        assertThat(keys).hasSize(modules.list().size());
        assertThat(modules.list()).allMatch(module -> module.enabled() && !module.name().isBlank());
    }
}
