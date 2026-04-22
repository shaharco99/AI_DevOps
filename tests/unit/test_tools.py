"""Unit tests for DevOps tools."""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from ai_devops_copilot.tools.sql_tool import SQLQueryTool
from ai_devops_copilot.tools.log_tool import LogAnalysisTool
from ai_devops_copilot.tools.metrics_tool import MetricsTool
from ai_devops_copilot.tools.kubernetes_tool import KubernetesTool
from ai_devops_copilot.tools.pipeline_tool import PipelineTool


class TestSQLQueryTool:
    """Test SQL query tool."""

    @pytest.fixture
    def sql_tool(self):
        """SQL tool fixture."""
        return SQLQueryTool()

    def test_name_and_description(self, sql_tool):
        """Test tool name and description."""
        assert sql_tool.name == "sql_query"
        assert "SQL queries" in sql_tool.description

    def test_safe_query_validation(self, sql_tool):
        """Test SQL injection prevention."""
        # Safe queries should pass
        assert sql_tool._is_safe_query("SELECT * FROM users WHERE id = 1")
        assert sql_tool._is_safe_query("SELECT COUNT(*) FROM logs")

        # Dangerous queries should fail
        assert not sql_tool._is_safe_query("DROP TABLE users")
        assert not sql_tool._is_safe_query("DELETE FROM users")
        assert not sql_tool._is_safe_query("UPDATE users SET password = 'hack'")
        assert not sql_tool._is_safe_query("INSERT INTO users VALUES (1, 'hack')")

    @pytest.mark.asyncio
    async def test_execute_safe_query(self, sql_tool):
        """Test executing safe query."""
        with patch("ai_devops_copilot.tools.sql_tool.get_db_session") as mock_session:
            mock_conn = AsyncMock()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [("data1",), ("data2",)]
            mock_conn.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_conn

            result = await sql_tool.execute("SELECT * FROM test_table")

            assert "data1" in result
            assert "data2" in result

    @pytest.mark.asyncio
    async def test_execute_unsafe_query(self, sql_tool):
        """Test executing unsafe query is blocked."""
        result = await sql_tool.execute("DROP TABLE users")
        assert "not allowed" in result.lower()


class TestLogAnalysisTool:
    """Test log analysis tool."""

    @pytest.fixture
    def log_tool(self):
        """Log tool fixture."""
        return LogAnalysisTool()

    def test_name_and_description(self, log_tool):
        """Test tool name and description."""
        assert log_tool.name == "log_analysis"
        assert "log files" in log_tool.description

    @pytest.mark.asyncio
    async def test_analyze_logs(self, log_tool):
        """Test log analysis."""
        with patch("ai_devops_copilot.tools.log_tool.get_db_session") as mock_session:
            mock_conn = AsyncMock()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("2024-01-01 10:00:00", "INFO", "Application started"),
                ("2024-01-01 10:01:00", "ERROR", "Database connection failed")
            ]
            mock_conn.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_conn

            result = await log_tool.execute("error logs")

            assert "ERROR" in result
            assert "Database connection failed" in result


class TestMetricsTool:
    """Test metrics tool."""

    @pytest.fixture
    def metrics_tool(self):
        """Metrics tool fixture."""
        return MetricsTool()

    def test_name_and_description(self, metrics_tool):
        """Test tool name and description."""
        assert metrics_tool.name == "metrics_query"
        assert "metrics" in metrics_tool.description

    @pytest.mark.asyncio
    async def test_query_metrics(self, metrics_tool):
        """Test metrics querying."""
        with patch("ai_devops_copilot.tools.metrics_tool.get_db_session") as mock_session:
            mock_conn = AsyncMock()
            mock_result = MagicMock()
            mock_result.fetchall.return_value = [
                ("cpu_usage", "85.5", "2024-01-01 10:00:00"),
                ("memory_usage", "72.3", "2024-01-01 10:00:00")
            ]
            mock_conn.execute.return_value = mock_result
            mock_session.return_value.__aenter__.return_value = mock_conn

            result = await metrics_tool.execute("cpu metrics")

            assert "cpu_usage" in result
            assert "85.5" in result


class TestKubernetesTool:
    """Test Kubernetes tool."""

    @pytest.fixture
    def k8s_tool(self):
        """K8s tool fixture."""
        return KubernetesTool()

    def test_name_and_description(self, k8s_tool):
        """Test tool name and description."""
        assert k8s_tool.name == "kubernetes_query"
        assert "Kubernetes" in k8s_tool.description

    @pytest.mark.asyncio
    async def test_query_pods_disabled(self, k8s_tool):
        """Test K8s query when disabled."""
        with patch("ai_devops_copilot.config.settings.settings") as mock_settings:
            mock_settings.enable_k8s = False

            result = await k8s_tool.execute("list pods")
            assert "disabled" in result.lower()


class TestPipelineTool:
    """Test pipeline tool."""

    @pytest.fixture
    def pipeline_tool(self):
        """Pipeline tool fixture."""
        return PipelineTool()

    def test_name_and_description(self, pipeline_tool):
        """Test tool name and description."""
        assert pipeline_tool.name == "pipeline_status"
        assert "CI/CD" in pipeline_tool.description

    @pytest.mark.asyncio
    async def test_pipeline_status(self, pipeline_tool):
        """Test pipeline status check."""
        result = await pipeline_tool.execute("pipeline status")
        assert isinstance(result, str)
        assert len(result) > 0