"""
Unified Agent - Integrating Agentic RAG, Chat, CLI, Database Tools, and RAG into one system.

This module provides:
1. **Agentic RAG**: Autonomously decides when to retrieve from vector stores
2. **Self-Reflective**: Iteratively refines responses based on feedback
3. **Hybrid Routing**: Routes to SQL (numeric), Vector (policy), or Both
4. **Chat Interface**: Interactive conversation support
5. **CLI Interface**: Command-line execution
6. **Database Tools**: Safe SQL execution with auto-correction
7. **RAG Integration**: ChromaDB vector store access

Architecture:
- UnifiedAgent: Main orchestrator combining all functionality
- QueryRouter: Analyzes and routes queries (SQL/Vector/Hybrid/None)
- ReflectionAgent: Evaluates response quality iteratively
- VectorRetriever: ChromaDB wrapper for semantic search
- ChatInterface: Conversation management with memory
- IntegratedDatabaseTools: Safe SQL execution with auto-correction

Integration:
- Imports database_tools from LLM_CI for SQL execution
- Uses Tools.py for document loading and vault management
- Uses Utils.py for LLM provider and system prompts
- Works with Chat.py and ChatGUI.py as frontends
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

# Configure logger early so it can be used in imports
logger = logging.getLogger(__name__)

try:
    import chromadb
except ImportError:
    chromadb = None

try:
    from langchain.agents import initialize_agent
    from langchain.agents import AgentType
    from langchain import ConversationBufferMemory
    from langchain.tools import Tool, tool
    from langchain_core.language_models import BaseLanguageModel
except ImportError as e:
    initialize_agent = None
    AgentType = None
    ConversationBufferMemory = None
    Tool = None
    tool = None
    BaseLanguageModel = None
    logger.warning(f"LangChain not fully available: {e}")
    logger.warning(f"  Python executable: {sys.executable}")
    logger.warning(f"  To fix: Run 'source venv/bin/activate' before running the script")

# Import Ollama client separately so a missing langchain package doesn't
# prevent using langchain_ollama when it is installed.
try:
    from langchain_ollama import OllamaLLM
except ImportError as e:
    OllamaLLM = None
    logger.warning(f"langchain_ollama not available: {e}")
    logger.warning(f"  Python executable: {sys.executable}")
    logger.warning(f"  To fix: Run 'source venv/bin/activate' before running the script")

from unittest.mock import MagicMock


class QueryRouteType(str, Enum):
    """Query routing strategy types."""
    SQL_ONLY = "sql_only"
    VECTOR_ONLY = "vector_only"
    HYBRID = "hybrid"
    NO_RETRIEVAL = "no_retrieval"


class ReflectionFeedback(str, Enum):
    """Self-reflection feedback types."""
    SUFFICIENT = "sufficient"
    NEEDS_MORE_CONTEXT = "needs_context"
    NEEDS_REFINEMENT = "needs_refinement"
    CONTRADICTORY = "contradictory"


@dataclass
class QueryAnalysis:
    """Result of query analysis."""
    route_type: QueryRouteType
    confidence: float
    reasoning: str
    should_retrieve_sql: bool
    should_retrieve_vector: bool
    num_iterations: int


@dataclass
class ReflectionResult:
    """Result of self-reflection evaluation."""
    feedback: ReflectionFeedback
    confidence: float
    reasoning: str
    suggested_action: str
    requires_refinement: bool


class QueryRouter:
    """Intelligent query router determining optimal retrieval strategy."""

    def __init__(self, llm: BaseLanguageModel):
        self.llm = llm
        self.routing_prompt = """Analyze the following query and determine the optimal retrieval strategy.

Query: {query}

Respond with a JSON object containing:
{{
    "route_type": "sql_only" | "vector_only" | "hybrid" | "no_retrieval",
    "confidence": 0.0-1.0,
    "reasoning": "brief explanation",
    "numeric_indicators": ["list of numeric/analytical keywords found"],
    "policy_indicators": ["list of policy/document keywords found"]
}}

Guidelines:
- sql_only: Queries with metrics, counts, numbers, dates, aggregations
- vector_only: Queries about policies, documentation, best practices, guidelines
- hybrid: Queries combining both analytical AND policy aspects
- no_retrieval: General conversation not requiring data access

