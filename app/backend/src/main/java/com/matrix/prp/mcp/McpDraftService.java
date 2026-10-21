package com.matrix.prp.mcp;

import com.fasterxml.jackson.core.JsonProcessingException;
import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.matrix.prp.auth.security.CurrentUser;
import com.matrix.prp.finance.model.CreateFinanceTransactionRequest;
import com.matrix.prp.finance.service.FinanceService;
import com.matrix.prp.records.model.CreateRecordRequest;
import com.matrix.prp.records.service.RecordService;
import com.matrix.prp.tasks.model.CreateTaskRequest;
import com.matrix.prp.tasks.service.TaskService;
import jakarta.validation.Validator;
import java.sql.Timestamp;
import java.time.LocalDateTime;
import java.util.List;
import java.util.UUID;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.boot.autoconfigure.condition.ConditionalOnProperty;
import org.springframework.http.HttpStatus;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.web.server.ResponseStatusException;

/**
 * Owner-scoped MCP drafts. The model only proposes a bounded business request.
 * A separate, explicit confirmation consumes a row once under a DB lock.
 * Never accept a userId, SQL statement or URL supplied by a model.
 */
@Service
@ConditionalOnProperty(prefix = "matrix-prp.mcp", name = "enabled", havingValue = "true")
public class McpDraftService {
    public enum Kind { TASK, FINANCE, RECORD }
    public record Preview(String draftId, String kind, JsonNode values, String expiresAt,
                          String instruction) {}
    public record Result(String draftId, String kind, JsonNode saved, boolean alreadySaved) {}
    private record Stored(String kind, String payload, String result, String status,
                          LocalDateTime expiresAt) {}

    private final JdbcTemplate db;
    private final ObjectMapper json;
    private final Validator validator;
    private final TaskService tasks;
    private final FinanceService finance;
    private final RecordService records;
    private final boolean writeEnabled;

    public McpDraftService(JdbcTemplate db, ObjectMapper json, Validator validator,
                           TaskService tasks, FinanceService finance, RecordService records,
                           @Value("${matrix-prp.mcp.write-enabled:false}") boolean writeEnabled) {
        this.db = db;
        this.json = json;
        this.validator = validator;
        this.tasks = tasks;
        this.finance = finance;
        this.records = records;
        this.writeEnabled = writeEnabled;
    }

    private void requireWrite() {
        CurrentUser.id(); // Fail closed if no authenticated PRP user reached the tool.
        if (!writeEnabled) {
            throw new ResponseStatusException(HttpStatus.FORBIDDEN, "MCP writing is disabled");
        }
    }

    @Transactional
    public Preview prepare(Kind kind, Object request) {
        requireWrite();
        validate(request);
        long owner = CurrentUser.id();
        Integer pending = db.queryForObject(
            "SELECT COUNT(*) FROM prp_mcp_write_drafts WHERE user_id=? AND status='PENDING' AND expires_at > CURRENT_TIMESTAMP",
            Integer.class, owner);
        if (pending != null && pending >= 50) {
            throw new ResponseStatusException(HttpStatus.TOO_MANY_REQUESTS, "Too many pending MCP drafts");
        }
        String id = UUID.randomUUID().toString();
        LocalDateTime expiry = LocalDateTime.now().plusMinutes(15);
        try {
            db.update("INSERT INTO prp_mcp_write_drafts (id,user_id,kind,payload_json,expires_at) VALUES (?,?,?,?,?)",
                id, owner, kind.name(), json.writeValueAsString(request), Timestamp.valueOf(expiry));
        } catch (JsonProcessingException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid draft");
        }
        return new Preview(id, kind.name(), json.valueToTree(request), expiry.toString(),
            "Review these values with the user. Do not call prp_confirm_draft until the user explicitly approves.");
    }

