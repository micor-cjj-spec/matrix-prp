package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.*;

import java.nio.charset.StandardCharsets;
import org.junit.jupiter.api.Test;
import org.springframework.core.io.buffer.DefaultDataBufferFactory;

class DeepSeekStreamCompletionProbeTests {
    private final DefaultDataBufferFactory buffers = new DefaultDataBufferFactory();

    void observe(DeepSeekStreamCompletionProbe probe, String piece) {
        var buffer = buffers.wrap(piece.getBytes(StandardCharsets.UTF_8));
        int readPosition = buffer.readPosition();
        probe.inspect(buffer);
        assertThat(buffer.readPosition()).isEqualTo(readPosition);
    }

    @Test void recognizesSplitSentinelWithCrlf() {
        var probe = new DeepSeekStreamCompletionProbe();
        observe(probe, "data: {\\\"choices\\\":[]}\r\n\r\n");
        observe(probe, "data: [DO");
        assertThat(probe.isComplete()).isFalse();
        observe(probe, "NE]\r\n\r\n");
        assertThat(probe.isComplete()).isTrue();
        probe.requireDone();
    }

    @Test void jsonTextAndQuotedMarkersAreNotCompletion() {
        var probe = new DeepSeekStreamCompletionProbe();
        observe(probe, "data: {\\\"choices\\\":[{\\\"delta\\\":{\\\"content\\\":\\\"data: [DONE]\\\"},\\\"finish_reason\\\":\\\"stop\\\"}]}\n\n");
        assertThatThrownBy(probe::requireDone).isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("completion sentinel");
    }

    @Test void oversizedLineCannotSpoofSseBoundary() {
        var probe = new DeepSeekStreamCompletionProbe();
        observe(probe, "data: " + "A".repeat(5000) + " [DONE]\n");
        assertThat(probe.isComplete()).isFalse();
        observe(probe, "data:[DONE]\n\n");
        assertThatThrownBy(probe::requireDone).isInstanceOf(IllegalStateException.class);
        observe(probe, "data: [DONE]\n\n");
        probe.requireDone();
    }

    @Test void truncatedSentinelWithoutLineTerminatorIsRejected() {
        var probe = new DeepSeekStreamCompletionProbe();
        observe(probe, "data: [DONE]");
        assertThatThrownBy(probe::requireDone).isInstanceOf(IllegalStateException.class);
    }
}
