package com.matrix.prp.vocal;

import java.util.List;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class VocalAnalysisTests {
    @Test void targetHitAndMedian() {
        var s=VocalAnalysis.summarize(List.of(
            new VocalAnalysis.Point(0,440),new VocalAnalysis.Point(.1,444),
            new VocalAnalysis.Point(.2,438)),440d);
        assertThat(s.voicedSamples()).isEqualTo(3);
        assertThat(s.targetHitPercent()).isEqualTo(100);
        assertThat(s.medianHz()).isEqualTo(440);
    }
    @Test void withoutReferenceDoesNotInventPitchAccuracy() {
        assertThat(VocalAnalysis.summarize(List.of(new VocalAnalysis.Point(1,200)),null)
            .targetHitPercent()).isNull();
        assertThat(VocalAnalysis.summarize(List.of(),440d).targetHitPercent()).isNull();
    }
    @Test void rejectsInvalidAndOversizedTelemetry() {
        assertThatThrownBy(()->VocalAnalysis.summarize(
            List.of(new VocalAnalysis.Point(0,440),new VocalAnalysis.Point(-1,450)),440d))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->VocalAnalysis.summarize(
            List.of(new VocalAnalysis.Point(0,Double.NaN)),null))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(()->VocalAnalysis.targetFor("unknown"))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
