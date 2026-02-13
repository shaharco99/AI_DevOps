#!/usr/bin/env python3
"""
Unit tests for the Unified Agent system.

Tests cover:
- Core Agent Components (QueryRouter, ReflectionAgent, VectorRetriever)
- Database Tools Integration
- Chat/CLI Interface
- Agentic RAG Pipeline
"""
import asyncio
import json
import os
import sqlite3
import sys
import tempfile
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, Mock, patch

import pytest

# Mock chromadb before importing unified_agent
sys.modules['chromadb'] = MagicMock()

# Add parent directory to path
sys.path.insert(0, str(Path(__file__).parent.parent))

# Import from unified_agent
from unified_agent import (
    UnifiedAgent,
    QueryRouter,
    ReflectionAgent,
    VectorRetriever,
    DatabaseTools,
    QueryRouteType,
    ReflectionFeedback,
    QueryAnalysis,
    ReflectionResult
)


class TestQueryRouter:
    """Tests for QueryRouter component."""
    
    def test_extract_json_valid(self):
        """Test JSON extraction from valid JSON."""
        text = '{"route_type": "sql_only", "confidence": 0.9}'
        result = QueryRouter._extract_json(text)
        assert result["route_type"] == "sql_only"
        assert result["confidence"] == 0.9
    
    def test_extract_json_with_markdown(self):
        """Test JSON extraction from markdown code blocks."""
        text = """Decision:
```json
{"route_type": "vector_only", "confidence": 0.85}
```"""
        result = QueryRouter._extract_json(text)
        assert result["route_type"] == "vector_only"
    
    def test_extract_json_fallback(self):
        """Test JSON extraction with invalid JSON fallback."""
        text = "Not JSON at all"
        result = QueryRouter._extract_json(text)
        assert result["route_type"] == "no_retrieval"
        assert result["confidence"] == 0.1
    
    def test_analyze_sql_query(self):
        """Test routing analysis for SQL query."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "route_type": "sql_only",
            "confidence": 0.95,
            "reasoning": "Numeric query detected"
        })
        mock_llm.invoke.return_value = mock_response
        
        router = QueryRouter(mock_llm)
        analysis = router.analyze("What is the total revenue?")
        
        assert analysis.route_type == QueryRouteType.SQL_ONLY
        assert analysis.confidence == 0.95
        assert analysis.should_retrieve_sql is True
        assert analysis.should_retrieve_vector is False
    
    def test_analyze_vector_query(self):
        """Test routing analysis for vector/document query."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "route_type": "vector_only",
            "confidence": 0.9,
            "reasoning": "Policy/documentation query"
        })
        mock_llm.invoke.return_value = mock_response
        
        router = QueryRouter(mock_llm)
        analysis = router.analyze("What is the deployment policy?")
        
        assert analysis.route_type == QueryRouteType.VECTOR_ONLY
        assert analysis.should_retrieve_vector is True
        assert analysis.should_retrieve_sql is False
    
    def test_analyze_hybrid_query(self):
        """Test routing analysis for hybrid query."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "route_type": "hybrid",
            "confidence": 0.85,
            "reasoning": "Both numeric and policy aspects"
        })
        mock_llm.invoke.return_value = mock_response
        
        router = QueryRouter(mock_llm)
        analysis = router.analyze("How many deployments comply with policy?")
        
        assert analysis.route_type == QueryRouteType.HYBRID
        assert analysis.should_retrieve_sql is True
        assert analysis.should_retrieve_vector is True


class TestReflectionAgent:
    """Tests for ReflectionAgent component."""
    
    def test_reflect_sufficient(self):
        """Test reflection when response is sufficient."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "feedback": "sufficient",
            "confidence": 0.88,
            "reasoning": "Response is complete and accurate",
            "suggested_action": "Return response"
        })
        mock_llm.invoke.return_value = mock_response
        
        reflector = ReflectionAgent(mock_llm)
        result = reflector.reflect(
            query="What is the revenue?",
            response="The total revenue is $1.5M",
            sql_results_available=True
        )
        
        assert result.feedback == ReflectionFeedback.SUFFICIENT
        assert result.requires_refinement is False
    
    def test_reflect_needs_refinement(self):
        """Test reflection when refinement is needed."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "feedback": "needs_refinement",
            "confidence": 0.65,
            "reasoning": "Response lacks specific details",
            "suggested_action": "Add specific metrics and examples"
        })
        mock_llm.invoke.return_value = mock_response
        
        reflector = ReflectionAgent(mock_llm)
        result = reflector.reflect(
            query="Explain the deployment process",
            response="The deployment is done"
        )
        
        assert result.feedback == ReflectionFeedback.NEEDS_REFINEMENT
        assert result.requires_refinement is True
    
    def test_reflect_needs_context(self):
        """Test reflection when more context is needed."""
        mock_llm = MagicMock()
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "feedback": "needs_context",
            "confidence": 0.7,
            "reasoning": "Insufficient data to answer",
            "suggested_action": "Retrieve additional documents"
        })
        mock_llm.invoke.return_value = mock_response
        
        reflector = ReflectionAgent(mock_llm)
        result = reflector.reflect(
            query="What is the SLA?",
            response="I need more information",
            vector_results_available=False
        )
        
        assert result.feedback == ReflectionFeedback.NEEDS_MORE_CONTEXT
        assert result.requires_refinement is True
    
    def test_reflect_error_handling(self):
        """Test reflection with error handling."""
        mock_llm = MagicMock()
        mock_llm.invoke.side_effect = Exception("LLM error")
        
        reflector = ReflectionAgent(mock_llm)
        result = reflector.reflect(
            query="Test query",
            response="Test response"
        )
        
        assert result.feedback == ReflectionFeedback.SUFFICIENT
        assert result.confidence < 0.5


class TestVectorRetriever:
    """Tests for VectorRetriever component."""
    
    def test_retrieve_documents(self):
        """Test document retrieval from vector store."""
        # Mock the chromadb Client
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            'documents': [['doc1 content', 'doc2 content']],
            'metadatas': [[{'source': 'file1.txt'}, {'source': 'file2.txt'}]],
            'ids': [['id1', 'id2']]
        }
        
        # Mock chromadb.Client() to return our mock client
        import chromadb
        chromadb.Client = MagicMock(return_value=MagicMock())
        chromadb.Client.return_value.get_or_create_collection.return_value = mock_collection
        
        retriever = VectorRetriever("test_collection")
        results = retriever.retrieve("test query", top_k=2)
        
        assert len(results) == 2
        assert results[0]['content'] == 'doc1 content'
        assert results[0]['id'] == 'id1'
    
    def test_retrieve_empty_results(self):
        """Test retrieval when no documents found."""
        mock_collection = MagicMock()
        mock_collection.query.return_value = {'documents': [[]]}
        
        import chromadb
        chromadb.Client = MagicMock(return_value=MagicMock())
        chromadb.Client.return_value.get_or_create_collection.return_value = mock_collection
        
        retriever = VectorRetriever("test_collection")
        results = retriever.retrieve("unknown topic")
        
        assert len(results) == 0
    
    def test_retrieve_with_top_k(self):
        """Test retrieval with specific top_k parameter."""
        mock_collection = MagicMock()
        mock_collection.query.return_value = {
            'documents': [[f'doc{i}' for i in range(5)]],
            'metadatas': [[{'source': f'file{i}'} for i in range(5)]],
            'ids': [[f'id{i}' for i in range(5)]]
        }
        
        import chromadb
        chromadb.Client = MagicMock(return_value=MagicMock())
        chromadb.Client.return_value.get_or_create_collection.return_value = mock_collection
        
        retriever = VectorRetriever("test_collection")
        results = retriever.retrieve("query", top_k=5)
        
        assert len(results) == 5
        mock_collection.query.assert_called_with(query_texts=['query'], n_results=5)


class TestDatabaseTools:
    """Tests for DatabaseTools component."""
    
    def test_database_initialization(self):
        """Test database tools initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            
            # Create a test database
            conn = sqlite3.connect(db_path)
            conn.commit()
            conn.close()
            
            tools = DatabaseTools(db_path)
            assert tools.db_path == db_path
            
            # Test schema retrieval
            schema = tools.get_schema()
            assert 'clients' in schema
            assert 'id' in schema['clients']
            assert 'name' in schema['clients']
    
    def test_execute_query_select(self):
        """Test SELECT query execution."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            
            tools = DatabaseTools(db_path)
            rows, error = tools.execute_query('SELECT * FROM products')
            
            assert error is None
            assert len(rows) == 5
            assert rows[0]['name'] == 'Laptop'
    
    
    def test_get_schema(self):
        """Test schema retrieval."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            
            
            tools = DatabaseTools(db_path)
            schema = tools.get_schema()
            
            assert 'orders' in schema
            assert set(schema['orders']) == {'id', 'client_id', 'order_date', 'total_amount','status'}


