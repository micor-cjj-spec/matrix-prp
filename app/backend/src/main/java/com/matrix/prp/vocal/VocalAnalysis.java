package com.matrix.prp.vocal;

import java.util.ArrayList;
import java.util.Collections;
import java.util.List;
import java.util.Map;

/** Device-observed pitch telemetry. Not an independent server-side audio analysis. */
public final class VocalAnalysis {
    private VocalAnalysis() {}
    public record Point(double time, double hz) {}
    public record Summary(int voicedSamples, Double medianHz, Double stabilityCents,
                          Double targetHitPercent, String guidance) {}

    public static Summary summarize(List<Point> points, Double target) {
        if (points == null || points.size() > 1800)
            throw new IllegalArgumentException("Too many pitch observations");
        List<Double> frequencies = new ArrayList<>();
        int targetHit = 0;
        double lastTime = -1;
        for (Point p : points) {
            if (!Double.isFinite(p.time()) || p.time() < 0 || p.time() > 600
                || p.time() < lastTime || !Double.isFinite(p.hz())
                || p.hz() < 65 || p.hz() > 1500)
                throw new IllegalArgumentException("Invalid pitch observation");
            lastTime = p.time();
            frequencies.add(p.hz());
            if (target != null && Math.abs(1200 * Math.log(p.hz() / target) / Math.log(2)) <= 50)
                targetHit++;
        }
        if (target != null && (!Double.isFinite(target) || target < 65 || target > 1500))
            throw new IllegalArgumentException("Invalid reference pitch");
        if (frequencies.isEmpty())
            return new Summary(0, null, null, null, "未检测到稳定的单音或有效音高样本；可能是输入音量低、伴奏、气声或分析器未获取到有效数据。这不等于录音文件没有声音，请先试听录音再决定是否重录。");
        Collections.sort(frequencies);
        double median = frequencies.get(frequencies.size() / 2);
        List<Double> deviations = new ArrayList<>();
        for (double hz : frequencies)
            deviations.add(Math.abs(1200 * Math.log(hz / median) / Math.log(2)));
        Collections.sort(deviations);
        // MAD measures overall pitch spread, not singing proficiency; melody changes can increase it.
        double spread = deviations.get(deviations.size() / 2);
        Double hit = target == null ? null : Math.round(targetHit * 1000d / frequencies.size()) / 10d;
        String advice = hit == null
            ? "已保存音高分布。没有指定参考音，不能据此评价音准。"
            : hit >= 70 ? "参考音附近的命中较多，尝试保持轻松、连贯的发声。"
                        : "参考音附近的命中较少，可降低速度，先短句模唱，再逐渐连接。";
        return new Summary(frequencies.size(), Math.round(median * 10d) / 10d,
            Math.round(spread * 10d) / 10d, hit, advice);
    }

    public static List<Map<String, Object>> exercises() {
        return List.of(
            Map.of("code","hum","name","哼鸣热身","description","轻柔哼鸣，不追求音量或极限音高","minutes",3,"targetHz",0),
            Map.of("code","lip","name","唇颤音","description","放松双唇，注意舒适和连续性","minutes",3,"targetHz",0),
            Map.of("code","a4","name","A4 单音模唱","description","跟随 440Hz 参考音轻声模唱","minutes",4,"targetHz",440),
            Map.of("code","phrase","name","连音与乐句","description","一口气轻声连接音节，不必逐字断开","minutes",5,"targetHz",0)
        );
    }

    public static Double targetFor(String code) {
        if (List.of("hum","lip","phrase").contains(code)) return null;
        if ("a4".equals(code)) return 440d;
        throw new IllegalArgumentException("Unknown exercise");
    }
}
