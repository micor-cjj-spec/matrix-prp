package com.matrix.prp.practice;

import java.util.List;

public final class PracticeModels {
    private PracticeModels() {}

    public record Subject(long id, Long parentId, String name, String description) {}
    public record SubjectForm(Long parentId, String name, String description) {}
    public record Bank(long id, long subjectId, String title, String description,
                       String sourceName, String licenseNote, String status) {}
    public record BankForm(long subjectId, String title, String description,
                           String sourceName, String licenseNote) {}
    public record Option(String key, String text) {}
    public record Question(long id, long bankId, String type, String stem,
                           List<Option> options, List<String> answers, String explanation,
                           String difficulty, String status) {}
    public record QuestionForm(String type, String stem, List<Option> options,
                               List<String> answers, String explanation, String difficulty) {}
    public record QuestionPublic(long id, long bankId, String type, String stem,
                                 List<Option> options, String difficulty) {}
    public record ImportForm(String format, String content, String sourceName) {}
    public record ImportPreview(int total, List<QuestionForm> examples) {}
    public record ImportResult(int imported, int duplicates) {}
    public record AnswerForm(List<String> answers) {}
    public record GradeResult(boolean correct, List<String> correctAnswers, String explanation) {}
    public record Statistics(long attempted, long correct, long wrong) {}
}