package com.matrix.prp.ai;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;

import com.fasterxml.jackson.databind.ObjectMapper;
import java.io.BufferedReader;
import java.io.StringReader;
import org.junit.jupiter.api.Test;

class DeepSeekStreamCompletionTests {
    private static final String CHUNK =
        "data: {\"choices\":[{\"delta\":{\"content\":\"partial\"}}]}\n\n";

    private DeepSeekClient.Result parse(String raw) throws Exception {
        return DeepSeekClient.parseStream(new BufferedReader(new StringReader(raw)),
            new ObjectMapper(), part -> {});
    }

    @Test
    void completedStreamIsAccepted() throws Exception {
        DeepSeekClient.Result result = parse(CHUNK + "data: [DONE]\n\n");
        assertThat(result.answer()).isEqualTo("partial");
    }

    @Test
    void truncatedStreamMustNotBeSavedAsSuccess() {
        assertThatThrownBy(() -> parse(CHUNK))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("completion sentinel");
    }

    @Test
    void completionWithoutAnyContentIsRejected() {
        assertThatThrownBy(() -> parse("data: [DONE]\n\n"))
            .isInstanceOf(IllegalStateException.class)
            .hasMessageContaining("empty response");
    }
}