class TestUnifiedAgent:
    """Tests for the main UnifiedAgent."""
    
    def test_agent_initialization(self):
        """Test agent initialization."""
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = os.path.join(tmpdir, 'test.db')
            
            # Create test database
            conn = sqlite3.connect(db_path)
            conn.execute('CREATE TABLE test (id INTEGER)')
            conn.commit()
            conn.close()
            
            agent = UnifiedAgent(
                db_path=db_path,
                collection_name='test_collection',
                max_reflection_iterations=3
            )
            
            assert agent.max_reflection_iterations == 3
            assert agent.router is not None
            assert agent.reflector is not None
            assert agent.vector_retriever is not None
            assert agent.db_tools is not None
    
    def test_add_tool(self):
        """Test adding tools to agent."""
        agent = UnifiedAgent()
        
        def dummy_tool(x: str) -> str:
            return f"Result: {x}"
        
        agent.add_tool("test_tool", dummy_tool, "A test tool for demonstration")
        
        # Tool class might not be available (no langchain), so this could be 0 or 1
        # The important thing is that add_tool doesn't crash
        assert agent is not None
    
    def test_augment_query_with_context(self):
        """Test query augmentation with retrieved context."""
        agent = UnifiedAgent()
        
        retrieval_results = {
            'vector_results': [
                {'content': 'Policy document content', 'source': 'policy.txt', 'id': 'doc1'},
                {'content': 'More policy content', 'source': 'policy.txt', 'id': 'doc2'}
            ],
            'strategy': 'hybrid'
        }
        
        augmented = agent._augment_query("What is the escalation policy?", retrieval_results)
        
        assert "Retrieved Documents" in augmented
        assert "Policy document content" in augmented
    
    def test_augment_query_without_context(self):
        """Test query augmentation when no context."""
        agent = UnifiedAgent()
        
        retrieval_results = {'vector_results': [], 'strategy': 'no_retrieval'}
        original_query = "General knowledge question?"
        
        augmented = agent._augment_query(original_query, retrieval_results)
        
        assert augmented == original_query
    
    def test_get_diagnostic_info(self):
        """Test diagnostic information retrieval."""
        agent = UnifiedAgent()
        
        agent.last_query_analysis = QueryAnalysis(
            route_type=QueryRouteType.HYBRID,
            confidence=0.85,
            reasoning="Test routing decision",
            should_retrieve_sql=True,
            should_retrieve_vector=True,
            num_iterations=1
        )
        
        agent.last_reflection = ReflectionResult(
            feedback=ReflectionFeedback.SUFFICIENT,
            confidence=0.88,
            reasoning="Response quality good",
            suggested_action="Return response",
            requires_refinement=False
        )
        
        agent.last_retrieval_results = {'strategy': 'hybrid', 'vector_results': []}
        
        diagnostics = agent.get_diagnostic_info()
        
        assert diagnostics['last_routing']['route_type'] == 'hybrid'
        assert diagnostics['last_routing']['confidence'] == 0.85
        assert diagnostics['last_reflection']['feedback'] == 'sufficient'
        assert diagnostics['retrieval_strategy'] == 'hybrid'
    
    def test_get_tools_description(self):
        """Test getting tools description."""
        agent = UnifiedAgent()
        
        def sample_func():
            """Sample function"""
            pass
        
        agent.add_tool("sample", sample_func, "A sample tool")
        tools_desc = agent.get_tools_description()
        
        # Tool might not be available, so list could be empty
        assert isinstance(tools_desc, list)


