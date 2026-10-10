package com.matrix.prp.video;

public final class ByteRanges {
    private ByteRanges() { }

    public record Span(long start, long end) {
        public long length() { return end - start + 1; }
    }

    /** Supports a single HTTP Range, including suffix and open-ended ranges. */
    public static Span parse(String header, long size) {
        if (size <= 0) throw new IllegalArgumentException("Empty media");
        if (header == null || header.isBlank()) return new Span(0, size - 1);
        if (!header.startsWith("bytes=") || header.contains(",")) {
            throw new IllegalArgumentException("Only single byte ranges are supported");
        }
        try {
            String range = header.substring(6);
            int dash = range.indexOf('-');
            if (dash < 0) throw new IllegalArgumentException("Invalid Range");
            String startValue = range.substring(0, dash);
            String endValue = range.substring(dash + 1);
            if (startValue.isEmpty()) {
                long suffix = Long.parseLong(endValue);
                if (suffix <= 0) throw new IllegalArgumentException("Invalid suffix");
                return new Span(Math.max(0, size - suffix), size - 1);
            }
            long start = Long.parseLong(startValue);
            long end = endValue.isEmpty() ? size - 1 : Math.min(size - 1, Long.parseLong(endValue));
            if (start < 0 || start >= size || end < start) throw new IllegalArgumentException("Unsatisfiable Range");
            return new Span(start, end);
        } catch (NumberFormatException e) {
            throw new IllegalArgumentException("Invalid Range", e);
        }
    }
}
