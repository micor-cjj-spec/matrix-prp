package com.matrix.prp.ai;

import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;

class AiMonthlyQuotaTests {
    @Test void userCanUseTwoThousandCallsWithoutHittingAnUnchangedTokenOrGlobalCap() {
        var usage=new InMemoryAiStore();
        long user=919919L;
        String month="2099-12";
        for(int i=0;i<2000;i++)
            usage.reserve(user,month,5000,2000,12000000L,10000,60000000L);
        assertThat(usage.usage(user,month).requests()).isEqualTo(2000);
        assertThat(usage.usage(user,month).reservedTokens()).isEqualTo(10000000L);
        assertThatThrownBy(()->usage.reserve(user,month,5000,2000,12000000L,10000,60000000L))
            .isInstanceOf(ResponseStatusException.class)
            .hasMessageContaining("Monthly AI allowance reached");
    }

    @Test void serverNeverLabelsProviderRateLimitAsPrpMonthlyQuota() {
        assertThat(AiService.quotaSource(new ResponseStatusException(
            HttpStatus.TOO_MANY_REQUESTS,"AI provider request failed (429)")))
            .isEqualTo("provider");
        assertThat(AiService.quotaSource(new ResponseStatusException(
            HttpStatus.TOO_MANY_REQUESTS,"AI provider request failed")))
            .isEqualTo("provider");
        assertThat(AiService.quotaSource(new ResponseStatusException(
            HttpStatus.TOO_MANY_REQUESTS,"Monthly AI allowance reached")))
            .isEqualTo("prp");
        assertThat(AiService.quotaSource(new ResponseStatusException(
            HttpStatus.SERVICE_UNAVAILABLE,"service busy")))
            .isEqualTo("none");
    }
}
