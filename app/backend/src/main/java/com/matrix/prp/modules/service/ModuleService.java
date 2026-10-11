package com.matrix.prp.modules.service;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.modules.model.ModuleItem;
import java.io.IOException;
import java.io.InputStream;
import java.util.ArrayList;
import java.util.List;
import org.springframework.core.io.ClassPathResource;
import org.springframework.stereotype.Service;

@Service
public class ModuleService {
    private static final String FEATURE = "feature";
    private static final String DOMAIN = "domain";

    private final List<ModuleItem> modules;

    public ModuleService(ObjectMapper objectMapper) {
        this.modules = loadModules(objectMapper);
    }

    private static List<ModuleItem> loadModules(ObjectMapper mapper) {
        try (InputStream input = new ClassPathResource("feature-registry.json").getInputStream()) {
            JsonNode entries = mapper.readTree(input).path("modules");
            if (!entries.isArray() || entries.isEmpty()) {
                throw new IllegalStateException("Feature registry missing or empty");
            }
            List<ModuleItem> loaded = new ArrayList<>();
            for (JsonNode node : entries) {
                loaded.add(new ModuleItem(
                        node.path("code").asText(),
                        node.path("name").asText(),
                        node.path("description").asText(),
                        node.path("type").asText(),
                        node.path("sortOrder").asInt(),
                        node.path("enabled").asBoolean()));
            }
            return List.copyOf(loaded);
        } catch (IOException e) {
            throw new IllegalStateException("Unable to read classpath feature-registry.json", e);
        }
    }

    public List<ModuleItem> list() {
        return modules;
    }

    public List<ModuleItem> listFeatures() {
        return listByType(FEATURE);
    }

    public List<ModuleItem> listDomains() {
        return listByType(DOMAIN);
    }

    private List<ModuleItem> listByType(String type) {
        return modules.stream().filter(module -> type.equals(module.type())).toList();
    }
}