Respond ONLY with the JSON object."""

    def analyze(self, query: str) -> QueryAnalysis:
        """Analyze query and determine routing strategy."""
        try:
            prompt = self.routing_prompt.format(query=query)
            response = self.llm.invoke(prompt)
            text = response.content if hasattr(response, 'content') else str(response)
            analysis_data = self._extract_json(text)
            
            route_type = QueryRouteType(analysis_data.get("route_type", "no_retrieval"))
            
            return QueryAnalysis(
                route_type=route_type,
                confidence=float(analysis_data.get("confidence", 0.5)),
                reasoning=analysis_data.get("reasoning", ""),
                should_retrieve_sql=route_type in [QueryRouteType.SQL_ONLY, QueryRouteType.HYBRID],
                should_retrieve_vector=route_type in [QueryRouteType.VECTOR_ONLY, QueryRouteType.HYBRID],
                num_iterations=1
            )
        except Exception as e:
            logger.warning(f"Query routing failed: {e}, defaulting to hybrid")
            return QueryAnalysis(
                route_type=QueryRouteType.HYBRID,
                confidence=0.3,
                reasoning="Error during routing analysis",
                should_retrieve_sql=True,
                should_retrieve_vector=True,
                num_iterations=1
            )

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Extract JSON from text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        return {
            "route_type": "no_retrieval",
            "confidence": 0.1,
            "reasoning": "Could not parse routing decision"
        }


class ReflectionAgent:
    """Self-reflective agent evaluating response quality."""

    def __init__(self, llm: BaseLanguageModel):
        self.llm = llm
        self.reflection_prompt = """Evaluate the quality of this response to the user's query.

User Query: {query}

Assistant Response:
{response}

Retrieved Context Used:
- SQL Results: {sql_results_available}
- Vector Results: {vector_results_available}
- Number of retrieval attempts: {iterations}

Respond with a JSON object containing:
{{
    "feedback": "sufficient" | "needs_context" | "needs_refinement" | "contradictory",
    "confidence": 0.0-1.0,
    "reasoning": "detailed explanation",
    "issues_found": ["list of specific issues if any"],
    "suggested_action": "specific actionable suggestion"
}}