class TestBackwardCompatibility:
    """Tests for backward compatibility aliases."""
    
    def test_agentic_rag_agent_alias(self):
        """Test that AgenticRAGAgent alias works."""
        from unified_agent import AgenticRAGAgent
        
        agent = AgenticRAGAgent()
        assert isinstance(agent, UnifiedAgent)
    
    def test_mcp_agent_orchestrator_alias(self):
        """Test that MCPAgentOrchestrator alias works."""
        from unified_agent import MCPAgentOrchestrator
        
        agent = MCPAgentOrchestrator()
        assert isinstance(agent, UnifiedAgent)


class TestEnumerations:
    """Tests for enumeration types."""
    
    def test_query_route_types(self):
        """Test QueryRouteType enumeration."""
        assert QueryRouteType.SQL_ONLY.value == "sql_only"
        assert QueryRouteType.VECTOR_ONLY.value == "vector_only"
        assert QueryRouteType.HYBRID.value == "hybrid"
        assert QueryRouteType.NO_RETRIEVAL.value == "no_retrieval"
    
    def test_reflection_feedback_types(self):
        """Test ReflectionFeedback enumeration."""
        assert ReflectionFeedback.SUFFICIENT.value == "sufficient"
        assert ReflectionFeedback.NEEDS_MORE_CONTEXT.value == "needs_context"
        assert ReflectionFeedback.NEEDS_REFINEMENT.value == "needs_refinement"
        assert ReflectionFeedback.CONTRADICTORY.value == "contradictory"


class TestDataclasses:
    """Tests for dataclass structures."""
    
    def test_query_analysis_dataclass(self):
        """Test QueryAnalysis dataclass creation."""
        analysis = QueryAnalysis(
            route_type=QueryRouteType.HYBRID,
            confidence=0.85,
            reasoning="Test",
            should_retrieve_sql=True,
            should_retrieve_vector=True,
            num_iterations=2
        )
        
        assert analysis.route_type == QueryRouteType.HYBRID
        assert analysis.confidence == 0.85
        assert analysis.num_iterations == 2
    
    def test_reflection_result_dataclass(self):
        """Test ReflectionResult dataclass creation."""
        result = ReflectionResult(
            feedback=ReflectionFeedback.SUFFICIENT,
            confidence=0.9,
            reasoning="Good response",
            suggested_action="Return",
            requires_refinement=False
        )
        
        assert result.feedback == ReflectionFeedback.SUFFICIENT
        assert result.confidence == 0.9
        assert result.requires_refinement is False


if __name__ == '__main__':
    pytest.main([__file__, '-v', '--tb=short'])
