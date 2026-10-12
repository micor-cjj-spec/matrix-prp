package com.matrix.prp.deployment;

import java.io.InputStreamReader;
import java.nio.charset.StandardCharsets;
import java.util.Properties;
import org.flywaydb.core.Flyway;

/** Deployment-only entry point; credentials arrive on stdin, never argv or logs. */
public final class DatabaseTool {
    private DatabaseTool() {}
    public static void main(String[] args) throws Exception {
        if (args.length != 1 || !java.util.Set.of("validate", "migrate", "baseline-v7", "info").contains(args[0]))
            throw new IllegalArgumentException("Expected validate, migrate, info or explicit baseline-v7");
        Properties p = new Properties();
        p.load(new InputStreamReader(System.in, StandardCharsets.UTF_8));
        Flyway f = Flyway.configure().dataSource(p.getProperty("url"), p.getProperty("user"), p.getProperty("password"))
                .locations("filesystem:" + p.getProperty("migrations"))
                .baselineVersion("7").baselineOnMigrate(false).cleanDisabled(true).validateOnMigrate(true).load();
        switch (args[0]) {
            case "baseline-v7" -> {
                if (f.info().applied().length != 0) throw new IllegalStateException("History exists; refusing baseline");
                f.baseline();
            }
            case "migrate" -> f.migrate();
            case "validate" -> f.validate();
            case "info" -> System.out.println("Schema version: " + (f.info().current() == null ? "none" : f.info().current().getVersion()));
            default -> throw new IllegalStateException();
        }
    }
}
