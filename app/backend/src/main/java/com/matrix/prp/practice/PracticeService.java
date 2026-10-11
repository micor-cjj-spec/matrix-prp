package com.matrix.prp.practice;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.practice.PracticeModels.*;
import java.nio.charset.StandardCharsets;
import java.security.MessageDigest;
import java.security.NoSuchAlgorithmException;
import java.sql.PreparedStatement;
import java.sql.Statement;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.HexFormat;
import java.util.List;
import java.util.Set;
import java.util.function.Function;
import org.springframework.context.annotation.Profile;
import org.springframework.dao.DuplicateKeyException;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.jdbc.core.RowMapper;
import org.springframework.jdbc.support.GeneratedKeyHolder;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

@Service
@Profile("!test")
public class PracticeService {
    private final JdbcTemplate jdbc;
    private ObjectMapper json;
    public PracticeService(JdbcTemplate jdbc, ObjectMapper json) {
        this.jdbc = jdbc;
        this.json = json;
    }

    private String required(String value, int max, String field) {
        if (value == null || value.isBlank() || value.trim().length() > max)
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, field + " must be between 1 and " + max + " chars");
        return value.trim();
    }
    private String optional(String value, int max, String field) {
        if (value == null) return "";
        if (value.length() > max) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, field + " too long");
        return value.trim();
    }
    private void ensure(boolean condition, String reason) {
        if (!condition) throw new ResponseStatusException(HttpStatus.BAD_REQUEST, reason);
    }
    private long insert(String sql, Object... args) {
        var holder = new GeneratedKeyHolder();
        jdbc.update(connection -> {
            PreparedStatement statement = connection.prepareStatement(sql, Statement.RETURN_GENERATED_KEYS);
            for (int i = 0; i < args.length; i++) statement.setObject(i + 1, args[i]);
            return statement;
        }, holder);
        return holder.getKey().longValue();
    }
    private long count(String sql, Object... args) {
        Long result = jdbc.queryForObject(sql, Long.class, args);
        return result == null ? 0 : result;
    }
    private void notFoundUnless(boolean found) {
        if (!found) throw new ResponseStatusException(HttpStatus.NOT_FOUND, "Resource not found");
    }
    public boolean ownsSubject(long id) {
        return count("SELECT COUNT(*) FROM prp_practice_subjects WHERE id=? AND user_id=?", id, CurrentUser.id()) == 1;
    }
    public boolean ownsBank(long id) {
        return count("SELECT COUNT(*) FROM prp_practice_banks WHERE id=? AND user_id=?", id, CurrentUser.id()) == 1;
    }
    private void requireSubject(long id) { notFoundUnless(ownsSubject(id)); }
    private void requireBank(long id) { notFoundUnless(ownsBank(id)); }
    private void requireQuestion(long id) {
        notFoundUnless(count("SELECT COUNT(*) FROM prp_practice_questions WHERE id=? AND user_id=?", id, CurrentUser.id()) == 1);
    }
    private void validateParent(Long parentId, Long selfId) {
        if (parentId == null) return;
        Set<Long> seen = new HashSet<>();
        Long cursor = parentId;
        while (cursor != null) {
            requireSubject(cursor);
            ensure(seen.add(cursor) && !cursor.equals(selfId), "Subject hierarchy contains a cycle");
            var parents = jdbc.query("SELECT parent_id FROM prp_practice_subjects WHERE id=? AND user_id=?",
                    (rs, n) -> rs.getObject(1, Long.class), cursor, CurrentUser.id());
            cursor = parents.get(0);
        }
    }

    private final RowMapper<Subject> subjectRow = (rs, row) ->
            new Subject(rs.getLong("id"), rs.getObject("parent_id", Long.class),
                    rs.getString("name"), rs.getString("description"));
    private final RowMapper<Bank> bankRow = (rs, row) ->
            new Bank(rs.getLong("id"), rs.getLong("subject_id"), rs.getString("title"),
                    rs.getString("description"), rs.getString("source_name"),
                    rs.getString("license_note"), rs.getString("status"));

    public List<Subject> subjects() {
        return jdbc.query("SELECT * FROM prp_practice_subjects WHERE user_id=? ORDER BY id",
                subjectRow, CurrentUser.id());
    }
    public Subject createSubject(SubjectForm form) {
        validateParent(form.parentId(), null);
        long id = insert("INSERT INTO prp_practice_subjects(user_id,parent_id,name,description) VALUES(?,?,?,?)",
                CurrentUser.id(), form.parentId(), required(form.name(), 120, "name"),
                optional(form.description(), 500, "description"));
        return subjects().stream().filter(s -> s.id() == id).findFirst().orElseThrow();
    }
    public void updateSubject(long id, SubjectForm form) {
        requireSubject(id);
        validateParent(form.parentId(), id);
        jdbc.update("UPDATE prp_practice_subjects SET parent_id=?,name=?,description=? WHERE id=? AND user_id=?",
                form.parentId(), required(form.name(), 120, "name"),
                optional(form.description(), 500, "description"), id, CurrentUser.id());
    }
    @Transactional
    public void deleteSubject(long id) {
        requireSubject(id);
        ensure(count("SELECT COUNT(*) FROM prp_practice_subjects WHERE parent_id=?", id) == 0, "Subject has children");
        ensure(count("SELECT COUNT(*) FROM prp_practice_banks WHERE subject_id=?", id) == 0, "Subject has banks");
        jdbc.update("DELETE FROM prp_practice_subjects WHERE id=? AND user_id=?", id, CurrentUser.id());
    }

    public List<Bank> banks(long subjectId) {
        requireSubject(subjectId);
        return jdbc.query("SELECT * FROM prp_practice_banks WHERE subject_id=? AND user_id=? ORDER BY id DESC",
                bankRow, subjectId, CurrentUser.id());
    }
    public Bank bank(long id) {
        return jdbc.query("SELECT * FROM prp_practice_banks WHERE id=? AND user_id=?",
                bankRow, id, CurrentUser.id()).stream().findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Bank not found"));
    }
    public Bank createBank(BankForm form) {
        requireSubject(form.subjectId());
        long id = insert("INSERT INTO prp_practice_banks(user_id,subject_id,title,description,source_name,license_note) VALUES(?,?,?,?,?,?)",
                CurrentUser.id(), form.subjectId(), required(form.title(), 160, "title"),
                optional(form.description(), 500, "description"),
                optional(form.sourceName(), 255, "sourceName"), optional(form.licenseNote(), 255, "licenseNote"));
        return bank(id);
    }
    public void updateBank(long id, BankForm form) {
        requireBank(id);
        requireSubject(form.subjectId());
        jdbc.update("UPDATE prp_practice_banks SET subject_id=?,title=?,description=?,source_name=?,license_note=? WHERE id=? AND user_id=?",
                form.subjectId(), required(form.title(), 160, "title"),
                optional(form.description(), 500, "description"),
                optional(form.sourceName(), 255, "sourceName"), optional(form.licenseNote(), 255, "licenseNote"),
                id, CurrentUser.id());
    }
    public void setBankStatus(long id, String status) {
        requireBank(id);
        ensure("draft".equals(status) || "published".equals(status), "Invalid status");
        jdbc.update("UPDATE prp_practice_banks SET status=? WHERE id=? AND user_id=?",
                status, id, CurrentUser.id());
    }
    @Transactional
    public void deleteBank(long id) {
        requireBank(id);
        ensure(count("SELECT COUNT(*) FROM prp_practice_questions WHERE bank_id=?", id) == 0, "Bank has questions");
        jdbc.update("DELETE FROM prp_practice_imports WHERE bank_id=? AND user_id=?", id, CurrentUser.id());
        jdbc.update("DELETE FROM prp_practice_banks WHERE id=? AND user_id=?", id, CurrentUser.id());
    }

    private <T> T decode(String text, TypeReference<T> type) {
        try { return json.readValue(text, type); }
        catch (JsonProcessingException e) { throw new IllegalStateException("Corrupt practice JSON in database", e); }
    }
    private String encode(Object value) {
        try { return json.writeValueAsString(value); }
        catch (JsonProcessingException e) { throw new IllegalArgumentException("Invalid JSON content", e); }
    }
    private final RowMapper<Question> questionRow = (rs, row) -> new Question(
            rs.getLong("id"), rs.getLong("bank_id"), rs.getString("question_type"),
            rs.getString("stem"), decode(rs.getString("options_json"), new TypeReference<List<Option>>() {}),
            decode(rs.getString("answers_json"), new TypeReference<List<String>>() {}),
            rs.getString("explanation"), rs.getString("difficulty"), rs.getString("status"));

    public List<Question> questions(long bankId) {
        requireBank(bankId);
        return jdbc.query("SELECT * FROM prp_practice_questions WHERE bank_id=? AND user_id=? ORDER BY id DESC LIMIT 500",
                questionRow, bankId, CurrentUser.id());
    }
    public Question question(long id) {
        return jdbc.query("SELECT * FROM prp_practice_questions WHERE id=? AND user_id=?",
                questionRow, id, CurrentUser.id()).stream().findFirst()
                .orElseThrow(() -> new ResponseStatusException(HttpStatus.NOT_FOUND, "Question not found"));
    }

    public QuestionForm validated(QuestionForm form) {
        ensure(form != null, "Question is missing");
        String type = required(form.type(), 20, "type").toLowerCase();
        ensure(List.of("single", "multiple", "boolean").contains(type), "Unsupported question type");
        String stem = required(form.stem(), 5000, "stem");
        var options = form.options();
        ensure(options != null && options.size() >= 2 && options.size() <= 8, "2-8 options required");
        Set<String> keys = new HashSet<>();
        List<Option> validated = new ArrayList<>();
        for (var o : options) {
            ensure(o != null, "Invalid option");
            String key = required(o.key(), 8, "option key").toUpperCase();
            ensure(keys.add(key), "Duplicate option key");
            validated.add(new Option(key, required(o.text(), 1000, "option text")));
        }
        var answers = form.answers();
        ensure(answers != null && !answers.isEmpty(), "Answer required");
        var normalized = answers.stream().map(s -> required(s, 8, "answer").toUpperCase()).distinct().sorted().toList();
        ensure(keys.containsAll(normalized), "Answer must match an option");
        ensure(!type.equals("single") || normalized.size() == 1, "Single choice needs one answer");
        ensure(!type.equals("boolean") || (normalized.size() == 1 && options.size() == 2), "Boolean question needs two options");
        String difficulty = form.difficulty() == null || form.difficulty().isBlank() ? "medium" : form.difficulty();
        ensure(List.of("easy", "medium", "hard").contains(difficulty), "Invalid difficulty");
        return new QuestionForm(type, stem, validated, normalized,
                optional(form.explanation(), 20000, "explanation"), difficulty);
    }
    private String fingerprint(QuestionForm form) {
        try {
            byte[] digest = MessageDigest.getInstance("SHA-256").digest(
                    encode(List.of(form.type(), form.stem(), form.options(), form.answers())).getBytes(StandardCharsets.UTF_8));
            return HexFormat.of().formatHex(digest);
        } catch (NoSuchAlgorithmException e) { throw new IllegalStateException(e); }
    }
    private boolean insertQuestion(long bankId, QuestionForm form) {
        QuestionForm checked = validated(form);
        try {
            insert("INSERT INTO prp_practice_questions(user_id,bank_id,question_type,stem,options_json,answers_json,explanation,difficulty,fingerprint) VALUES(?,?,?,?,?,?,?,?,?)",
                    CurrentUser.id(), bankId, checked.type(), checked.stem(), encode(checked.options()),
                    encode(checked.answers()), checked.explanation(), checked.difficulty(), fingerprint(checked));
            return true;
        } catch (DuplicateKeyException ex) {
            return false;
        }
    }
    public Question createQuestion(long bankId, QuestionForm form) {
        requireBank(bankId);
        QuestionForm checked = validated(form);
        ensure(insertQuestion(bankId, checked), "Duplicate question in this bank");
        return jdbc.query("SELECT * FROM prp_practice_questions WHERE bank_id=? AND user_id=? AND fingerprint=?",
                questionRow, bankId, CurrentUser.id(), fingerprint(checked)).get(0);
    }
    public void updateQuestion(long id, QuestionForm form) {
        Question old = question(id);
        QuestionForm checked = validated(form);
        ensure("draft".equals(old.status()), "Only draft questions can be edited");
        try {
            jdbc.update("UPDATE prp_practice_questions SET question_type=?,stem=?,options_json=?,answers_json=?,explanation=?,difficulty=?,fingerprint=? WHERE id=? AND user_id=?",
                    checked.type(), checked.stem(), encode(checked.options()), encode(checked.answers()),
                    checked.explanation(), checked.difficulty(), fingerprint(checked), id, CurrentUser.id());
        } catch (DuplicateKeyException ex) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "Duplicate question");
        }
    }
    public void setQuestionStatus(long id, String status) {
        requireQuestion(id);
        ensure("draft".equals(status) || "published".equals(status), "Invalid status");
        jdbc.update("UPDATE prp_practice_questions SET status=? WHERE id=? AND user_id=?", status, id, CurrentUser.id());
    }
    public void deleteQuestion(long id) {
        requireQuestion(id);
        ensure(count("SELECT COUNT(*) FROM prp_practice_attempts WHERE question_id=?", id) == 0,
                "Question has learning history; unpublish it instead");
        jdbc.update("DELETE FROM prp_practice_questions WHERE id=? AND user_id=?", id, CurrentUser.id());
    }
    public List<QuestionPublic> playable(long bankId) {
        ensure("published".equals(bank(bankId).status()), "Publish the bank to start practicing");
        return jdbc.query("SELECT * FROM prp_practice_questions WHERE bank_id=? AND user_id=? AND status='published' ORDER BY id LIMIT 100",
                questionRow, bankId, CurrentUser.id()).stream()
                .map(q -> new QuestionPublic(q.id(), q.bankId(), q.type(), q.stem(), q.options(), q.difficulty())).toList();
    }
    @Transactional
    public GradeResult grade(long id, AnswerForm request) {
        Question q = question(id);
        ensure("published".equals(q.status()) && "published".equals(bank(q.bankId()).status()),
                "Question is not published");
        ensure(request != null && request.answers() != null, "Missing answers");
        var answers = request.answers().stream().map(a -> required(a, 8, "answer").toUpperCase()).distinct().sorted().toList();
        ensure(q.options().stream().map(Option::key).collect(java.util.stream.Collectors.toSet()).containsAll(answers),
                "Unknown answer option");
        boolean correct = q.answers().equals(answers);
        jdbc.update("INSERT INTO prp_practice_attempts(user_id,question_id,submitted_answers,is_correct) VALUES(?,?,?,?)",
                CurrentUser.id(), id, encode(answers), correct);
        return new GradeResult(correct, q.answers(), q.explanation());
    }
    public Statistics statistics() {
        var rows = jdbc.query("SELECT COUNT(*) AS total, COALESCE(SUM(is_correct),0) AS correct FROM prp_practice_attempts WHERE user_id=?",
                (rs, n) -> new Statistics(rs.getLong("total"), rs.getLong("correct"),
                        rs.getLong("total") - rs.getLong("correct")), CurrentUser.id());
        return rows.get(0);
    }
    public List<QuestionPublic> wrongQuestions() {
        return jdbc.query("SELECT q.* FROM prp_practice_questions q JOIN ("
                + "SELECT question_id, MAX(id) AS last_id FROM prp_practice_attempts WHERE user_id=? GROUP BY question_id"
                + ") latest ON latest.question_id=q.id JOIN prp_practice_attempts a ON a.id=latest.last_id "
                + "JOIN prp_practice_banks b ON b.id=q.bank_id "
                + "WHERE q.user_id=? AND a.is_correct=0 AND q.status='published' AND b.status='published' "
                + "ORDER BY a.created_at DESC LIMIT 100", questionRow, CurrentUser.id(), CurrentUser.id())
                .stream().map(q -> new QuestionPublic(q.id(), q.bankId(), q.type(), q.stem(),
                        q.options(), q.difficulty())).toList();
    }

    public ImportPreview preview(ImportForm form) {
        List<QuestionForm> questions = PracticeImportParser.parse(form, json).stream().map(this::validated).toList();
        return new ImportPreview(questions.size(), questions.stream().limit(3).toList());
    }
    @Transactional
    public ImportResult importQuestions(long bankId, ImportForm form) {
        requireBank(bankId);
        List<QuestionForm> questions = PracticeImportParser.parse(form, json);
        int added = 0;
        for (QuestionForm item : questions) if (insertQuestion(bankId, item)) added++;
        jdbc.update("INSERT INTO prp_practice_imports(user_id,bank_id,format_name,imported_count,duplicate_count,source_name) VALUES(?,?,?,?,?,?)",
                CurrentUser.id(), bankId, form.format().toLowerCase(), added, questions.size()-added,
                optional(form.sourceName(), 255, "sourceName"));
        return new ImportResult(added, questions.size()-added);
    }
}