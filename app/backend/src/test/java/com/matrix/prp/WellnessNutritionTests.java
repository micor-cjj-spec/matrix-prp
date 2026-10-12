package com.matrix.prp;

import com.matrix.prp.wellness.NutritionMath;
import java.math.BigDecimal;
import org.junit.jupiter.api.Test;
import static org.assertj.core.api.Assertions.*;

class WellnessNutritionTests {
    @Test void calculatesPortionFromReference100g() {
        assertThat(NutritionMath.portion(new BigDecimal("130"), new BigDecimal("150")))
            .isEqualByComparingTo("195.00");
        assertThat(NutritionMath.portion(new BigDecimal("3.6"), new BigDecimal("80")))
            .isEqualByComparingTo("2.88");
    }
    @Test void rejectsInvalidPortions() {
        assertThatThrownBy(() -> NutritionMath.portion(new BigDecimal("100"), BigDecimal.ZERO))
            .isInstanceOf(IllegalArgumentException.class);
        assertThatThrownBy(() -> NutritionMath.portion(new BigDecimal("-1"), BigDecimal.ONE))
            .isInstanceOf(IllegalArgumentException.class);
    }
}
