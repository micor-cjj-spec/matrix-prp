package io.micor.prp.health;
public final class HealthOAuthDiscoveryFactory extends HealthDiscoveryFactory {
    public String getId(){return "prp-production-health-oauth-discovery";}
    public String getAlias(){return "oauth-authorization-server";}
    public boolean isAvailableViaServerMetadata(){return true;}
}
