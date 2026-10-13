package com.matrix.prp.ai;

/** Stores only operation metadata; private tool results and prompts are not audited here. */
public interface AiToolAudit {
    void record(long userId,String conversationId,String tool,String scope,String status,long elapsedMs);
}
