package com.matrix.prp;

import com.matrix.prp.auth.model.UserAccount;
import com.matrix.prp.auth.repository.UserStore;
import com.matrix.prp.mcp.*;
import com.matrix.prp.wellness.*;
import com.matrix.prp.wellness.WellnessModels.*;
import java.math.BigDecimal;
import java.time.LocalDate;
import java.util.*;
import org.junit.jupiter.api.*;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.*;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;
import org.springframework.security.crypto.password.PasswordEncoder;
import org.springframework.web.server.ResponseStatusException;
import org.springframework.transaction.support.TransactionTemplate;
import static org.assertj.core.api.Assertions.*;

/** Real disposable MySQL: structured health rows, owner locks, human approval and atomic consumption. */
@SpringBootTest
@ActiveProfiles("video-integration")
@TestPropertySource(properties={"matrix-prp.mcp.enabled=true","matrix-prp.mcp.write-enabled=true","spring.ai.mcp.server.enabled=true"})
class McpWellnessDatabaseIT {
    @Autowired McpDraftService drafts;
    @Autowired WellnessService wellness;
    @Autowired UserStore users;
    @Autowired PasswordEncoder passwords;
    @Autowired JdbcTemplate db;
    @Autowired org.springframework.transaction.PlatformTransactionManager transactions;
    final String password="synthetic-health-ci-password";
    UserAccount owner,other;
    @BeforeEach void setup() {
        owner=users.create("health_"+UUID.randomUUID().toString().replace("-","").substring(0,18),"Synthetic health",passwords.encode(password),false);
        other=users.create("health_"+UUID.randomUUID().toString().replace("-","").substring(0,18),"Synthetic other",passwords.encode(password),false);
        as(owner);
    }
    void as(UserAccount user) { SecurityContextHolder.getContext().setAuthentication(new UsernamePasswordAuthenticationToken(user.profile(),null,List.of())); }
    @AfterEach void clear() { SecurityContextHolder.clearContext(); }
    McpWellnessSupport.Input input(String entity,String note) {
        return switch(entity) {
            case "meal" -> new McpWellnessSupport.Input(new McpWellnessSupport.Meal(LocalDate.now(),"LUNCH",note,
                List.of(new WellnessService.AiMealItem(null,"Synthetic meal",null,new BigDecimal("500.00")))),null,null);
            case "exercise" -> new McpWellnessSupport.Input(null,new ExerciseInput(LocalDate.now(),note,30,new BigDecimal("100"),"Synthetic"),null);
            default -> new McpWellnessSupport.Input(null,null,new BodyMetricInput(LocalDate.now(),new BigDecimal(note),null,null));
        };
    }
    long approveCreate(String entity) {
        var draft=drafts.prepareWellness(entity,0,input(entity,entity.equals("metric")?"70":"Before"),McpDraftService.Kind.WELLNESS_CREATE);
        assertThatThrownBy(()->drafts.confirm(draft.draftId())).isInstanceOf(ResponseStatusException.class);
        as(other);assertThatThrownBy(()->drafts.approve(draft.draftId(),password)).isInstanceOf(ResponseStatusException.class);
        as(owner);assertThat(drafts.approve(draft.draftId(),password).status()).isEqualTo("APPROVED");
        long id=drafts.confirm(draft.draftId()).saved().path("id").asLong();
        assertThat(id).isPositive();assertThat(drafts.confirm(draft.draftId()).alreadySaved()).isTrue();return id;
    }
    @Test void allThreeEntitiesHaveApprovedCreateUpdateDeleteAndIdempotentConsumption() {
        for(String entity:List.of("meal","exercise","metric")) {
            long id=approveCreate(entity);
            if(entity.equals("meal")) {
                assertThat(wellness.daily(LocalDate.now()).calories()).isEqualByComparingTo("500");
                assertThat(wellness.ownedMeal(id).items().getFirst().estimate()).isTrue();
            }
            as(other);assertThatThrownBy(()->drafts.prepareWellness(entity,id,null,McpDraftService.Kind.WELLNESS_DELETE)).isInstanceOf(ResponseStatusException.class);
            as(owner);
            var update=drafts.prepareWellness(entity,id,input(entity,entity.equals("metric")?"71":"After"),McpDraftService.Kind.WELLNESS_UPDATE);
            drafts.approve(update.draftId(),password);var changed=drafts.confirm(update.draftId());
            assertThat(changed.saved().path(entity.equals("meal")?"note":entity.equals("exercise")?"name":"weightKg").asText()).startsWith(entity.equals("metric")?"71":"After");
            assertThat(drafts.confirm(update.draftId()).alreadySaved()).isTrue();
            var deletion=drafts.prepareWellness(entity,id,null,McpDraftService.Kind.WELLNESS_DELETE);
            drafts.approve(deletion.draftId(),password);assertThat(drafts.confirm(deletion.draftId()).saved().path("deleted").asBoolean()).isTrue();
            assertThat(drafts.confirm(deletion.draftId()).alreadySaved()).isTrue();
        }
        assertThat(db.queryForObject("SELECT COUNT(*) FROM prp_records WHERE user_id=?",Integer.class,owner.id())).isZero();
    }
    @Test void changedRecordCannotBeDeletedAndFailedTransactionRestoresBothRecordAndDraft() {
        long id=approveCreate("exercise");
        var draft=drafts.prepareWellness("exercise",id,null,McpDraftService.Kind.WELLNESS_DELETE);
        drafts.approve(draft.draftId(),password);
        wellness.updateExercise(id,new ExerciseInput(LocalDate.now(),"Human edit",40,null,null));
        assertThatThrownBy(()->drafts.confirm(draft.draftId())).isInstanceOf(ResponseStatusException.class);
        assertThat(wellness.ownedExercise(id).name()).isEqualTo("Human edit");
        var fresh=drafts.prepareWellness("exercise",id,null,McpDraftService.Kind.WELLNESS_DELETE);drafts.approve(fresh.draftId(),password);
        assertThatThrownBy(()->new TransactionTemplate(transactions).executeWithoutResult(s->{drafts.confirm(fresh.draftId());throw new IllegalStateException("Synthetic rollback");})).isInstanceOf(IllegalStateException.class);
        assertThat(wellness.ownedExercise(id).name()).isEqualTo("Human edit");
        assertThat(drafts.review(fresh.draftId()).status()).isEqualTo("APPROVED");
    }
    @Test void foodOwnershipAndNutritionSnapshotAreRecheckedBeforeCommit() {
        var food=wellness.addFood(new FoodInput("Synthetic food","",new BigDecimal("100"),BigDecimal.ZERO,BigDecimal.ZERO,BigDecimal.ZERO,"CI"));
        var input=new McpWellnessSupport.Input(new McpWellnessSupport.Meal(LocalDate.now(),"DINNER","CI",List.of(new WellnessService.AiMealItem(food.id(),null,new BigDecimal("100"),null))),null,null);
        as(other);assertThatThrownBy(()->drafts.prepareWellness("meal",0,input,McpDraftService.Kind.WELLNESS_CREATE)).isInstanceOf(ResponseStatusException.class);
        as(owner);var draft=drafts.prepareWellness("meal",0,input,McpDraftService.Kind.WELLNESS_CREATE);drafts.approve(draft.draftId(),password);
        db.update("UPDATE prp_wellness_foods SET calories_100g=200 WHERE id=? AND owner_user_id=?",food.id(),owner.id());
        assertThatThrownBy(()->drafts.confirm(draft.draftId())).isInstanceOf(ResponseStatusException.class);
        assertThat(wellness.meals(LocalDate.now())).isEmpty();
        assertThat(drafts.review(draft.draftId()).status()).isEqualTo("APPROVED");
    }
    @Test void invalidUnionAndExpiredOrRejectedDraftsNeverWriteHealthData() {
        assertThatThrownBy(()->drafts.prepareWellness("exercise",0,input("metric","70"),McpDraftService.Kind.WELLNESS_CREATE)).isInstanceOf(ResponseStatusException.class);
        for(boolean expire:List.of(true,false)) {
            var draft=drafts.prepareWellness("metric",0,input("metric","70"),McpDraftService.Kind.WELLNESS_CREATE);
            drafts.approve(draft.draftId(),password);
            if(expire) db.update("UPDATE prp_mcp_write_drafts SET expires_at=DATE_SUB(NOW(),INTERVAL 1 MINUTE) WHERE id=?",draft.draftId());
            else drafts.reject(draft.draftId());
            assertThatThrownBy(()->drafts.confirm(draft.draftId())).isInstanceOf(ResponseStatusException.class);
        }
        assertThat(wellness.metrics(1)).isEmpty();
    }
}
