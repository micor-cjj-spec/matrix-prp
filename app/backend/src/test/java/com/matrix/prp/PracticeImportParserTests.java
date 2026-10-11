package com.matrix.prp;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.practice.PracticeImportParser;
import com.matrix.prp.practice.PracticeModels.ImportForm;
import org.junit.jupiter.api.Test;
import org.springframework.web.server.ResponseStatusException;
import static org.assertj.core.api.Assertions.*;

class PracticeImportParserTests {
    private final ObjectMapper mapper = new ObjectMapper();

    @Test void acceptsGeneralPurposeJsonQuestions() {
        String data = """
            [{"type":"single","stem":"Java 的基本单位？","options":[
               {"key":"A","text":"class"},{"key":"B","text":"package"}],
               "answers":["A"],"explanation":"类是基本结构","difficulty":"easy"}]
            """;
        var parsed = PracticeImportParser.parse(new ImportForm("json", data, "test"), mapper);
        assertThat(parsed).hasSize(1);
        assertThat(parsed.get(0).stem()).contains("Java");
    }

    @Test void readsQuotedCsvCellsAndNewlines() {
        String csv = "type,stem,options,answers,explanation,difficulty\n"
                + "multiple,\"A, B 哪些正确？\",\"A:甲|B:乙|C:丙\",A|C,\"第一行\n第二行\",medium\n";
        var result = PracticeImportParser.parse(new ImportForm("csv", csv, "test"), mapper);
        assertThat(result).hasSize(1);
        assertThat(result.get(0).answers()).containsExactly("A","C");
        assertThat(result.get(0).explanation()).contains("第二行");
    }

    @Test void rejectsBadAnswersAndOversizedImports() {
        String csv = "type,stem,options,answers,explanation,difficulty\n"
                + "single,example,A:a|B:b,Z,wrong,easy";
        assertThatThrownBy(() -> PracticeImportParser.parse(new ImportForm("csv", csv, "bad"), mapper))
                .isInstanceOf(ResponseStatusException.class);
        assertThatThrownBy(() -> PracticeImportParser.parse(
                new ImportForm("json", "x".repeat(1_000_001), "big"), mapper))
                .isInstanceOf(ResponseStatusException.class);
    }
}