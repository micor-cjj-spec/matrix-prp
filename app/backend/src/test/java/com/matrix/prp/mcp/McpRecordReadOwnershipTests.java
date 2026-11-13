package com.matrix.prp.mcp;

import com.matrix.prp.auth.model.UserProfile;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.model.RecordFilter;
import com.matrix.prp.records.repository.InMemoryRecordRepository;
import com.matrix.prp.records.service.RecordService;
import java.time.LocalDate;
import java.util.List;
import org.junit.jupiter.api.AfterEach;
import org.junit.jupiter.api.Test;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import static org.assertj.core.api.Assertions.*;

class McpRecordReadOwnershipTests {
    void user(long id) {
        SecurityContextHolder.getContext().setAuthentication(
            new UsernamePasswordAuthenticationToken(
                new UserProfile(id,"synthetic","Test"),null,List.of()));
    }
    @AfterEach void cleanup() { SecurityContextHolder.clearContext(); }

    @Test void exactOwnerIsolationAndResultCap() {
        var records=new RecordService(new InMemoryRecordRepository());
        user(101);
        for(int i=0;i<25;i++)records.create(new CreateRecordRequest(
            "life","Synthetic record "+i,"Private content",LocalDate.of(2026,11,13),List.of()));
        assertThat(records.listLimited(new RecordFilter("life",null,null,null),20))
            .hasSize(20).allSatisfy(item->assertThat(item.title()).startsWith("Synthetic record"));
        user(102);
        assertThat(records.listLimited(new RecordFilter(null,null,null,null),20)).isEmpty();
        records.create(new CreateRecordRequest("work","Other owner's record","Secret",null,List.of()));
        user(101);
        assertThat(records.listLimited(new RecordFilter("work",null,null,null),20)).isEmpty();
    }

    @Test void limitMustBeWithinSafeBounds() {
        var records=new RecordService(new InMemoryRecordRepository());
        user(101);
        assertThatThrownBy(()->records.listLimited(new RecordFilter(null,null,null,null),0))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->records.listLimited(new RecordFilter(null,null,null,null),101))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
