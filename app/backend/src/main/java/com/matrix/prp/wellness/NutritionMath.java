package com.matrix.prp.wellness;

import java.math.BigDecimal;
import java.math.RoundingMode;

public final class NutritionMath {
    private NutritionMath() {}
    public static BigDecimal portion(BigDecimal per100g, BigDecimal grams) {
        if (per100g == null || grams == null || per100g.signum() < 0
                || grams.signum() <= 0 || grams.compareTo(new BigDecimal("10000")) > 0) {
            throw new IllegalArgumentException("Invalid food nutrition or portion");
        }
        return per100g.multiply(grams).divide(new BigDecimal("100"), 2, RoundingMode.HALF_UP);
    }
}
