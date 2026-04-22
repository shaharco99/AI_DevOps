"""Application constants."""

# ============================================================================
# Tool Names
# ============================================================================
TOOL_SQL = "sql_query_tool"
TOOL_KUBERNETES = "kubernetes_tool"
TOOL_LOG_ANALYSIS = "log_analysis_tool"
TOOL_METRICS = "metrics_tool"
TOOL_PIPELINE = "pipeline_status_tool"
TOOL_RAG = "rag_retrieval_tool"

# Available tools
AVAILABLE_TOOLS = {
    TOOL_SQL,
    TOOL_KUBERNETES,
    TOOL_LOG_ANALYSIS,
    TOOL_METRICS,
    TOOL_PIPELINE,
    TOOL_RAG,
}

# ============================================================================
# Kubernetes Constants
# ============================================================================
K8S_POD_PHASE_PENDING = "Pending"
K8S_POD_PHASE_RUNNING = "Running"
K8S_POD_PHASE_SUCCEEDED = "Succeeded"
K8S_POD_PHASE_FAILED = "Failed"
K8S_POD_PHASE_UNKNOWN = "Unknown"

# ============================================================================
# Pipeline Status
# ============================================================================
PIPELINE_STATUS_SUCCESS = "success"
PIPELINE_STATUS_FAILED = "failed"
PIPELINE_STATUS_RUNNING = "running"
PIPELINE_STATUS_PENDING = "pending"

# ============================================================================
# Database
# ============================================================================
MAX_SQL_RESULT_ROWS = 1000
SQL_QUERY_TIMEOUT = 30

# ============================================================================
# Logging
# ============================================================================
LOG_FORMAT_JSON = "json"
LOG_FORMAT_TEXT = "text"

# ============================================================================
# Cache
# ============================================================================
CACHE_TTL_SHORT = 60  # 1 minute
CACHE_TTL_MEDIUM = 300  # 5 minutes
CACHE_TTL_LONG = 3600  # 1 hour

# ============================================================================
# API
# ============================================================================
API_RESPONSE_TIMEOUT = 30
MAX_REQUEST_SIZE = 10 * 1024 * 1024  # 10 MB

# ============================================================================
# RAG
# ============================================================================
RAG_TOP_K = 5  # Number of documents to retrieve
RAG_SCORE_THRESHOLD = 0.3  # Similarity threshold

# ============================================================================
# Error Messages
# ============================================================================
ERROR_TOOL_NOT_FOUND = "Tool {tool_name} not found"
ERROR_TOOL_EXECUTION_FAILED = "Tool {tool_name} execution failed: {error}"
ERROR_DATABASE_ERROR = "Database error: {error}"
ERROR_KUBERNETES_ERROR = "Kubernetes error: {error}"
ERROR_SQL_INJECTION_DETECTED = "Potential SQL injection detected"
ERROR_INVALID_METRIC_NAME = "Invalid metric name: {metric_name}"
