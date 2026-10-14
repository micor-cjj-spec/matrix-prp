package com.matrix.prp;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import com.matrix.prp.video.ByteRanges;
import com.matrix.prp.video.MediaTicketService;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

class VideoSecurityPrimitivesTests {
    @Test
    void supportsCompleteOpenAndSuffixRanges() {
        assertThat(ByteRanges.parse(null, 100)).isEqualTo(new ByteRanges.Span(0, 99));
        assertThat(ByteRanges.parse("bytes=10-19", 100)).isEqualTo(new ByteRanges.Span(10, 19));
        assertThat(ByteRanges.parse("bytes=98-", 100)).isEqualTo(new ByteRanges.Span(98, 99));
        assertThat(ByteRanges.parse("bytes=-10", 100)).isEqualTo(new ByteRanges.Span(90, 99));
        assertThatThrownBy(() -> ByteRanges.parse("bytes=200-", 100)).isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> ByteRanges.parse("bytes=0-1,3-5", 100)).isInstanceOf(IllegalArgumentException.class);
    }

    @Test
    void ticketsAreBoundToAssetAndTamperingIsRejected() {
        MediaTicketService tickets = new MediaTicketService("0123456789-secret-signing-key-for-tests-abc");
        String valid = tickets.issue(9, 2).value();
        assertThat(tickets.verify(valid, 9)).isEqualTo(2L);
        assertThatThrownBy(() -> tickets.verify(valid, 10)).isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> tickets.verify(valid + "bad", 9)).isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
    }
    @Test
    void malformedAndCrossAssetPlaybackTicketsFailClosed() {
        MediaTicketService tickets = new MediaTicketService("0123456789-secret-signing-key-for-tests-abc");
        String ticket = tickets.issue(45, 8).value();

        assertThatThrownBy(() -> tickets.verify(ticket, 46))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> tickets.verify("", 45))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> tickets.verify("malformed", 45))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> tickets.verify(ticket + ".extra", 45))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
        assertThatThrownBy(() -> tickets.verify(ticket.substring(0, ticket.length() - 1) + "!", 45))
                .isInstanceOf(ResponseStatusException.class)
                .satisfies(ex -> assertThat(((ResponseStatusException) ex).getStatusCode())
                        .isEqualTo(HttpStatus.FORBIDDEN));
    }

    @Test
    void shortSigningKeysAreRejectedAtStartup() {
        assertThatThrownBy(() -> new MediaTicketService("short"))
                .isInstanceOf(IllegalArgumentException.class);
    }

}
