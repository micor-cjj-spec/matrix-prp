package com.matrix.prp.mcp;

import org.springframework.http.HttpStatus;
import org.springframework.security.oauth2.jwt.Jwt;
import org.springframework.web.server.ResponseStatusException;

/**
 * Keycloak access tokens normally identify the OAuth client using signed azp.
 * Other compliant issuers may include signed client_id. If both appear they
 * must agree; never use a client ID from tool arguments or unverified headers.
 */
final class McpOAuthClientIdentity {
    private McpOAuthClientIdentity() {}

    static String clientId(Jwt jwt) {
        String clientId = jwt.getClaimAsString("client_id");
        String authorizedParty = jwt.getClaimAsString("azp");
        if (clientId != null && authorizedParty != null && !clientId.equals(authorizedParty)) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
                "Conflicting OAuth client identity claims");
        }
        String selected = clientId != null ? clientId : authorizedParty;
        if (selected == null || !selected.matches("[A-Za-z0-9][A-Za-z0-9._~:/-]{1,127}")) {
            throw new ResponseStatusException(HttpStatus.UNAUTHORIZED,
                "Missing verified OAuth client identity");
        }
        return selected;
    }
}
