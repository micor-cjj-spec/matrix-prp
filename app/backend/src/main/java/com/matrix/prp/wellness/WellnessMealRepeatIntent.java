package com.matrix.prp.wellness;

import java.time.LocalDate;
import java.util.ArrayList;
import java.util.LinkedHashSet;
import java.util.List;
import java.util.Optional;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Deterministic, bounded interpretation of an explicitly requested copy of an existing meal.
 * Never infer food ingredients, dates or writes from model-generated text.
 */
final class WellnessMealRepeatIntent {
    record Intent(String mealType, List<LocalDate> targets) {}
    private static final Pattern DATE = Pattern.compile("(?<!\\d)(20\\d{2})-(\\d{2})-(\\d{2})(?!\\d)");
    private static final Pattern LAST_DAYS = Pattern.compile("(?:过去|最近|近)([2-7二两三四五六七])天");
    private WellnessMealRepeatIntent() {}

    static Optional<Intent> parse(String input, LocalDate today) {
        if (input == null || input.isBlank() || input.length() > 1500) return Optional.empty();
        boolean copy = Pattern.compile("一样|也是|同样|相同|复制|照着|照搬|重复|照.+(?:吃|记)|按.+(?:吃|记录)").matcher(input).find();
        if (!copy) return Optional.empty();
        String type;
        if (input.matches("(?s).*(?:早餐|早饭).*")) type = "BREAKFAST";
        else if (input.matches("(?s).*(?:午餐|午饭).*")) type = "LUNCH";
        else if (input.matches("(?s).*(?:晚餐|晚饭).*")) type = "DINNER";
        else if (input.matches("(?s).*加餐.*")) type = "SNACK";
        else return Optional.empty();

        LinkedHashSet<LocalDate> days = new LinkedHashSet<>();
        if (input.contains("前天") || input.contains("前日")) days.add(today.minusDays(2));
        if (input.contains("昨天") || input.contains("昨日")) days.add(today.minusDays(1));

        Matcher count = LAST_DAYS.matcher(input);
        if (count.find()) {
            int n = switch (count.group(1)) {
                case "二", "两" -> 2;
                case "三" -> 3;
                case "四" -> 4;
                case "五" -> 5;
                case "六" -> 6;
                case "七" -> 7;
                default -> Integer.parseInt(count.group(1));
            };
            for (int i = n; i >= 1; i--) days.add(today.minusDays(i));
        }
        Matcher explicit = DATE.matcher(input);
        while (explicit.find()) {
            try {
                days.add(LocalDate.of(Integer.parseInt(explicit.group(1)),
                    Integer.parseInt(explicit.group(2)), Integer.parseInt(explicit.group(3))));
            } catch (RuntimeException ignored) { return Optional.empty(); }
        }

        if (days.isEmpty() || days.size() > 7) return Optional.empty();
        ArrayList<LocalDate> sorted = new ArrayList<>(days);
        sorted.sort(LocalDate::compareTo);
        // Never copy to today or a future date, and never more than two years back.
        if (sorted.stream().anyMatch(day -> !day.isBefore(today) || day.isBefore(today.minusYears(2))))
            return Optional.empty();
        return Optional.of(new Intent(type, List.copyOf(sorted)));
    }
}
