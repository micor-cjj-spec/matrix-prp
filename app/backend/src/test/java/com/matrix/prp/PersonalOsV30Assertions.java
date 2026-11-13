package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;
import java.sql.SQLException;
import java.sql.Statement;

/**
 * Synthetic JDBC evidence for V30 on the existing disposable CI-only MySQL.
 * No production connection, real user rows, or non-rollback data mutations.
 */
final class PersonalOsV30Assertions {
    private PersonalOsV30Assertions() {}

    private static final String CI_URL =
        "jdbc:mysql://127.0.0.1:3306/matrix_prp_flyway?useSSL=false";

    static void verify(String url, String user, String password) throws SQLException {
        if (!CI_URL.equals(url) || !"true".equals(System.getenv("GITHUB_ACTIONS"))
                || !"Linux".equals(System.getenv("RUNNER_OS"))
                || !"matrix_prp".equals(user)
                || !"ci-app-password".equals(password)) {
            throw new SecurityException("DISPOSABLE_PERSONAL_OS_SCHEMA_TEST_ONLY");
        }

        try (Connection c = DriverManager.getConnection(url, user, password)) {
            assertThat(count(c,
                "SELECT COUNT(*) FROM flyway_schema_history WHERE version='30' " +
                "AND script='V30__personal_os_goals_and_assertions.sql' AND success=1"))
                .isEqualTo(1);
            assertThat(count(c,
                "SELECT COUNT(*) FROM information_schema.tables WHERE table_schema=DATABASE()" +
                " AND table_name IN ('prp_goals','prp_personal_assertions')"))
                .isEqualTo(2);
            assertThat(count(c,"SELECT COUNT(*) FROM prp_goals")).isZero();
            assertThat(count(c,"SELECT COUNT(*) FROM prp_personal_assertions")).isZero();

            c.setAutoCommit(false);
            try {
                insert(c, "INSERT INTO prp_users (id,username,display_name,password_hash) " +
                    "VALUES (970001,'personal_os_ci_a','Synthetic A','CI_ONLY') ");
                insert(c, "INSERT INTO prp_users (id,username,display_name,password_hash) " +
                    "VALUES (970002,'personal_os_ci_b','Synthetic B','CI_ONLY') ");
                long goal = insertKey(c, "INSERT INTO prp_goals " +
                    "(user_id,title,domain,request_key,created_at,updated_at) " +
                    "VALUES (970001,'Synthetic goal','career','goal-key',NOW(6),NOW(6))");
                assertThat(goal).isPositive();
                long a = insertKey(c,"INSERT INTO prp_personal_assertions " +
                    "(user_id,subject_type,subject_ref,predicate,object_type,object_ref," +
                    "origin,status,request_key,created_at,updated_at) " +
                    "VALUES (970001,'PERSON','970001','PURSUES','GOAL',?," +
                    "'USER_CONFIRMED','CONFIRMED','assert-a',NOW(6),NOW(6))",
                    Long.toString(goal));
                assertThat(a).isPositive();

                assertThatThrownBy(() -> insert(c,
                    "INSERT INTO prp_goals (user_id,title,domain,created_at,updated_at) " +
                    "VALUES (979999,'Orphan','career',NOW(6),NOW(6))"))
                    .isInstanceOf(SQLException.class);
                assertThatThrownBy(() -> insert(c,
                    "INSERT INTO prp_goals " +
                    "(user_id,title,domain,request_key,created_at,updated_at) " +
                    "VALUES (970001,'Duplicate','career','goal-key',NOW(6),NOW(6))"))
                    .isInstanceOf(SQLException.class);
                assertThatThrownBy(() -> insert(c,
                    "INSERT INTO prp_personal_assertions " +
                    "(user_id,subject_type,subject_ref,predicate,object_type,object_ref," +
                    "origin,status,supersedes_id,created_at,updated_at) " +
                    "VALUES (970002,'PERSON','970002','PURSUES','GOAL',?," +
                    "'AI_CANDIDATE','PENDING',?,NOW(6),NOW(6))",
                    Long.toString(goal), a))
                    .as("a second owner cannot supersede the first owner's assertion")
                    .isInstanceOf(SQLException.class);
                assertThat(count(c,"SELECT COUNT(*) FROM prp_personal_assertions " +
                    "WHERE user_id=970001")).isEqualTo(1);
            } finally {
                c.rollback();
                c.setAutoCommit(true);
            }
            assertThat(count(c,"SELECT COUNT(*) FROM prp_goals")).isZero();
            assertThat(count(c,"SELECT COUNT(*) FROM prp_personal_assertions")).isZero();
        }
    }

    private static long count(Connection c, String sql) throws SQLException {
        try (Statement st=c.createStatement(); ResultSet rs=st.executeQuery(sql)) {
            assertThat(rs.next()).isTrue();
            return rs.getLong(1);
        }
    }

    private static void insert(Connection c, String sql, Object... params) throws SQLException {
        try (PreparedStatement st=c.prepareStatement(sql)) {
            for (int i=0;i<params.length;i++) st.setObject(i+1,params[i]);
            assertThat(st.executeUpdate()).isEqualTo(1);
        }
    }

    private static long insertKey(Connection c,String sql,Object... params) throws SQLException {
        try (PreparedStatement st=c.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS)) {
            for (int i=0;i<params.length;i++) st.setObject(i+1,params[i]);
            assertThat(st.executeUpdate()).isEqualTo(1);
            try (ResultSet keys=st.getGeneratedKeys()) {
                assertThat(keys.next()).isTrue();
                return keys.getLong(1);
            }
        }
    }
}
