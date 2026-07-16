package com.matrix.prp.common.api;

import java.nio.file.Files;
import java.nio.file.Path;
import java.sql.Connection;
import java.util.Arrays;
import java.util.List;
import javax.sql.DataSource;
import org.springframework.beans.factory.ObjectProvider;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.core.env.Environment;
import org.springframework.stereotype.Service;

@Service
public class RuntimeHealthService {

    private final ObjectProvider<DataSource> dataSourceProvider;
    private final Environment environment;
    private final Path knowledgeRoot;

    public RuntimeHealthService(
            ObjectProvider<DataSource> dataSourceProvider,
            Environment environment,
            @Value("${matrix-prp.knowledge.root:../../knowledge}") String knowledgeRoot) {
        this.dataSourceProvider = dataSourceProvider;
        this.environment = environment;
        this.knowledgeRoot = Path.of(knowledgeRoot).toAbsolutePath().normalize();
    }

    public RuntimeHealth runtime() {
        DataSource dataSource = dataSourceProvider.getIfAvailable();
        String persistence = dataSource == null ? "in-memory" : "mysql";
        String database = databaseStatus(dataSource);
        boolean knowledgeAvailable = Files.isDirectory(knowledgeRoot);
        String status = isRuntimeUp(database, knowledgeAvailable) ? "UP" : "DEGRADED";

        return new RuntimeHealth(
                status,
                persistence,
                database,
                knowledgeRoot.toString(),
                knowledgeAvailable,
                activeProfiles());
    }

    private String databaseStatus(DataSource dataSource) {
        if (dataSource == null) {
            return "NOT_CONFIGURED";
        }
        try (Connection connection = dataSource.getConnection()) {
            return connection.isValid(2) ? "UP" : "DOWN";
        } catch (Exception ignored) {
            return "DOWN";
        }
    }

    private boolean isRuntimeUp(String database, boolean knowledgeAvailable) {
        return ("UP".equals(database) || "NOT_CONFIGURED".equals(database)) && knowledgeAvailable;
    }

    private List<String> activeProfiles() {
        String[] profiles = environment.getActiveProfiles();
        if (profiles.length == 0) {
            return List.of("default");
        }
        return Arrays.asList(profiles);
    }
}
