package com.matrix.prp.practice;

import com.matrix.prp.common.api.ApiResponse;
import com.matrix.prp.practice.PracticeModels.*;
import java.util.List;
import org.springframework.context.annotation.Profile;
import org.springframework.web.bind.annotation.*;

@RestController
@Profile("!test")
@RequestMapping("/api/practice")
public class PracticeController {
    private final PracticeService practice;
    private final PracticeAiService ai;

    public PracticeController(PracticeService practice, PracticeAiService ai) {
        this.practice = practice;
        this.ai = ai;
    }

    @GetMapping("/subjects")
    public ApiResponse<List<Subject>> subjects() { return ApiResponse.success(practice.subjects()); }
    @PostMapping("/subjects")
    public ApiResponse<Subject> createSubject(@RequestBody SubjectForm request) {
        return ApiResponse.success(practice.createSubject(request));
    }
    @PutMapping("/subjects/{id}")
    public ApiResponse<Void> updateSubject(@PathVariable long id, @RequestBody SubjectForm request) {
        practice.updateSubject(id, request); return ApiResponse.success();
    }
    @DeleteMapping("/subjects/{id}")
    public ApiResponse<Void> deleteSubject(@PathVariable long id) {
        practice.deleteSubject(id); return ApiResponse.success();
    }

    @GetMapping("/subjects/{subjectId}/banks")
    public ApiResponse<List<Bank>> banks(@PathVariable long subjectId) {
        return ApiResponse.success(practice.banks(subjectId));
    }
    @PostMapping("/banks")
    public ApiResponse<Bank> createBank(@RequestBody BankForm request) {
        return ApiResponse.success(practice.createBank(request));
    }
    @PutMapping("/banks/{id}")
    public ApiResponse<Void> updateBank(@PathVariable long id, @RequestBody BankForm request) {
        practice.updateBank(id, request); return ApiResponse.success();
    }
    @PutMapping("/banks/{id}/status")
    public ApiResponse<Void> bankStatus(@PathVariable long id, @RequestParam String status) {
        practice.setBankStatus(id, status); return ApiResponse.success();
    }
    @DeleteMapping("/banks/{id}")
    public ApiResponse<Void> deleteBank(@PathVariable long id) {
        practice.deleteBank(id); return ApiResponse.success();
    }

    @GetMapping("/banks/{bankId}/questions")
    public ApiResponse<List<Question>> questions(@PathVariable long bankId) {
        return ApiResponse.success(practice.questions(bankId));
    }
    @PostMapping("/banks/{bankId}/questions")
    public ApiResponse<Question> createQuestion(@PathVariable long bankId, @RequestBody QuestionForm request) {
        return ApiResponse.success(practice.createQuestion(bankId, request));
    }
    @PutMapping("/questions/{id}")
    public ApiResponse<Void> updateQuestion(@PathVariable long id, @RequestBody QuestionForm request) {
        practice.updateQuestion(id, request); return ApiResponse.success();
    }
    @PutMapping("/questions/{id}/status")
    public ApiResponse<Void> questionStatus(@PathVariable long id, @RequestParam String status) {
        practice.setQuestionStatus(id, status); return ApiResponse.success();
    }
    @DeleteMapping("/questions/{id}")
    public ApiResponse<Void> deleteQuestion(@PathVariable long id) {
        practice.deleteQuestion(id); return ApiResponse.success();
    }

    @PostMapping("/imports/preview")
    public ApiResponse<ImportPreview> preview(@RequestBody ImportForm request) {
        return ApiResponse.success(practice.preview(request));
    }
    @PostMapping("/banks/{bankId}/imports")
    public ApiResponse<ImportResult> importQuestions(@PathVariable long bankId, @RequestBody ImportForm request) {
        return ApiResponse.success(practice.importQuestions(bankId, request));
    }

    @GetMapping("/banks/{bankId}/play")
    public ApiResponse<List<QuestionPublic>> play(@PathVariable long bankId) {
        return ApiResponse.success(practice.playable(bankId));
    }
    @PostMapping("/questions/{id}/check")
    public ApiResponse<GradeResult> check(@PathVariable long id, @RequestBody AnswerForm request) {
        return ApiResponse.success(practice.grade(id, request));
    }
    @GetMapping("/statistics")
    public ApiResponse<Statistics> statistics() {
        return ApiResponse.success(practice.statistics());
    }
    @GetMapping("/wrong-questions")
    public ApiResponse<List<QuestionPublic>> wrong() {
        return ApiResponse.success(practice.wrongQuestions());
    }

    @PostMapping("/banks/{bankId}/ai/generate")
    public ApiResponse<ImportResult> generate(@PathVariable long bankId,
                                               @RequestBody AiGenerationForm request) {
        return ApiResponse.success(ai.generate(bankId, request));
    }
    @PostMapping("/questions/{id}/ai/explain")
    public ApiResponse<AiExplanation> explain(@PathVariable long id,
                                               @RequestBody AiExplanationForm request) {
        return ApiResponse.success(ai.explain(id, request));
    }
    public record AiGenerationForm(String topic, String difficulty, int count) {}
    public record AiExplanationForm(String question) {}
    public record AiExplanation(String content) {}
}