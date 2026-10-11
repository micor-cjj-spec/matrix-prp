package com.matrix.prp.practice;

import com.fasterxml.jackson.core.type.TypeReference;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.practice.PracticeModels.*;
import java.util.ArrayList;
import java.util.Arrays;
import java.util.List;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

/** Strict, bounded UTF-8 JSON/CSV ingestion; no implicit publication. */
public final class PracticeImportParser {
    private PracticeImportParser() {}
    public static List<QuestionForm> parse(ImportForm form, ObjectMapper mapper) {
        if (form == null || form.format() == null || form.content() == null
                || form.content().length() > 1_000_000)
            throw bad("Invalid or oversized import (maximum 1MB)");
        List<QuestionForm> questions;
        try {
            if (form.format().equalsIgnoreCase("json")) {
                questions = mapper.readValue(form.content(), new TypeReference<List<QuestionForm>>() {});
            } else if (form.format().equalsIgnoreCase("csv")) {
                questions = parseCsv(form.content());
            } else throw bad("Supported formats: JSON and CSV");
        } catch (ResponseStatusException e) { throw e; }
        catch (Exception e) { throw bad("Cannot parse import: " + e.getClass().getSimpleName()); }
        if (questions == null || questions.isEmpty() || questions.size() > 200)
            throw bad("Import requires 1-200 questions");
        return questions.stream().map(PracticeImportParser::validate).toList();
    }
    private static QuestionForm validate(QuestionForm q) {
        if (q == null || q.type() == null || q.stem() == null || q.stem().isBlank()
                || q.stem().length() > 5000 || q.answers() == null || q.answers().isEmpty()
                || q.options() == null || q.options().size() < 2 || q.options().size() > 8)
            throw bad("Invalid question in import");
        String type = q.type().toLowerCase();
        if (!List.of("single","multiple","boolean").contains(type)) throw bad("Unsupported question type");
        var keys = q.options().stream().map(o -> o == null ? "" : o.key()).toList();
        if (keys.stream().anyMatch(k -> k == null || k.isBlank())
                || keys.stream().distinct().count() != keys.size()
                || q.options().stream().anyMatch(o -> o == null || o.text() == null || o.text().isBlank()))
            throw bad("Invalid or duplicated option keys");
        if (!keys.containsAll(q.answers())) throw bad("Answer does not match option keys");
        if (!type.equals("multiple") && q.answers().size() != 1) throw bad("Single/boolean expects one answer");
        return q;
    }
    private static List<QuestionForm> parseCsv(String source) {
        List<List<String>> rows = csvRows(source);
        if (rows.isEmpty() || !rows.get(0).equals(
                List.of("type","stem","options","answers","explanation","difficulty")))
            throw bad("CSV header must be type,stem,options,answers,explanation,difficulty");
        List<QuestionForm> forms = new ArrayList<>();
        for (int i = 1; i < rows.size(); i++) {
            var row = rows.get(i);
            if (row.size() == 1 && row.get(0).isBlank()) continue;
            if (row.size() != 6) throw bad("Invalid CSV column count at row " + (i + 1));
            List<Option> options = new ArrayList<>();
            for (String option : row.get(2).split("\\|", -1)) {
                int divider = option.indexOf(':');
                if (divider < 1) throw bad("Options require A:text|B:text at row " + (i + 1));
                options.add(new Option(option.substring(0, divider).trim(),
                        option.substring(divider + 1).trim()));
            }
            forms.add(new QuestionForm(row.get(0).trim(), row.get(1).trim(), options,
                    Arrays.stream(row.get(3).split("\\|")).map(String::trim).toList(),
                    row.get(4), row.get(5).isBlank() ? "medium" : row.get(5).trim()));
        }
        return forms;
    }
    /** RFC4180-style quoting (including commas and newlines); prohibit unterminated quotes. */
    private static List<List<String>> csvRows(String source) {
        var rows = new ArrayList<List<String>>();
        var row = new ArrayList<String>();
        var cell = new StringBuilder();
        boolean quoted = false;
        for (int i = 0; i < source.length(); i++) {
            char c = source.charAt(i);
            if (c == '"') {
                if (quoted && i + 1 < source.length() && source.charAt(i+1) == '"') {
                    cell.append('"'); i++;
                } else quoted = !quoted;
            } else if (c == ',' && !quoted) {
                row.add(cell.toString()); cell.setLength(0);
            } else if ((c == '\n' || c == '\r') && !quoted) {
                if (c == '\r' && i + 1 < source.length() && source.charAt(i+1) == '\n') i++;
                row.add(cell.toString()); cell.setLength(0);
                rows.add(row); row = new ArrayList<>();
            } else cell.append(c);
        }
        if (quoted) throw bad("Unterminated CSV quote");
        if (!row.isEmpty() || !cell.isEmpty()) { row.add(cell.toString()); rows.add(row); }
        return rows;
    }
    private static ResponseStatusException bad(String message) {
        return new ResponseStatusException(HttpStatus.BAD_REQUEST, message);
    }
}