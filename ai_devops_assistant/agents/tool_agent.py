"""Multi-agent orchestration system for complex DevOps tasks."""

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional

from ai_devops_assistant.agents.agent import AgentConfig, AgentResponse, AgentRole, AgentTask, DevOpsAgent

logger = logging.getLogger(__name__)


@dataclass
class AgentOrchestrationResult:
    """Result of multi-agent orchestration."""
    primary_response: AgentResponse
    specialist_contributions: Dict[str, AgentResponse] = field(default_factory=dict)
    coordination_steps: List[str] = field(default_factory=list)
    final_consensus: Optional[str] = None
    execution_time: float = 0.0


class AgentOrchestrator:
    """Orchestrates multiple AI agents for complex DevOps operations."""

    def __init__(self):
        """Initialize orchestrator."""
        self.agents: Dict[AgentRole, DevOpsAgent] = {}
        self.task_history: List[Dict[str, Any]] = []

    async def initialize_agents(self, session=None) -> None:
        """Initialize all specialist agents."""
        roles_to_initialize = [
            AgentRole.GENERAL,
            AgentRole.DEVOPS,
            AgentRole.SECURITY,
            AgentRole.MONITORING,
            AgentRole.DATABASE,
            AgentRole.INFRASTRUCTURE,
        ]

        for role in roles_to_initialize:
            config = AgentConfig(
                role=role,
                capabilities=[
                    "tool_use", "rag_retrieval", "analysis",
                    "planning", "execution"
                ]
            )
            agent = DevOpsAgent(config, session)
            await agent.initialize()
            self.agents[role] = agent

        logger.info(f"Initialized {len(self.agents)} specialist agents")

    async def orchestrate_task(
        self,
        task_description: str,
        primary_role: AgentRole = AgentRole.GENERAL,
        require_collaboration: bool = False,
        collaboration_roles: Optional[List[AgentRole]] = None,
    ) -> AgentOrchestrationResult:
        """Orchestrate task execution across multiple agents.

        Args:
            task_description: Description of the task to execute
            primary_role: Primary agent role for the task
            require_collaboration: Whether to involve multiple agents
            collaboration_roles: Specific roles to collaborate with

        Returns:
            Orchestration result with responses from all involved agents
        """
        start_time = asyncio.get_event_loop().time()

        try:
            # Create main task
            task = AgentTask(description=task_description)
            coordination_steps = []

            # Determine which agents to involve
            involved_roles = [primary_role]
            if require_collaboration:
                if collaboration_roles:
                    involved_roles.extend(collaboration_roles)
                else:
                    # Auto-determine collaboration based on task analysis
                    involved_roles.extend(await self._analyze_task_requirements(task))

            # Remove duplicates
            involved_roles = list(set(involved_roles))
            coordination_steps.append(f"Involved agents: {[r.value for r in involved_roles]}")

            # Execute with primary agent
            primary_agent = self.agents.get(primary_role)
            if not primary_agent:
                raise ValueError(f"Primary agent {primary_role.value} not initialized")

            primary_response = await primary_agent._execute_task(task)
            coordination_steps.append(f"Primary agent ({primary_role.value}) completed task")

            specialist_contributions = {}

            # Get contributions from other agents if collaboration required
            if len(involved_roles) > 1:
                collaboration_tasks = []
                for role in involved_roles[1:]:  # Skip primary
                    agent = self.agents.get(role)
                    if agent:
                        # Create specialized task for this agent
                        specialized_task = AgentTask(
                            description=f"Provide {role.value} perspective on: {task_description}",
                            context={"primary_response": primary_response.content}
                        )
                        collaboration_tasks.append(self._get_agent_contribution(agent, specialized_task, role))

                # Execute collaborations concurrently
                if collaboration_tasks:
                    collaboration_results = await asyncio.gather(*collaboration_tasks, return_exceptions=True)

                    for i, result in enumerate(collaboration_results):
                        role = involved_roles[i + 1]  # +1 to skip primary
                        if isinstance(result, Exception):
                            logger.error(f"Collaboration with {role.value} failed: {result}")
                            specialist_contributions[role.value] = AgentResponse(
                                content=f"Collaboration failed: {str(result)}",
                                confidence_score=0.0
                            )
                        else:
                            specialist_contributions[role.value] = result

                    coordination_steps.append(f"Collected contributions from {len(specialist_contributions)} specialists")

            # Generate consensus if multiple agents involved
            final_consensus = None
            if len(involved_roles) > 1:
                final_consensus = await self._generate_consensus(
                    primary_response,
                    specialist_contributions,
                    task_description
                )
                coordination_steps.append("Generated consensus from multiple perspectives")

            execution_time = asyncio.get_event_loop().time() - start_time

            result = AgentOrchestrationResult(
                primary_response=primary_response,
                specialist_contributions=specialist_contributions,
                coordination_steps=coordination_steps,
                final_consensus=final_consensus,
                execution_time=execution_time,
            )

            # Record in history
            self.task_history.append({
                "task": task_description,
                "involved_roles": [r.value for r in involved_roles],
                "execution_time": execution_time,
                "success": True,
            })

            return result

        except Exception as e:
            execution_time = asyncio.get_event_loop().time() - start_time
            logger.error(f"Task orchestration failed: {e}")

            # Record failure
            self.task_history.append({
                "task": task_description,
                "error": str(e),
                "execution_time": execution_time,
                "success": False,
            })

            raise

    async def _analyze_task_requirements(self, task: AgentTask) -> List[AgentRole]:
        """Analyze task requirements to determine which specialists to involve."""
        # Simple keyword-based analysis (could be enhanced with LLM)
        description_lower = task.description.lower()

        specialists = []

        # Security-related keywords
        if any(word in description_lower for word in ["security", "vulnerability", "auth", "access", "encrypt"]):
            specialists.append(AgentRole.SECURITY)

        # Monitoring-related keywords
        if any(word in description_lower for word in ["monitor", "metrics", "alert", "log", "performance"]):
            specialists.append(AgentRole.MONITORING)

        # Database-related keywords
        if any(word in description_lower for word in ["database", "sql", "query", "table", "data"]):
            specialists.append(AgentRole.DATABASE)

        # Infrastructure-related keywords
        if any(word in description_lower for word in ["infra", "kubernetes", "docker", "cloud", "network"]):
            specialists.append(AgentRole.INFRASTRUCTURE)

        # DevOps-related keywords (catch-all for DevOps agent)
        if any(word in description_lower for word in ["deploy", "pipeline", "ci/cd", "build", "release"]):
            specialists.append(AgentRole.DEVOPS)

        return specialists

    async def _get_agent_contribution(
        self,
        agent: DevOpsAgent,
        task: AgentTask,
        role: AgentRole
    ) -> AgentResponse:
        """Get contribution from a specialist agent."""
        return await agent._execute_task(task)

    async def _generate_consensus(
        self,
        primary_response: AgentResponse,
        specialist_contributions: Dict[str, AgentResponse],
        original_task: str
    ) -> str:
        """Generate a consensus response from multiple agent perspectives."""
        # Use the general agent to synthesize responses
        general_agent = self.agents.get(AgentRole.GENERAL)
        if not general_agent:
            return primary_response.content

        # Build consensus prompt
        contributions_text = "\n".join([
            f"{role}: {response.content}"
            for role, response in specialist_contributions.items()
        ])

        consensus_prompt = f"""
        Synthesize a comprehensive response by combining insights from multiple specialists.

        Original Task: {original_task}

        Primary Response: {primary_response.content}

        Specialist Contributions:
        {contributions_text}

        Create a unified, well-structured response that incorporates the best insights from all perspectives.
        Resolve any conflicts and ensure the response is practical and actionable.
        """

        try:
            consensus_response = await general_agent.llm_service.generate(
                consensus_prompt,
                temperature=0.3,  # Lower temperature for consensus
                max_tokens=2048
            )
            return consensus_response
        except Exception as e:
            logger.error(f"Consensus generation failed: {e}")
            return primary_response.content

    def get_orchestration_stats(self) -> Dict[str, Any]:
        """Get statistics about orchestration performance."""
        if not self.task_history:
            return {"total_tasks": 0}

        successful_tasks = [t for t in self.task_history if t.get("success", False)]
        failed_tasks = [t for t in self.task_history if not t.get("success", False)]

        avg_execution_time = sum(t["execution_time"] for t in successful_tasks) / len(successful_tasks) if successful_tasks else 0

        # Count role usage
        role_usage = {}
        for task in self.task_history:
            for role in task.get("involved_roles", []):
                role_usage[role] = role_usage.get(role, 0) + 1

        return {
            "total_tasks": len(self.task_history),
            "successful_tasks": len(successful_tasks),
            "failed_tasks": len(failed_tasks),
            "success_rate": len(successful_tasks) / len(self.task_history) if self.task_history else 0,
            "average_execution_time": avg_execution_time,
            "role_usage": role_usage,
        }