    @Transactional
    public Result confirm(String draftId, boolean userApproved) {
        requireWrite();
        if (!userApproved) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Explicit approval is required");
        }
        try {
            UUID.fromString(draftId);
        } catch (RuntimeException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid draft ID");
        }
        long owner = CurrentUser.id();
        List<Stored> rows = db.query(
            "SELECT kind,payload_json,result_json,status,expires_at FROM prp_mcp_write_drafts " +
                "WHERE id=? AND user_id=? FOR UPDATE",
            (rs, n) -> new Stored(rs.getString("kind"), rs.getString("payload_json"),
                rs.getString("result_json"), rs.getString("status"),
                rs.getTimestamp("expires_at").toLocalDateTime()),
            draftId, owner);
        if (rows.isEmpty()) {
            throw new ResponseStatusException(HttpStatus.NOT_FOUND, "MCP draft not found");
        }
        Stored row = rows.getFirst();
        if ("CONSUMED".equals(row.status())) {
            return new Result(draftId, row.kind(), readJson(row.result()), true);
        }
        if (!"PENDING".equals(row.status()) || !row.expiresAt().isAfter(LocalDateTime.now())) {
            throw new ResponseStatusException(HttpStatus.CONFLICT, "MCP draft expired or invalid");
        }
        JsonNode saved;
        try {
            Object request = switch (Kind.valueOf(row.kind())) {
                case TASK -> json.readValue(row.payload(), CreateTaskRequest.class);
                case FINANCE -> json.readValue(row.payload(), CreateFinanceTransactionRequest.class);
                case RECORD -> json.readValue(row.payload(), CreateRecordRequest.class);
            };
            validate(request);
            Object result = switch (Kind.valueOf(row.kind())) {
                case TASK -> tasks.create((CreateTaskRequest) request);
                case FINANCE -> finance.createTransaction((CreateFinanceTransactionRequest) request);
                case RECORD -> records.create((CreateRecordRequest) request);
            };
            saved = json.valueToTree(result);
            if (db.update("UPDATE prp_mcp_write_drafts SET status='CONSUMED', result_json=?, consumed_at=CURRENT_TIMESTAMP " +
                    "WHERE id=? AND user_id=? AND status='PENDING'",
                    json.writeValueAsString(saved), draftId, owner) != 1) {
                throw new ResponseStatusException(HttpStatus.CONFLICT, "MCP draft already consumed");
            }
        } catch (JsonProcessingException ex) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid MCP draft payload");
        }
        return new Result(draftId, row.kind(), saved, false);
    }

    private JsonNode readJson(String raw) {
        try {
            return json.readTree(raw);
        } catch (JsonProcessingException ex) {
            throw new ResponseStatusException(HttpStatus.INTERNAL_SERVER_ERROR, "Unreadable prior result");
        }
    }

    private void validate(Object request) {
        if (!validator.validate(request).isEmpty()) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid business fields");
        }
        if (request instanceof CreateTaskRequest t) {
            length(t.moduleCode(), 1, 40); length(t.title(), 1, 160);
            length(t.description(), 0, 4000);
        } else if (request instanceof CreateFinanceTransactionRequest f) {
            length(f.category(), 1, 80); length(f.account(), 0, 80);
            length(f.merchant(), 0, 160); length(f.note(), 0, 2000);
            if (f.amount() == null || f.amount().signum() <= 0 ||
                f.amount().compareTo(new java.math.BigDecimal("100000000")) > 0) {
                throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid amount");
            }
        } else if (request instanceof CreateRecordRequest r) {
            length(r.moduleCode(), 1, 40); length(r.title(), 1, 160);
            length(r.content(), 0, 10000);
        } else {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Unsupported request");
        }
    }

    private static void length(String value, int min, int max) {
        if ((value == null && min > 0) ||
            (value != null && (value.isBlank() && min > 0 || value.length() > max ||
                value.length() < min))) {
            throw new ResponseStatusException(HttpStatus.BAD_REQUEST, "Invalid field length");
        }
    }
}
