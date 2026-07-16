package com.matrix.prp.modules.service;

import com.matrix.prp.modules.model.ModuleItem;
import java.util.List;
import org.springframework.stereotype.Service;

@Service
public class ModuleService {

    private static final String FEATURE = "feature";
    private static final String DOMAIN = "domain";

    private final List<ModuleItem> modules = List.of(
            new ModuleItem("records", "Records", "沉淀学习、生活、工作和兴趣记录", FEATURE, 10, true),
            new ModuleItem("tasks", "Tasks", "管理今日任务和近期计划", FEATURE, 20, true),
            new ModuleItem("finance", "Finance", "记录收入支出并查看月度概览", FEATURE, 30, true),
            new ModuleItem("reviews", "Reviews", "沉淀周、月和模块复盘", FEATURE, 40, true),
            new ModuleItem("knowledge", "Knowledge", "浏览现有 Markdown 知识库", FEATURE, 50, true),
            new ModuleItem("life", "生活", "日常、习惯、健康和家庭事务", DOMAIN, 110, true),
            new ModuleItem("learning", "学习", "课程、考试、证书和成长记录", DOMAIN, 120, true),
            new ModuleItem("work", "工作", "项目、会议、任务和职业成长", DOMAIN, 130, true),
            new ModuleItem("interests", "兴趣", "阅读、旅行、音乐和长期爱好", DOMAIN, 140, true),
            new ModuleItem("social", "社交", "联系人、互动和关系维护", DOMAIN, 150, true),
            new ModuleItem("finance", "财务", "收入、支出、账单和财务复盘", DOMAIN, 160, true));

    public List<ModuleItem> list() {
        return modules;
    }

    public List<ModuleItem> listFeatures() {
        return listByType(FEATURE);
    }

    public List<ModuleItem> listDomains() {
        return listByType(DOMAIN);
    }

    private List<ModuleItem> listByType(String type) {
        return modules.stream()
                .filter(module -> type.equals(module.type()))
                .toList();
    }
}