# Convenience functions for common orchestration patterns
async def orchestrate_devops_task(
    task_description: str,
    require_security_review: bool = False,
    require_monitoring_setup: bool = False,
) -> AgentOrchestrationResult:
    """Convenience function for DevOps task orchestration."""
    orchestrator = AgentOrchestrator()
    await orchestrator.initialize_agents()

    collaboration_roles = [AgentRole.DEVOPS]
    if require_security_review:
        collaboration_roles.append(AgentRole.SECURITY)
    if require_monitoring_setup:
        collaboration_roles.append(AgentRole.MONITORING)

    return await orchestrator.orchestrate_task(
        task_description=task_description,
        primary_role=AgentRole.DEVOPS,
        require_collaboration=True,
        collaboration_roles=collaboration_roles,
    )


async def orchestrate_security_audit(
    target_description: str,
) -> AgentOrchestrationResult:
    """Convenience function for security audit orchestration."""
    orchestrator = AgentOrchestrator()
    await orchestrator.initialize_agents()

    return await orchestrator.orchestrate_task(
        task_description=f"Perform comprehensive security audit of: {target_description}",
        primary_role=AgentRole.SECURITY,
        require_collaboration=True,
        collaboration_roles=[AgentRole.INFRASTRUCTURE, AgentRole.DATABASE],
    )


async def orchestrate_infrastructure_deployment(
    deployment_description: str,
) -> AgentOrchestrationResult:
    """Convenience function for infrastructure deployment orchestration."""
    orchestrator = AgentOrchestrator()
    await orchestrator.initialize_agents()

    return await orchestrator.orchestrate_task(
        task_description=f"Plan and execute infrastructure deployment: {deployment_description}",
        primary_role=AgentRole.INFRASTRUCTURE,
        require_collaboration=True,
        collaboration_roles=[AgentRole.DEVOPS, AgentRole.SECURITY, AgentRole.MONITORING],
    )
