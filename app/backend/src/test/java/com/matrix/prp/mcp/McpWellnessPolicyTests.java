package com.matrix.prp.mcp;

import java.util.*;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class McpWellnessPolicyTests {
    static final String SCOPES=String.join(",",McpProductionWellnessGuard.SCOPES);
    @Test void healthManifestCannotExposeTaskFinanceOrGenericWriteTools() {
        assertThat(McpToolConfiguration.exposedNames(SCOPES,true)).containsExactlyInAnyOrder(
            "prp_wellness_daily","prp_wellness_list","prp_wellness_get","prp_wellness_foods",
            "prp_prepare_wellness_create","prp_prepare_wellness_update","prp_prepare_wellness_delete",
            "prp_wellness_draft_status","prp_confirm_wellness_draft");
    }
    @Test void healthWriteRequiresIndependentWriteFlag() {
        assertThatThrownBy(()->McpToolConfiguration.exposedNames(SCOPES,false)).isInstanceOf(IllegalArgumentException.class);
        assertThat(McpToolConfiguration.exposedNames("prp.wellness.write.update",true))
            .containsExactly("prp_prepare_wellness_update");
        assertThat(McpDraftService.operationScope("WELLNESS_DELETE")).isEqualTo("prp.wellness.write.delete");
    }
    private void verify(String scopes,String db,String resource,String issuer,String owners,boolean flyway) {
        McpProductionWellnessGuard.verify(true,true,true,flyway,false,scopes,db,resource,issuer,owners);
    }
    @Test void productionHealthContractAcceptsOnlyExplicitReviewedBoundary() {
        verify(SCOPES,"jdbc:mysql://127.0.0.1:3306/matrix_prp?useSSL=false","https://micor.top/api/mcp",
            "https://auth.micor.top/realms/prp-mcp-prod","7",false);
        for(String db:List.of("jdbc:mysql://127.0.0.1/matrix_prp_mcp_stage_v2","jdbc:mysql://remote/matrix_prp",
                "jdbc:mysql://127.0.0.1/matrix_prp?sessionVariables=x"))
            assertThatThrownBy(()->verify(SCOPES,db,"https://micor.top/api/mcp","https://auth.micor.top/realms/prp-mcp-prod","7",false))
                .isInstanceOf(IllegalStateException.class);
        for(String scopes:List.of(SCOPES+",prp.write.create",SCOPES+",prp.tasks.read",SCOPES+",offline_access"))
            assertThatThrownBy(()->verify(scopes,"jdbc:mysql://127.0.0.1/matrix_prp","https://micor.top/api/mcp","https://auth.micor.top/realms/prp-mcp-prod","7",false))
                .isInstanceOf(RuntimeException.class);
        for(String owners:List.of("","0","-1","7,","*"))
            assertThatThrownBy(()->verify(SCOPES,"jdbc:mysql://127.0.0.1/matrix_prp","https://micor.top/api/mcp","https://auth.micor.top/realms/prp-mcp-prod",owners,false))
                .isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->verify(SCOPES,"jdbc:mysql://127.0.0.1/matrix_prp","https://prp-test.micor.top/api/mcp","https://auth-test.micor.top/realms/prp-mcp","7",false)).isInstanceOf(IllegalStateException.class);
        assertThatThrownBy(()->verify(SCOPES,"jdbc:mysql://127.0.0.1/matrix_prp","https://micor.top/api/mcp","https://auth.micor.top/realms/prp-mcp-prod","7",true)).isInstanceOf(IllegalStateException.class);
    }
}
