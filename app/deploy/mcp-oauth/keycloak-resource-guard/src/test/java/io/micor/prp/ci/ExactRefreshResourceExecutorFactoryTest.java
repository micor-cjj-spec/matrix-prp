package io.micor.prp.ci;

import jakarta.ws.rs.core.MultivaluedHashMap;
import jakarta.ws.rs.core.MultivaluedMap;
import org.junit.jupiter.api.Test;
import org.keycloak.models.ClientModel;
import org.keycloak.services.clientpolicy.ClientPolicyException;
import org.keycloak.services.clientpolicy.context.TokenRefreshContext;

import static org.junit.jupiter.api.Assertions.*;
import static org.mockito.Mockito.*;

class ExactRefreshResourceExecutorFactoryTest {
    private static final String CLIENT = "https://chatgpt.com/oauth/client.json";
    private static final String RESOURCE = "https://prp-test.micor.top/api/mcp";

    private ExactRefreshResourceExecutorFactory.Configuration config() {
        var c = new ExactRefreshResourceExecutorFactory.Configuration();
        c.setTargetClientId(CLIENT);
        c.setAllowedResource(RESOURCE);
        return c;
    }

    private TokenRefreshContext context(String clientId, String... resources) {
        ClientModel model = mock(ClientModel.class);
        when(model.getClientId()).thenReturn(clientId);
        MultivaluedMap<String, String> form = new MultivaluedHashMap<>();
        if (resources != null) {
            for (String resource : resources) {
                form.add("resource", resource);
            }
        }
        return new TokenRefreshContext(form, model, "openid offline_access prp.tasks.read");
    }

    private ExactRefreshResourceExecutorFactory.ExactRefreshResourceExecutor executor(
            ExactRefreshResourceExecutorFactory.Configuration c) {
        var e = new ExactRefreshResourceExecutorFactory.ExactRefreshResourceExecutor();
        e.setupConfiguration(c);
        assertEquals(ExactRefreshResourceExecutorFactory.Configuration.class,
                     e.getExecutorConfigurationClass());
        return e;
    }

    @Test
    void acceptsOnlyExactSingleResourceForTargetClient() {
        assertDoesNotThrow(() -> executor(config()).executeOnEvent(context(CLIENT, RESOURCE)));
    }

    @Test
    void rejectForeignEvenWhenCanonicalResourceAlsoPresent() {
        assertThrows(ClientPolicyException.class, () ->
            executor(config()).executeOnEvent(context(CLIENT, RESOURCE,
                "https://unrelated.example.test/api/mcp")));
    }

    @Test
    void rejectDuplicateIdenticalValuesAndEmptyResource() {
        var guard = executor(config());
        assertThrows(ClientPolicyException.class, () ->
            guard.executeOnEvent(context(CLIENT, RESOURCE, RESOURCE)));
        assertThrows(ClientPolicyException.class, () ->
            guard.executeOnEvent(context(CLIENT, "")));
    }

    @Test
    void rejectMissingResourceForTargetClient() {
        assertThrows(ClientPolicyException.class, () ->
            executor(config()).executeOnEvent(context(CLIENT)));
    }

    @Test
    void leaveOtherClientsUntouchedWithValidConfiguration() {
        var guard = executor(config());
        assertDoesNotThrow(() -> guard.executeOnEvent(context(
            "ci-unrelated-client", "https://unrelated.example.test/api/mcp")));
    }

    @Test
    void rejectMissingAndMalformedConfiguration() {
        assertThrows(ClientPolicyException.class, () ->
            executor(null).executeOnEvent(context(CLIENT, RESOURCE)));
        var missing = config();
        missing.setTargetClientId(null);
        assertFalse(missing.validateConfig());
        assertThrows(ClientPolicyException.class, () ->
            executor(missing).executeOnEvent(context(CLIENT, RESOURCE)));
        var unsafe = config();
        unsafe.setAllowedResource("http://localhost/api/mcp");
        assertFalse(unsafe.validateConfig());
        assertThrows(ClientPolicyException.class, () ->
            executor(unsafe).executeOnEvent(context("ci-unrelated-client", RESOURCE)));
    }

    @Test
    void validateHostResourceShapeAndExactClientName() {
        var c = config();
        assertTrue(c.validateConfig());
        for (String resource : new String[] {
            "http://prp-test.micor.top/api/mcp",
            "https://prp-test.micor.top/api/mcp?token=1",
            "https://user@prp-test.micor.top/api/mcp",
            "https://prp-test.micor.top/api/mcp#fragment",
            "https://prp-test.micor.top/api/mcp/",
            "https://prp-test.micor.top:8443/api/mcp",
            "https://*.micor.top/api/mcp",
            "https://prp-test.micor.top/%61pi/mcp",
            ""
        }) {
            c.setAllowedResource(resource);
            assertFalse(c.validateConfig(), "Rejected invalid resource");
        }
        c.setAllowedResource(RESOURCE);
        c.setTargetClientId("ci-*");
        assertFalse(c.validateConfig());
        c.setTargetClientId(CLIENT);
        assertTrue(c.validateConfig());
    }
}
