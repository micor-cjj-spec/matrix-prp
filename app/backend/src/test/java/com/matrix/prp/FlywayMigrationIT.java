package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.Statement;
import java.sql.SQLException;
import org.flywaydb.core.Flyway;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.condition.EnabledIfEnvironmentVariable;

/** Runs on two isolated real MySQL schemas provisioned by CI; never targets production. */
@EnabledIfEnvironmentVariable(named = "MATRIX_PRP_FLYWAY_FRESH_URL", matches = "jdbc:mysql:.+")
class FlywayMigrationIT {
    private String user() { return System.getenv("MATRIX_PRP_FLYWAY_DB_USER"); }
    private String password() { return System.getenv("MATRIX_PRP_FLYWAY_DB_PASSWORD"); }

    private Flyway flyway(String url) {
        return Flyway.configure().dataSource(url, user(), password())
                .locations("classpath:db/migration")
                .baselineVersion("7")
                .baselineOnMigrate(false)
                .cleanDisabled(true)
                .load();
    }

    private long count(String url, String sql) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, user(), password());
                PreparedStatement statement = connection.prepareStatement(sql);
                ResultSet result = statement.executeQuery()) {
            result.next();
            return result.getLong(1);
        }
    }

    private String existingAiRowSnapshot(String url) throws SQLException {
        // Match the production controller's "SELECT *" fingerprint contract,
        // including the number and ordering of old table columns.
        try (Connection c=DriverManager.getConnection(url,user(),password());
             Statement st=c.createStatement();
             ResultSet rs=st.executeQuery("SELECT * FROM prp_ai_conversations WHERE id='00000000-0000-0000-0000-00000000f018'")) {
            assertThat(rs.next()).isTrue();
            var md=rs.getMetaData();
            StringBuilder snapshot=new StringBuilder();
            for(int i=1;i<=md.getColumnCount();i++)
                snapshot.append(md.getColumnName(i)).append('=').append(rs.getString(i)).append('|');
            return snapshot.toString();
        }
    }

    private void insertSentinel(String url, String username) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, user(), password())) {
            try (PreparedStatement userInsert = connection.prepareStatement(
                    "INSERT INTO prp_users(username,display_name,password_hash) VALUES(?,?,?)")) {
                userInsert.setString(1, username);
                userInsert.setString(2, "Migration CI");
                userInsert.setString(3, "not-a-login");
                userInsert.executeUpdate();
            }
            try (PreparedStatement taskInsert = connection.prepareStatement(
                    "INSERT INTO prp_tasks(user_id,module_code,title,description,created_at,updated_at) " +
                            "SELECT id,'work','MIGRATION_SENTINEL','preserve row',NOW(6),NOW(6) " +
                            "FROM prp_users WHERE username=?")) {
                taskInsert.setString(1, username);
                assertThat(taskInsert.executeUpdate()).isEqualTo(1);
            }
        }
    }


    private void createLegacyMojibakeFixtures(String url) throws SQLException {
        try (Connection connection = DriverManager.getConnection(url, user(), password());
                Statement statement = connection.createStatement()) {
            // Reproduce a UTF-8 file imported through a latin1 MySQL client.
            assertThat(statement.executeUpdate(
                    "UPDATE prp_wellness_foods SET name=CONVERT(0xE59C9FE8B186 USING latin1),"
                            + "source_note=CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE697A0E9A29DE5A496E6B2B9E88482 USING latin1) "
                            + "WHERE owner_user_id IS NULL AND CAST(name AS BINARY)=CAST(CONVERT(0xE59C9FE8B186 USING utf8mb4) AS BINARY)"
                            + " AND preparation='cooked' AND calories_100g=87")).isEqualTo(1);
            statement.executeUpdate(
                    "INSERT INTO prp_wellness_meals(user_id,meal_date,meal_type,note)"
                    + " SELECT id,'2026-10-11','BREAKFAST','MIGRATION_TEXT_SENTINEL'"
                    + " FROM prp_users WHERE username='flyway_legacy_ci'");
            statement.executeUpdate(
                    "INSERT INTO prp_wellness_meal_items(meal_id,food_id,food_name,grams,calories,"
                    + "protein_g,carbs_g,fat_g,is_estimate)"
                    + " SELECT m.id,f.id,f.name,100,87,1.9,20.1,0.1,1"
                    + " FROM prp_wellness_meals m JOIN prp_wellness_foods f"
                    + " ON f.owner_user_id IS NULL AND f.calories_100g=87"
                    + " WHERE m.note='MIGRATION_TEXT_SENTINEL'");
            // Identical-looking PRIVATE data must not be globally rewritten.
            statement.executeUpdate(
                    "INSERT INTO prp_wellness_foods(owner_user_id,name,preparation,calories_100g,"
                    + "protein_100g,carbs_100g,fat_100g,source_note)"
                    + " SELECT id,CONVERT(0xE59C9FE8B186 USING latin1),'cooked',87,1.9,20.1,0.1,"
                    + "'user supplied' FROM prp_users WHERE username='flyway_legacy_ci'");
        }
    }

    @Test
    void newSchemaMigratesTwiceWithoutChangingExistingRows() throws SQLException {
        String url = System.getenv("MATRIX_PRP_FLYWAY_FRESH_URL");
        // Recreate production's V17 -> V18 upgrade, with an existing historical
        // conversation. Adding any columns would break the SELECT * fingerprint.
        Flyway old=Flyway.configure().dataSource(url,user(),password())
                .locations("classpath:db/migration")
                .target(org.flywaydb.core.api.MigrationVersion.fromVersion("17"))
                .cleanDisabled(true).load();
        assertThat(old.migrate().migrationsExecuted).isEqualTo(17);
        try(Connection connection=DriverManager.getConnection(url,user(),password());
            Statement st=connection.createStatement()) {
            st.executeUpdate("INSERT INTO prp_ai_conversations(id,user_id,title,created_at,updated_at) VALUES "
                    + "('00000000-0000-0000-0000-00000000f018',99999,'historic chat',NOW(6),NOW(6))");
        }
        String originalRow=existingAiRowSnapshot(url);
        assertThat(count(url,"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE()"
                +" AND table_name='prp_ai_conversations'")).isEqualTo(5);
        Flyway migration = flyway(url);
        assertThat(migration.migrate().migrationsExecuted).isEqualTo(3);
        assertThat(existingAiRowSnapshot(url)).isEqualTo(originalRow);
        assertThat(count(url,"SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE()"
                +" AND table_name='prp_ai_conversations'")).isEqualTo(5);
        // End-to-end JDBC service uses only the new companion table for
        // rename/delete. Both the owner boundary and parent row hash hold.
        var source=new org.springframework.jdbc.datasource.DriverManagerDataSource(url,user(),password());
        var chat=new com.matrix.prp.ai.JdbcAiStore(new org.springframework.jdbc.core.JdbcTemplate(source));
        String id="00000000-0000-0000-0000-00000000f018";
        assertThat(chat.list(99999L)).extracting(com.matrix.prp.ai.AiStore.Conversation::title)
            .contains("historic chat");
        assertThatThrownBy(()->chat.rename(88L,id,"foreign change"))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
        assertThatThrownBy(()->chat.softDelete(88L,id))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
        chat.rename(99999L,id,"user renamed");
        assertThat(chat.list(99999L)).extracting(com.matrix.prp.ai.AiStore.Conversation::title)
            .contains("user renamed");
        assertThat(existingAiRowSnapshot(url)).isEqualTo(originalRow);
        chat.softDelete(99999L,id);
        assertThat(chat.owns(99999L,id)).isFalse();
        assertThat(chat.list(99999L)).isEmpty();
        assertThatThrownBy(()->chat.rename(99999L,id,"restore incorrectly"))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
        assertThatThrownBy(()->chat.softDelete(99999L,id))
            .isInstanceOf(org.springframework.web.server.ResponseStatusException.class);
        assertThat(existingAiRowSnapshot(url)).isEqualTo(originalRow);
        assertThat(migration.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history WHERE success=1")).isEqualTo(20);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'prp_ai_%'")).isEqualTo(10);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() " +
                "AND table_name='prp_ai_conversations' AND column_name IN ('deleted_at','is_pinned','title_source')"))
            .as("Existing conversation table must never be ALTERed by V18").isZero();
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() " +
                "AND table_name='prp_ai_conversation_meta' AND column_name IN ('deleted_at','is_pinned','title_source')"))
            .isEqualTo(3);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='prp_wellness_ai_drafts'")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='prp_wellness_ai_action_targets'")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='prp_wellness_dish_templates'")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() AND table_name='prp_wellness_meal_items' AND column_name IN ('protein_g','carbs_g','fat_g') AND is_nullable='YES'")).isEqualTo(3);

        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name='prp_finance_transfers'")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name IN ('prp_finance_import_batches','prp_finance_import_rows','prp_finance_source_links')")).isEqualTo(3);
        insertSentinel(url, "flyway_fresh_ci");
        long before = count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'");
        assertThat(migration.migrate().migrationsExecuted).isZero();
        assertThat(count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'")).isEqualTo(before);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_foods WHERE owner_user_id IS NULL"))
                .isGreaterThanOrEqualTo(140);
    }

    @Test
    void explicitLegacyBaselinePreservesPreexistingRows() throws SQLException {
        String url = System.getenv("MATRIX_PRP_FLYWAY_LEGACY_URL");
        insertSentinel(url, "flyway_legacy_ci");
        long before = count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'");
        createLegacyMojibakeFixtures(url);
        // Legacy expense has no configured account; V13 must create and link it losslessly.
        try (Connection connection = DriverManager.getConnection(url, user(), password());
             Statement statement=connection.createStatement()) {
            statement.executeUpdate("INSERT INTO prp_finance_transactions "
                    + "(user_id,type,amount,category,account,merchant,note,transaction_date,created_at,updated_at) "
                    + "SELECT id,'expense',25.00,'food','LEGACY_FINANCE_WALLET','store','legacy preserved',"
                    + "'2026-10-01',NOW(6),NOW(6) FROM prp_users WHERE username='flyway_legacy_ci'");
        }
        long financeBefore=count(url,"SELECT COUNT(*) FROM prp_finance_transactions WHERE note='legacy preserved'");
        long seedRows = count(url, "SELECT COUNT(*) FROM prp_wellness_foods");
        Flyway migration = flyway(url);
        assertThat(migration.baseline().successfullyBaselined).isTrue();
        // V8-V20 are pending after V7 baseline, including safe starter-food repair and additive common-food rows.
        assertThat(migration.migrate().migrationsExecuted).isEqualTo(13);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_tasks WHERE title='MIGRATION_SENTINEL'")).isEqualTo(before);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_foods")).isGreaterThanOrEqualTo(seedRows + 140);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_finance_transactions WHERE note='legacy preserved'"))
                .isEqualTo(financeBefore);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_finance_transactions t "
                + "JOIN prp_finance_accounts a ON a.id=t.account_id AND a.user_id=t.user_id "
                + "WHERE t.note='legacy preserved' AND t.amount=25.00 "
                + "AND a.name='LEGACY_FINANCE_WALLET' AND a.opening_balance=0.00")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE() AND table_name LIKE 'prp_ai_%'")).isEqualTo(10);
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() " +
                "AND table_name='prp_ai_conversations' AND column_name IN ('deleted_at','is_pinned','title_source')"))
            .as("Existing conversation table must never be ALTERed by V18").isZero();
        assertThat(count(url, "SELECT COUNT(*) FROM information_schema.columns WHERE table_schema=DATABASE() " +
                "AND table_name='prp_ai_conversation_meta' AND column_name IN ('deleted_at','is_pinned','title_source')"))
            .isEqualTo(3);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_foods "
                + "WHERE owner_user_id IS NULL AND CAST(name AS BINARY)=CAST(CONVERT(0xE59C9FE8B186 USING utf8mb4) AS BINARY)"))
                .as("legacy global seed name restored").isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_foods "
                + "WHERE owner_user_id IS NULL AND calories_100g=87"
                + " AND CAST(source_note AS BINARY)=CAST(CONVERT(0xE7A4BAE4BE8BE58F82E88083E580BCEFBC8CE697A0E9A29DE5A496E6B2B9E88482 USING utf8mb4) AS BINARY)"))
                .as("legacy global seed source note restored").isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_meal_items "
                + "WHERE CAST(food_name AS BINARY)=CAST(CONVERT(0xE59C9FE8B186 USING utf8mb4) AS BINARY) "
                + "AND meal_id IN (SELECT id FROM prp_wellness_meals "
                + "WHERE note='MIGRATION_TEXT_SENTINEL')")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_foods "
                + "WHERE owner_user_id IS NOT NULL "
                + "AND CAST(name AS BINARY)=CAST(CONVERT(CONVERT(0xE59C9FE8B186 USING latin1) USING utf8mb4) AS BINARY)")).isEqualTo(1);
        assertThat(count(url, "SELECT COUNT(*) FROM prp_wellness_meals "
                + "WHERE note='MIGRATION_TEXT_SENTINEL'")).isEqualTo(1);
        assertThat(migration.migrate().migrationsExecuted).isZero();
        assertThat(migration.validateWithResult().validationSuccessful).isTrue();
        assertThat(count(url, "SELECT COUNT(*) FROM flyway_schema_history WHERE success=1")).isEqualTo(14);
    }
}
