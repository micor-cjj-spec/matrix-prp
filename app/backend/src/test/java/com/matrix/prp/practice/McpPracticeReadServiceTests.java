package com.matrix.prp.practice;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.practice.PracticeModels.*;
import java.util.List;
import org.junit.jupiter.api.*;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;
import static org.mockito.Mockito.*;

class McpPracticeReadServiceTests {
    final JdbcTemplate jdbc=mock(JdbcTemplate.class);
    final PracticeService practice=new PracticeService(jdbc,new ObjectMapper());

    void user(long owner){
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(owner,"synthetic","Synthetic"),null,List.of()));
    }
    @AfterEach void clear(){SecurityContextHolder.clearContext();}

    @Test void subjectsAndWrongQuestionsAreSqlBoundedAndOwnerScoped(){
        user(77);
        practice.subjectsLimited(12);
        practice.wrongQuestionsLimited(5);
        verify(jdbc).query(contains("FROM prp_practice_subjects WHERE user_id=? ORDER BY id LIMIT 12"),
            any(RowMapper.class),eq(77L));
        verify(jdbc).query(contains("ORDER BY a.created_at DESC LIMIT 5"),
            any(RowMapper.class),eq(77L),eq(77L),eq(77L));
        user(88);
        practice.subjectsLimited(1);
        verify(jdbc).query(contains("LIMIT 1"),any(RowMapper.class),eq(88L));
    }

    @Test void inaccessibleSubjectCannotEnumerateAnotherUsersBanks(){
        user(77);
        assertThatThrownBy(()->practice.banksLimited(98,30))
            .isInstanceOf(ResponseStatusException.class)
            .satisfies(x->assertThat(((ResponseStatusException)x).getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND));
        verify(jdbc).queryForObject(contains("prp_practice_subjects WHERE id=? AND user_id=?"),
            eq(Long.class),eq(98L),eq(77L));
        verify(jdbc,never()).query(startsWith("SELECT * FROM prp_practice_banks"),
            any(RowMapper.class),anyLong(),anyLong());
    }

    @Test void unsafeLimitsAreRejectedBeforeAnyQuery(){
        user(77);
        assertThatThrownBy(()->practice.subjectsLimited(51)).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(()->practice.banksLimited(98,0)).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(()->practice.playableLimited(98,101)).isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(()->practice.wrongQuestionsLimited(-1)).isInstanceOf(ResponseStatusException.class);
        verifyNoInteractions(jdbc);
    }

    @Test void statisticsUseOwnerIdAndStayAggregated(){
        user(77);
        when(jdbc.query(startsWith("SELECT COUNT(*) AS total"),
            any(RowMapper.class),eq(77L))).thenReturn(List.of(new Statistics(9,6,3)));
        assertThat(practice.statistics()).isEqualTo(new Statistics(9,6,3));
        verify(jdbc).query(startsWith("SELECT COUNT(*) AS total"),
            any(RowMapper.class),eq(77L));
    }
}