Respond ONLY with the JSON object."""

    def reflect(
        self,
        query: str,
        response: str,
        sql_results_available: bool = False,
        vector_results_available: bool = False,
        iterations: int = 1
    ) -> ReflectionResult:
        """Evaluate response and provide feedback."""
        try:
            prompt = self.reflection_prompt.format(
                query=query,
                response=response,
                sql_results_available=sql_results_available,
                vector_results_available=vector_results_available,
                iterations=iterations
            )
            
            reflection_response = self.llm.invoke(prompt)
            text = reflection_response.content if hasattr(reflection_response, 'content') else str(reflection_response)
            result_data = self._extract_json(text)
            
            feedback = ReflectionFeedback(result_data.get("feedback", "sufficient"))
            
            return ReflectionResult(
                feedback=feedback,
                confidence=float(result_data.get("confidence", 0.5)),
                reasoning=result_data.get("reasoning", ""),
                suggested_action=result_data.get("suggested_action", ""),
                requires_refinement=feedback in [
                    ReflectionFeedback.NEEDS_MORE_CONTEXT,
                    ReflectionFeedback.NEEDS_REFINEMENT,
                    ReflectionFeedback.CONTRADICTORY
                ]
            )
        except Exception as e:
            logger.warning(f"Reflection failed: {e}")
            return ReflectionResult(
                feedback=ReflectionFeedback.SUFFICIENT,
                confidence=0.2,
                reasoning="Reflection analysis failed",
                suggested_action="Continue with current response",
                requires_refinement=False
            )

    @staticmethod
    def _extract_json(text: str) -> Dict[str, Any]:
        """Extract JSON from text."""
        try:
            return json.loads(text)
        except json.JSONDecodeError:
            pass
        
        match = re.search(r'\{[^{}]*\}', text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group())
            except json.JSONDecodeError:
                pass
        
        return {
            "feedback": "sufficient",
            "confidence": 0.1,
            "reasoning": "Could not parse reflection"
        }


class VectorRetriever:
    """Vector store retriever using ChromaDB."""
    
    def __init__(self, collection_name: str = "rag_collection"):
        self.collection_name = collection_name
        if chromadb is None:
            logger.warning("ChromaDB not installed, VectorRetriever will not work")
            self.client = None
        else:
            try:
                self.client = chromadb.Client()
            except Exception as e:
                logger.warning(f"Failed to initialize ChromaDB client: {e}")
                self.client = None
    
    def retrieve(
        self,
        query: str,
        top_k: int = 5,
        similarity_threshold: float = 0.5
    ) -> List[Dict[str, Any]]:
        """Retrieve relevant documents from vector store."""
        if self.client is None:
            logger.warning("ChromaDB client not available, returning empty results")
            return []
        
        try:
            collection = self.client.get_or_create_collection(name=self.collection_name)
            results = collection.query(query_texts=[query], n_results=top_k)
            
            if not results or not results.get('documents'):
                return []
            
            retrieved_docs = []
            for i, doc in enumerate(results['documents'][0]):
                retrieved_docs.append({
                    "content": doc,
                    "source": results.get('metadatas', [[]])[0][i] if results.get('metadatas') else None,
                    "id": results.get('ids', [[]])[0][i] if results.get('ids') else None
                })
            
            return retrieved_docs
        except Exception as e:
            logger.warning(f"Vector retrieval failed: {e}")
            return []


class DatabaseTools:
    """
    Safe database tools with auto-correction.
    
    This class wraps the sophisticated database_tools module from LLM_CI.
    If that module is not available, provides fallback implementation.
    """
    
    def __init__(self, db_path: str = 'sample_database.db'):
        self.db_path = db_path
        self._connection = None
        self._db_tools_module = None
        self._schema_cache = None
        
        # Try to import the full-featured database_tools module
        try:
            import sys
            llm_ci_path = os.path.join(os.path.dirname(__file__), 'LLM_CI')
            if os.path.exists(llm_ci_path) and llm_ci_path not in sys.path:
                sys.path.insert(0, llm_ci_path)
            
            from database_tools import (
                execute_database_query,
                get_database_schema_info,
                validate_sql_query,
                execute_query,
                get_sqlite_schema,
                parse_natural_language_query
            )
            self._db_tools_module = {
                'execute_database_query': execute_database_query,
                'get_database_schema_info': get_database_schema_info,
                'validate_sql_query': validate_sql_query,
                'execute_query': execute_query,
                'get_sqlite_schema': get_sqlite_schema,
                'parse_natural_language_query': parse_natural_language_query
            }
            logger.info("Loaded enhanced database_tools module from LLM_CI")
        except ImportError as e:
            logger.warning(f"Could not import enhanced database_tools: {e}, using fallback")
            self._db_tools_module = None
    
    def get_connection(self):
        """Get database connection."""
        if not self._connection:
            try:
                db_type = os.getenv('DB_TYPE', 'sqlite').lower()

                if db_type == 'sqlite':
                    import sqlite3
                    db_path = os.getenv('DB_PATH', self.db_path)
                    use_uri = os.getenv('DB_USE_URI', 'false').lower() in ('1', 'true', 'yes')
                    # Try several candidate locations similar to LLM_CI helpers
                    db_path_expanded = os.path.expanduser(db_path)
                    if not os.path.isabs(db_path_expanded):
                        candidates = [
                            os.path.join(os.getcwd(), db_path_expanded),
                            os.path.join(os.path.dirname(__file__), db_path_expanded),
                            os.path.normpath(os.path.join(os.path.dirname(__file__), '..', db_path_expanded)),
                        ]
                        found = None
                        for p in candidates:
                            if os.path.exists(p):
                                found = p
                                break
                        if not found:
                            # fallback to provided path
                            found = candidates[0]
                        db_path_final = found
                    else:
                        db_path_final = db_path_expanded

                    if not os.path.exists(db_path_final):
                        raise FileNotFoundError(f"Configured SQLite DB not found: {db_path_final}")

                    self._connection = sqlite3.connect(db_path_final, check_same_thread=False, uri=use_uri)
                    self._connection.row_factory = sqlite3.Row

                elif db_type in ('postgresql', 'postgres'):
                    try:
                        import psycopg2
                    except Exception as e:
                        raise ImportError('psycopg2 is required for PostgreSQL connections') from e

                    self._connection = psycopg2.connect(
                        host=os.getenv('DB_HOST', 'localhost'),
                        port=int(os.getenv('DB_PORT', 5432)),
                        user=os.getenv('DB_USER', ''),
                        password=os.getenv('DB_PASSWORD', ''),
                        dbname=os.getenv('DB_NAME', '')
                    )

                elif db_type == 'mysql':
                    try:
                        import pymysql
                    except Exception as e:
                        raise ImportError('pymysql is required for MySQL connections') from e

                    self._connection = pymysql.connect(
                        host=os.getenv('DB_HOST', 'localhost'),
                        port=int(os.getenv('DB_PORT', 3306)),
                        user=os.getenv('DB_USER', ''),
                        password=os.getenv('DB_PASSWORD', ''),
                        db=os.getenv('DB_NAME', ''),
                        charset='utf8mb4'
                    )

                elif db_type in ('mssql', 'sqlserver'):
                    try:
                        import pyodbc
                    except Exception as e:
                        raise ImportError('pyodbc is required for MSSQL connections') from e

                    driver = os.getenv('DB_DRIVER', 'ODBC Driver 17 for SQL Server')
                    host = os.getenv('DB_HOST', 'localhost')
                    port = os.getenv('DB_PORT', '1433')
                    database = os.getenv('DB_NAME', '')
                    user = os.getenv('DB_USER', '')
                    password = os.getenv('DB_PASSWORD', '')
                    conn_str = (
                        f'DRIVER={{{driver}}};SERVER={host},{port};DATABASE={database};UID={user};PWD={password}'
                    )
                    self._connection = pyodbc.connect(conn_str)

                else:
                    raise ValueError(f'Unsupported DB_TYPE: {db_type}')

            except Exception as e:
                logger.error(f"Database connection failed: {e}")
                raise
        return self._connection
    
    def execute_query(self, query: str) -> Tuple[List[Dict], Optional[str]]:
        """
        Execute SQL query safely.
        
        Uses enhanced database_tools if available, falls back to basic execution.
        """
        if self._db_tools_module and 'execute_query' in self._db_tools_module:
            try:
                results, error = self._db_tools_module['execute_query'](query)
                return results, error
            except Exception as e:
                logger.warning(f"Enhanced execute_query failed: {e}, using fallback")
        
        # Fallback implementation
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            # Validate query is SELECT-only
            if not query.strip().upper().startswith('SELECT'):
                return [], "Only SELECT queries are allowed"
            
            cur.execute(query)
            
            if cur.description:
                cols = [d[0] for d in cur.description]
                rows = [dict(zip(cols, row)) for row in cur.fetchall()]
                return rows, None
            
            return [], None
        except Exception as e:
            return [], str(e)
    
    def validate_query(self, query: str) -> Tuple[bool, str]:
        """
        Validate SQL query.
        
        Uses enhanced validation with auto-correction if available.
        """
        if self._db_tools_module and 'validate_sql_query' in self._db_tools_module:
            try:
                result = self._db_tools_module['validate_sql_query'](query)
                result_data = json.loads(result) if isinstance(result, str) else result
                return result_data.get('valid', False), result_data.get('message', '')
            except Exception as e:
                logger.warning(f"Enhanced validation failed: {e}")
        
        # Fallback: basic safety check
        query_upper = query.strip().upper()
        if not query_upper.startswith('SELECT'):
            return False, "Only SELECT queries are allowed"
        if ';' in query or '--' in query:
            return False, "Query contains prohibited syntax"
        return True, "Query appears valid"
    
    def get_schema(self) -> Dict[str, List[str]]:
        """
        Get database schema.
        
        Uses cached version of enhanced schema if available.
        """
        if self._schema_cache is not None:
            return self._schema_cache
        
        if self._db_tools_module and 'get_sqlite_schema' in self._db_tools_module:
            try:
                schema_dict = self._db_tools_module['get_sqlite_schema']()
                self._schema_cache = schema_dict
                return schema_dict
            except Exception as e:
                logger.warning(f"Enhanced get_schema failed: {e}")
        
        # Fallback: manual schema extraction
        schema = {}
        try:
            conn = self.get_connection()
            cur = conn.cursor()
            
            cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
            tables = cur.fetchall()
            
            for (table_name,) in tables:
                cur.execute(f"PRAGMA table_info('{table_name}');")
                cols = cur.fetchall()
                schema[table_name] = [col[1] for col in cols]
            
            self._schema_cache = schema
            return schema
        except Exception as e:
            logger.error(f"Schema retrieval failed: {e}")
            return {}
    
    def close(self):
        """Close database connection."""
        if self._connection:
            try:
                self._connection.close()
            except Exception:
                pass
            self._connection = None


class UnifiedAgent:
    """
    Unified Agent combining:
    - Agentic RAG with Self-Reflection
    - Chat/CLI interfaces
    - Database tools
    - Vector retrieval
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        collection_name: Optional[str] = None,
        db_path: Optional[str] = None,
        max_reflection_iterations: Optional[int] = None,
        llm: Optional[BaseLanguageModel] = None
    ):
        """
        Initialize UnifiedAgent.
        
        Args:
            base_url: Ollama base URL (default from OLLAMA_BASE_URL env var)
            model: Model name (default from OLLAMA_MODEL env var)
            collection_name: ChromaDB collection name (default from RAG_COLLECTION_NAME env var)
            db_path: Database path (default from DB_PATH env var)
            max_reflection_iterations: Max reflection loops (default from MAX_REFLECTION_ITERATIONS env var)
            llm: Optional pre-configured LLM (for testing/dependency injection)
        """
        # Load configuration from environment with defaults
        self.base_url = base_url or os.getenv('OLLAMA_BASE_URL', 'http://localhost:11434')
        self.model = model or os.getenv('OLLAMA_MODEL', 'llama3.1:8b')
        self.collection_name = collection_name or os.getenv('RAG_COLLECTION_NAME', 'rag_collection')
        self.db_path = db_path or os.getenv('DB_PATH', 'sample_database.db')
        self.max_reflection_iterations = max_reflection_iterations or int(os.getenv('MAX_REFLECTION_ITERATIONS', '3'))
        
        # Initialize LLM
        if llm is not None:
            self.llm = llm
        elif OllamaLLM is not None:
            try:
                self.llm = OllamaLLM(base_url=self.base_url, model=self.model, temperature=0.3)
            except Exception as e:
                logger.warning(
                    f"Failed to initialize OllamaLLM: {e}, using simple dummy LLM "
                    "for testing (no real model responses)."
                )

                class _DummyLLM:
                    """Simple synchronous LLM stub used when real LLM is unavailable."""

                    def predict(self, text: str) -> str:
                        return (
                            "Dummy LLM response (no real model available).\n\n"
                            f"Echo of your input:\n{text}"
                        )

                    def invoke(self, text: str):
                        # Mimic LangChain-style object with .content when possible
                        class _Resp:
                            def __init__(self, content: str):
                                self.content = content

                        return _Resp(self.predict(text))

                    def __call__(self, text: str) -> str:
                        return self.predict(text)

                self.llm = _DummyLLM()
        else:
            logger.warning(
                "LangChain OllamaLLM not available, using simple dummy LLM for testing "
                "(no real model responses)."
            )

            class _DummyLLM:
                """Simple synchronous LLM stub used when real LLM is unavailable."""

                def predict(self, text: str) -> str:
                    return (
                        "Dummy LLM response (no real model available).\n\n"
                        f"Echo of your input:\n{text}"
                    )

                def invoke(self, text: str):
                    class _Resp:
                        def __init__(self, content: str):
                            self.content = content

                    return _Resp(self.predict(text))

                def __call__(self, text: str) -> str:
                    return self.predict(text)

            self.llm = _DummyLLM()
        
        self.router = QueryRouter(self.llm)
        self.reflector = ReflectionAgent(self.llm)
        self.vector_retriever = VectorRetriever(self.collection_name) if chromadb else None
        self.db_tools = DatabaseTools(self.db_path)
        self.memory = ConversationBufferMemory(
            memory_key='chat_history', return_messages=True
        ) if ConversationBufferMemory else None
        self.tools: List[Tool] = []
        self.agent = None
        
        # Tracking
        self.last_query_analysis: Optional[QueryAnalysis] = None
        self.last_reflection: Optional[ReflectionResult] = None
        self.last_retrieval_results: Dict[str, Any] = {}
    
    def add_tool(self, name: str, func: callable, description: str):
        """Add a tool to the agent."""
        if Tool is None:
            logger.warning(f"Tool class not available, skipping tool addition: {name}")
            return
        
        self.tools.append(Tool(name=name, func=func, description=description))
    
    def initialize_agent(self):
        """Initialize the LangChain agent.

        Falls back to a simple LLM wrapper if LangChain agents are not available.
        """
        # If LangChain agent utilities are unavailable, create a minimal async wrapper
        if initialize_agent is None or AgentType is None:
            logger.warning(
                "LangChain Agent utilities not available. "
                "Falling back to a simple LLM-based agent. "
                "Tool usage and advanced agent behaviour will be limited."
            )

            class _SimpleAsyncAgent:
                """Minimal async-compatible agent wrapper around the LLM."""

                def __init__(self, llm, tools):
                    self._llm = llm
                    self._tools = tools or []

                async def arun(self, query: str) -> str:
                    """Asynchronously run the LLM on the provided query."""
                    # Prefer native async APIs if available
                    if hasattr(self._llm, "apredict"):
                        return await self._llm.apredict(query)
                    if hasattr(self._llm, "ainvoke"):
                        result = await self._llm.ainvoke(query)
                        return (
                            result.content
                            if hasattr(result, "content")
                            else str(result)
                        )

                    # Synchronous fallbacks
                    if hasattr(self._llm, "predict"):
                        return self._llm.predict(query)
                    if hasattr(self._llm, "invoke"):
                        result = self._llm.invoke(query)
                        return (
                            result.content
                            if hasattr(result, "content")
                            else str(result)
                        )
                    if callable(self._llm):
                        return self._llm(query)

                    raise RuntimeError("LLM instance does not support invocation APIs.")

            self.agent = _SimpleAsyncAgent(self.llm, self.tools)
            return

        # Normal LangChain agent initialization path
        self.agent = initialize_agent(
            tools=self.tools,
            llm=self.llm,
            agent=AgentType.CHAT_CONVERSATIONAL_REACT_DESCRIPTION,
            memory=self.memory,
            handle_parsing_errors=True,
            max_iterations=5,
            verbose=False,
        )
    
    async def _try_direct_database_execution(self, query: str) -> Optional[Dict[str, Any]]:
        """
        Try to directly execute a database query without LLM analysis.
        This uses intelligent natural language parsing to handle simple data requests with filters.
        
        For queries like "show me all clients from usa", this will:
        1. Detect the table name (clients)
        2. Detect the filter condition (from usa)
        3. Parse and generate proper SQL with WHERE clause
        4. Execute the query
        
        Returns a result dict if a query was successfully executed, None otherwise.
        """
        query_lower = query.lower().strip()
        
        # List of keywords that indicate a data retrieval request
        data_request_keywords = [
            'show', 'get', 'list', 'find', 'count', 'total', 'how many',
            'all ', 'top ', 'first ', 'last ', 'from ', 'select ',
            'where ', 'filter', 'search', 'retrieve', 'fetch', 'return'
        ]
        
        # Check if this looks like a data request
        is_data_request = any(keyword in query_lower for keyword in data_request_keywords)
        
        if not is_data_request:
            return None
        
        # Get database schema to understand what tables are available
        try:
            if not self.db_tools._db_tools_module or 'get_sqlite_schema' not in self.db_tools._db_tools_module:
                return None
            
            get_schema_func = self.db_tools._db_tools_module['get_sqlite_schema']
            schema = get_schema_func()
            
            if not schema:
                return None
        except Exception as e:
            logger.debug(f"Could not get database schema: {e}")
            return None
        
        table_names = list(schema.keys()) if schema else []
        if not table_names:
            return None
        
        # Check if query mentions any of the table names
        mentioned_tables = [
            tbl for tbl in table_names 
            if tbl.lower() in query_lower
        ]
        
        if not mentioned_tables:
            return None
        
        # Try to construct and execute a query for each mentioned table
        for table_name in mentioned_tables:
            try:
                # Try to parse the natural language query to extract filters
                sql_query = None
                if self.db_tools._db_tools_module and 'parse_natural_language_query' in self.db_tools._db_tools_module:
                    parse_func = self.db_tools._db_tools_module['parse_natural_language_query']
                    sql_query = parse_func(query, table_name, schema)
                
                # If NL parsing couldn't generate a filtered query, use basic SELECT
                if not sql_query:
                    columns = schema.get(table_name, [])
                    if not columns:
                        continue
                    
                    col_list = ', '.join(columns)
                    sql_query = f"SELECT {col_list} FROM {table_name} LIMIT 100"
                
                # Try to execute
                rows, err = self.db_tools.execute_query(sql_query)
                
                if not err and rows:
                    # Format as table
                    cols = list(rows[0].keys()) if rows else []
                    lines = [f"Results from '{table_name}' table:"]
                    lines.append(' | '.join(cols))
                    lines.append('-' * max(3, sum(len(c) + 3 for c in cols)))
                    for r in rows:
                        lines.append(' | '.join(str(r.get(c, '')) for c in cols))
                    formatted = '\n'.join(lines)
                    
                    return {
                        'status': 'success',
                        'result': formatted,
                        'error': None,
                        'routing_strategy': 'sql_only',
                        'routing_confidence': 0.8,
                        'retrieval_used': {'sql_executed': True, 'rows': rows}
                    }
            except Exception as e:
                logger.debug(f"Failed to execute query for table {table_name}: {e}")
                continue
        
        return None
    
    async def run(self, query: str) -> Dict[str, Any]:
        """Run the unified agent with full pipeline."""
        if not self.agent:
            self.initialize_agent()
        
        try:
            # Step 1: Try direct database query execution for common data requests
            # This works even when LangChain/LLM is unavailable
            result = await self._try_direct_database_execution(query)
            if result:
                return result
            
            # Step 2: Analyze query
            analysis = self.router.analyze(query)
            self.last_query_analysis = analysis
            
            # If routing indicates SQL retrieval, and the user's input is a SQL SELECT,
            # validate and execute it directly, returning results immediately.
            if analysis.should_retrieve_sql:
                try:
                    is_valid, msg = self.db_tools.validate_query(query)
                    if is_valid:
                        rows, err = self.db_tools.execute_query(query)
                        if err:
                            return {
                                'status': 'error',
                                'result': None,
                                'error': err,
                                'routing_strategy': analysis.route_type.value,
                                'routing_confidence': analysis.confidence,
                                'retrieval_used': {'sql_executed': True}
                            }

                        # Format rows as a simple table-like string
                        if rows:
                            cols = list(rows[0].keys()) if isinstance(rows, list) and len(rows) > 0 else []
                            lines = [' | '.join(cols)]
                            lines.append('-' * max(3, sum(len(c) + 3 for c in cols)))
                            for r in rows:
                                lines.append(' | '.join(str(r.get(c, '')) for c in cols))
                            formatted = '\n'.join(lines)
                        else:
                            formatted = 'No rows returned.'

                        return {
                            'status': 'success',
                            'result': formatted,
                            'error': None,
                            'routing_strategy': analysis.route_type.value,
                            'routing_confidence': analysis.confidence,
                            'retrieval_used': {'sql_executed': True, 'rows': rows}
                        }
                except Exception:
                    # Fall through to normal agent flow on errors
                    pass

            # Step 3: Retrieve context
            retrieval_results = await self._retrieve_context(query, analysis)
            self.last_retrieval_results = retrieval_results
            
            # Step 4: Augment query
            augmented_query = self._augment_query(query, retrieval_results)
            
            # Step 5: Execute agent
            response = await self.agent.arun(augmented_query)
            
            # Step 6: Reflection loop
            refined_response = await self._reflection_loop(
                query, response, retrieval_results
            )
            
            return {
                'status': 'success',
                'result': refined_response,
                'error': None,
                'routing_strategy': analysis.route_type.value,
                'routing_confidence': analysis.confidence,
                'retrieval_used': retrieval_results,
                'reflection_feedback': (
                    self.last_reflection.feedback.value if self.last_reflection else None
                )
            }
        
        except Exception as e:
            logger.exception(f"Agent execution failed: {e}")
            return {
                'status': 'error',
                'result': None,
                'error': str(e),
                'routing_strategy': None,
                'retrieval_used': {}
            }
    
    async def _retrieve_context(
        self,
        query: str,
        analysis: QueryAnalysis
    ) -> Dict[str, Any]:
        """Retrieve context based on routing decision."""
        results = {
            'sql_results': [],
            'vector_results': [],
            'strategy': analysis.route_type.value
        }
        
        if analysis.should_retrieve_vector:
            vector_docs = self.vector_retriever.retrieve(query, top_k=5)
            results['vector_results'] = vector_docs
            logger.info(f"Retrieved {len(vector_docs)} vector results")
        
        if analysis.should_retrieve_sql:
            logger.info("SQL retrieval enabled via agent tools")
            results['sql_enabled'] = True
        
        return results
    
    def _augment_query(
        self,
        query: str,
        retrieval_results: Dict[str, Any]
    ) -> str:
        """Augment query with retrieved context and system instructions."""
        # System instructions for handling database queries
        system_instructions = """## Database Query Processing Instructions

When processing database queries:
1. ALWAYS use the available database tools to construct and execute queries
2. First call 'get_database_schema_info' to understand the database structure if working with data
3. For natural language queries requesting data:
   - Extract ALL filter conditions and constraints from the user's request
   - Pay special attention to keywords like: FROM, WHERE, FILTER, ONLY, JUST, LIKE, CONTAINS, etc.
   - Example: "show me all clients from usa" means SELECT FROM clients WHERE country='USA'
   - Include country/state/region filters in WHERE clauses
   - Include date ranges in WHERE clauses if mentioned
4. Use 'execute_database_query' to run the constructed SQL query (the tool will validate and auto-correct it)
5. Return the results in a clear, formatted manner

IMPORTANT: Never ignore filter conditions or return unfiltered results when the user specifies criteria."""
        
        context_parts = [system_instructions]
        
        vector_results = retrieval_results.get('vector_results', [])
        if vector_results:
            context_parts.append("\n## Retrieved Documents:")
            for i, doc in enumerate(vector_results[:3], 1):
                source = doc.get('source', 'unknown')
                content = doc.get('content', '')[:500]
                context_parts.append(f"Document {i} (from {source}):\n{content}...")
        
        return f"""{''.join(context_parts)}

User Query: {query}"""
    
    async def _reflection_loop(
        self,
        query: str,
        response: str,
        retrieval_results: Dict[str, Any],
        iteration: int = 1
    ) -> str:
        """Iterative self-reflection and refinement."""
        if iteration > self.max_reflection_iterations:
            logger.info("Max reflection iterations reached")
            return response
        
        reflection = self.reflector.reflect(
            query=query,
            response=response,
            sql_results_available=bool(retrieval_results.get('sql_results')),
            vector_results_available=bool(retrieval_results.get('vector_results')),
            iterations=iteration
        )
        self.last_reflection = reflection
        
        logger.info(f"Reflection Feedback: {reflection.feedback.value}")
        
        if not reflection.requires_refinement or reflection.confidence < 0.5:
            logger.info("Response quality sufficient")
            return response
        
        logger.info(f"Refinement needed: {reflection.suggested_action}")
        
        refinement_prompt = f"""Your previous response was: "{response}"

Feedback: {reflection.reasoning}
Suggested action: {reflection.suggested_action}

Original query: {query}

Please provide an improved response."""
        
        try:
            refined = await self.agent.arun(refinement_prompt)
            return await self._reflection_loop(
                query, refined, retrieval_results, iteration + 1
            )
        except Exception as e:
            logger.warning(f"Refinement failed: {e}")
            return response
    
    def get_diagnostic_info(self) -> Dict[str, Any]:
        """Get diagnostic information."""
        return {
            'last_routing': {
                'route_type': self.last_query_analysis.route_type.value if self.last_query_analysis else None,
                'confidence': self.last_query_analysis.confidence if self.last_query_analysis else None,
                'reasoning': self.last_query_analysis.reasoning if self.last_query_analysis else None
            },
            'last_reflection': {
                'feedback': self.last_reflection.feedback.value if self.last_reflection else None,
                'confidence': self.last_reflection.confidence if self.last_reflection else None,
                'reasoning': self.last_reflection.reasoning if self.last_reflection else None
            },
            'retrieval_strategy': self.last_retrieval_results.get('strategy')
        }
    
    def get_tools_description(self) -> List[Dict[str, str]]:
        """Get available tools."""
        return [
            {'name': tool.name, 'description': tool.description} for tool in self.tools
        ]
    
    def close(self):
        """Clean up resources."""
        self.db_tools.close()


# Backward compatibility aliases
AgenticRAGAgent = UnifiedAgent
MCPAgentOrchestrator = UnifiedAgent
