"""Unit tests for DevOps tools."""

import pytest

from ai_devops_assistant.tools.kubernetes_tool import KubernetesTool
from ai_devops_assistant.tools.log_tool import LogAnalysisTool
from ai_devops_assistant.tools.metrics_tool import MetricsTool
from ai_devops_assistant.tools.pipeline_tool import PipelineTool
from ai_devops_assistant.tools.sql_tool import SQLQueryTool


class TestSQLQueryTool:
    """Test SQL query tool."""

    @pytest.fixture
    def sql_tool(self):
        """SQL tool fixture."""
        return SQLQueryTool()

    def test_name_and_description(self, sql_tool):
        """Test tool name and description."""
        assert sql_tool.name == "sql_query_tool"
        assert "SQL queries" in sql_tool.description

    def test_safe_query_validation(self, sql_tool):
        """Test SQL injection prevention."""
        # Safe queries should pass
        is_safe, _ = sql_tool.validate_sql_injection("SELECT * FROM users WHERE id = 1")
        assert is_safe
        is_safe, _ = sql_tool.validate_sql_injection("SELECT COUNT(*) FROM logs")
        assert is_safe

        # Dangerous queries should fail
        is_safe, _ = sql_tool.validate_sql_injection("DROP TABLE users")
        assert not is_safe
        is_safe, _ = sql_tool.validate_sql_injection("DELETE FROM users")
        assert not is_safe
        is_safe, _ = sql_tool.validate_sql_injection("UPDATE users SET password = 'hack'")
        assert not is_safe
        is_safe, _ = sql_tool.validate_sql_injection("INSERT INTO users VALUES (1, 'hack')")
        assert not is_safe

    @pytest.mark.asyncio
    async def test_execute_without_session(self, sql_tool):
        """Test execute returns error when DB session is missing."""
        result = await sql_tool.execute("SELECT 1")
        assert result["success"] is False
        assert "session" in result["error"].lower()


class TestLogAnalysisTool:
    """Test log analysis tool."""

    @pytest.fixture
    def log_tool(self):
        """Log tool fixture."""
        return LogAnalysisTool()

    def test_name_and_description(self, log_tool):
        """Test tool name and description."""
        assert log_tool.name == "log_analysis_tool"
        assert "logs" in log_tool.description.lower()

    @pytest.mark.asyncio
    async def test_analyze_logs_without_session(self, log_tool):
        """Test log analysis returns session configuration error."""
        result = await log_tool.execute("error logs")
        assert result["success"] is False
        assert "session" in result["error"].lower()


class TestMetricsTool:
    """Test metrics tool."""

    @pytest.fixture
    def metrics_tool(self):
        """Metrics tool fixture."""
        return MetricsTool()

    def test_name_and_description(self, metrics_tool):
        """Test tool name and description."""
        assert metrics_tool.name == "metrics_tool"
        assert "metrics" in metrics_tool.description

    @pytest.mark.asyncio
    async def test_query_metrics_invalid_query(self, metrics_tool):
        """Test invalid metrics query input handling."""
        result = await metrics_tool.execute("")
        assert result["success"] is False
        assert "invalid query" in result["error"].lower()


class TestKubernetesTool:
    """Test Kubernetes tool."""

    @pytest.fixture
    def k8s_tool(self):
        """K8s tool fixture."""
        return KubernetesTool()

    def test_name_and_description(self, k8s_tool):
        """Test tool name and description."""
        assert k8s_tool.name == "kubernetes_tool"
        assert "Kubernetes" in k8s_tool.description

    @pytest.mark.asyncio
    async def test_query_pods_not_initialized(self, k8s_tool):
        """Test K8s query when client is not initialized."""
        result = await k8s_tool.execute("list_pods")
        assert result["success"] is False
        assert "not initialized" in result["error"].lower()


class TestPipelineTool:
    """Test pipeline tool."""

    @pytest.fixture
    def pipeline_tool(self):
        """Pipeline tool fixture."""
        return PipelineTool()

    def test_name_and_description(self, pipeline_tool):
        """Test tool name and description."""
        assert pipeline_tool.name == "pipeline_status_tool"
        assert "CI/CD" in pipeline_tool.description

    @pytest.mark.asyncio
    async def test_pipeline_status(self, pipeline_tool):
        """Test pipeline status check."""
        result = await pipeline_tool.execute("get_status")
        assert isinstance(result, dict)
        assert result["success"] is True
        assert "recent_runs" in result
