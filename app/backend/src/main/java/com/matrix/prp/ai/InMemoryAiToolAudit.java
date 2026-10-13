package com.matrix.prp.ai;

import org.springframework.context.annotation.Profile;
import org.springframework.stereotype.Component;

@Component
@Profile("test")
public class InMemoryAiToolAudit implements AiToolAudit {
    @Override public void record(long userId,String conversationId,String tool,String scope,String status,long elapsedMs) {}
}
