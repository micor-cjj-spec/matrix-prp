package io.micor.prp.health;
import jakarta.ws.rs.core.MultivaluedHashMap;
import org.junit.jupiter.api.Test;
import static org.junit.jupiter.api.Assertions.*;

class HealthPolicyTest {
    MultivaluedHashMap<String,String> valid() {
        var p=new MultivaluedHashMap<String,String>();
        p.putSingle("client_id",HealthPolicyFactory.CLIENT);p.putSingle("redirect_uri",HealthPolicyFactory.REDIRECT);
        p.putSingle("resource",HealthPolicyFactory.RESOURCE);p.putSingle("response_type","code");
        p.putSingle("code_challenge_method","S256");p.putSingle("code_challenge","A".repeat(43));
        p.putSingle("scope",String.join(" ",HealthPolicyFactory.SCOPES));return p;
    }
    @Test void exactHealthAuthorizationIsAccepted() {
        assertDoesNotThrow(()->HealthPolicyFactory.authorization(valid()));
    }
    @Test void unrelatedOfflineAndDuplicateScopesAreRefused() {
        for(String scope:new String[]{"offline_access","prp.tasks.read","prp.finance.read","prp.write.create","*","prp.wellness.read prp.wellness.read"," prp.wellness.read"}) {
            var p=valid();p.putSingle("scope",scope);assertThrows(Exception.class,()->HealthPolicyFactory.authorization(p));
        }
    }
    @Test void redirectsClientResourceAndPkceCannotBeRelaxed() {
        String[][] cases={{"redirect_uri",HealthPolicyFactory.REDIRECT+"/"},{"client_id",HealthPolicyFactory.CLIENT+"?x=1"},
            {"resource","https://prp-test.micor.top/api/mcp"},{"response_type","token"},
            {"code_challenge_method","plain"},{"code_challenge","short"}};
        for(var pair:cases){var p=valid();p.putSingle(pair[0],pair[1]);assertThrows(Exception.class,()->HealthPolicyFactory.authorization(p));}
        var duplicate=valid();duplicate.add("resource",HealthPolicyFactory.RESOURCE);assertThrows(Exception.class,()->HealthPolicyFactory.authorization(duplicate));
    }
    @Test void codeAndRefreshRequireAnExplicitExactResource() {
        var p=valid();assertDoesNotThrow(()->HealthPolicyFactory.token(p));
        p.remove("scope");assertDoesNotThrow(()->HealthPolicyFactory.token(p));
        p.remove("resource");assertThrows(Exception.class,()->HealthPolicyFactory.token(p));
        p.putSingle("resource","");assertThrows(Exception.class,()->HealthPolicyFactory.token(p));
    }
}
