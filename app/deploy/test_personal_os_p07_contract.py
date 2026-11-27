"""Offline source contracts only. No proxy process, credentials or network."""
from pathlib import Path
import unittest

APP = Path(__file__).resolve().parents[1]
AI = APP / "backend/src/main/java/com/matrix/prp/ai"

class PersonalOsP07ContractTests(unittest.TestCase):
    def test_scoped_clients(self):
        for name in ("DeepSeekClient", "AiProviderClient", "AiToolPlanner",
                     "SpringAiToolPlanner", "SpringAiStructuredModelClient", "SpringAiVisionModelClient"):
            self.assertIn("AiEgressTransport.httpClient().build()", (AI / (name + ".java")).read_text())
        for name in ("SpringAiDeepSeekAdapter", "SpringAiUniversalProviderAdapter"):
            self.assertIn("AiEgressTransport.streamingClient().filter(", (AI / (name + ".java")).read_text())

    def test_native_wellness_and_practice_use_model_proxy_only(self):
        wellness = (AI.parent / "wellness/WellnessAiDraftService.java").read_text()
        practice = (AI.parent / "practice/PracticeAiService.java").read_text()
        self.assertIn("AiEgressTransport.httpClient().connectTimeout(Duration.ofSeconds(6)).build()", wellness)
        self.assertIn("AiEgressTransport.httpClient().build()", practice)
        for source in (wellness, practice):
            self.assertNotIn("HttpClient.newBuilder()", source)
        # These are not model provider HTTP calls; preserve their existing routes.
        for relative in ("wellness/UsdaFoodCatalog.java", "ai/OpenClawGatewayClient.java",
                         "ai/CodexWorkflowClient.java"):
            self.assertNotIn("AiEgressTransport", (AI.parent / relative).read_text())

    def test_extraction_build_and_runtime_default_off(self):
        app = (APP / "backend/src/main/resources/application.yml").read_text()
        docker = (APP / "deploy/mcp-staging/Dockerfile.web").read_text()
        workflow = (APP.parent / ".github/workflows/deploy-prp.yml").read_text()
        chat = (APP / "web/src/views/ChatView.vue").read_text()
        self.assertIn("enabled: ${MATRIX_PRP_PERSONAL_OS_CHAT_EXTRACTION_ENABLED:false}", app)
        self.assertIn("ARG VITE_PERSONAL_OS_CHAT_EXTRACTION=false", docker)
        self.assertIn("ENV VITE_PERSONAL_OS_CHAT_EXTRACTION=${VITE_PERSONAL_OS_CHAT_EXTRACTION}", docker)
        self.assertIn("vars.PRP_PERSONAL_OS_CHAT_EXTRACTION == 'true' && 'true' || 'false'", workflow)
        self.assertIn("import.meta.env.VITE_PERSONAL_OS_CHAT_EXTRACTION === 'true'", chat)

    def test_squid_review_policy_denies_before_allow(self):
        config = (APP / "deploy/personal-os/squid-egress.review.conf").read_text()
        self.assertIn("acl model_backend src 192.0.2.10/32", config)
        self.assertIn("acl model_host dstdomain -n api.deepseek.com", config)
        self.assertNotIn("ssl_bump", config)
        rules = [line for line in config.splitlines() if line.startswith("http_access ")]
        self.assertEqual(rules, ["http_access deny !model_backend", "http_access deny !CONNECT",
            "http_access deny !TLS_port", "http_access deny !model_host", "http_access deny private_dst",
            "http_access allow model_backend", "http_access deny all"])

if __name__ == "__main__":
    unittest.main()
