package com.matrix.prp.ai;

import org.springframework.core.io.buffer.DataBuffer;

/**
 * Bounded raw SSE sentinel observer. DeepSeek's Spring AI 1.1 parser removes
 * [DONE] from the Flux, so only observing the decoded ChatResponse is insufficient.
 * Per-stream instance; never reads prompts, model keys or upstream JSON payloads.
 */
final class DeepSeekStreamCompletionProbe {
    private static final int MAX_LINE_BYTES = 128;
    private final StringBuilder partialLine = new StringBuilder(MAX_LINE_BYTES);
    private final String completionLine;

    DeepSeekStreamCompletionProbe() { this("data: [DONE]"); }

    DeepSeekStreamCompletionProbe(String completionLine) {
        this.completionLine = java.util.Objects.requireNonNull(completionLine);
    }
    private boolean oversizedLine;
    private boolean sawDone;

    /** Does not change the buffer's read position, lifecycle, or contents. */
    void inspect(DataBuffer buffer) {
        int offset = buffer.readPosition();
        int end = offset + buffer.readableByteCount();
        for (int pos = offset; pos < end; pos++) {
            byte value = buffer.getByte(pos);
            if (value == '\n') {
                if (!oversizedLine && partialLine.toString().trim().equals(completionLine))
                    sawDone = true;
                partialLine.setLength(0);
                oversizedLine = false;
                continue;
            }
            if (!oversizedLine) {
                if (partialLine.length() < MAX_LINE_BYTES) {
                    partialLine.append((char) (value & 0xff));
                } else {
                    oversizedLine = true;
                    partialLine.setLength(0);
                }
            }
        }
    }

    boolean isComplete() { return sawDone; }

    void requireDone() {
        if (!sawDone)
            throw new IllegalStateException("AI provider stream ended without completion sentinel");
    }
}
