from collections.abc import AsyncIterable, Callable, Sequence
from typing import Any, Generic, Literal

from pydantic import BaseModel
from pydantic_ai import Agent, ModelRetry, RunContext
from pydantic_ai.messages import (
    AgentStreamEvent,
    FunctionToolCallEvent,
    FunctionToolResultEvent,
    HandleResponseEvent,
    ModelMessage,
    PartDeltaEvent,
    PartStartEvent,
    TextPart,
    TextPartDelta,
    ThinkingPart,
    ThinkingPartDelta,
)
from pydantic_ai.models import Model
from pydantic_ai.output import OutputDataT, OutputSpec
from pydantic_ai.toolsets import AbstractToolset
from typing_extensions import TypeVar

DepsT = TypeVar("DepsT", default=None)

AgentRetry = ModelRetry


class ToolCallEvent(BaseModel):
    """Structured tool call event for JSON streaming."""

    tool_name: str
    status: Literal["calling", "completed"]
    args: Any | None = None


class StreamHandlers:
    """Encapsulates all streaming event handlers for an agent interaction.

    Args:
        text: Called with text chunks as they arrive from the LLM
        tool_call: Called with (tool_name, status, args) for tool execution events
        thinking: Called with reasoning/thinking text chunks from the LLM
        json_mode: If True, tool_call receives ToolCallEvent objects instead of tuples
    """

    def __init__(
        self,
        text: Callable[[str], None] | None = None,
        tool_call: Callable[[str, Literal["calling", "completed"], Any], None]
        | Callable[[ToolCallEvent], None]
        | None = None,
        thinking: Callable[[str], None] | None = None,
        json_mode: bool = False,
    ):
        self.text = text
        self.tool_call = tool_call
        self.thinking = thinking
        self.json_mode = json_mode

    def has_any(self) -> bool:
        """Check if any handlers are registered."""
        return any([self.text, self.tool_call, self.thinking])

    def emit_tool_call(self, tool_name: str, status: Literal["calling", "completed"], args: Any) -> None:
        """Emit tool call event in appropriate format."""
        if self.tool_call is None:
            return

        if self.json_mode:
            event = ToolCallEvent(tool_name=tool_name, status=status, args=args)
            self.tool_call(event)  # type: ignore
        else:
            self.tool_call(tool_name, status, args)  # type: ignore


class BondAgent(Generic[DepsT, OutputDataT]):
    """AI agent with flexible tool composition and streaming support.

    Built on PydanticAI with enhanced capabilities for building production AI
    agents with tool calling, streaming responses, and dependency injection.

    Args:
        name: Agent identifier for debugging and logging
        instructions: Base system prompt and instructions for the agent
        model: LLM model instance compatible with PydanticAI
        toolsets: Optional sequence of PydanticAI FunctionToolsets for the agent to use
        dependency: Optional dependency object for the toolsets
        output_type: Type specification for structured output (defaults to str)
        max_retries: Maximum number of retries for transient errors

    Examples:
        Basic usage with string output:

        >>> agent = BondAgent(
        ...     name="chat-agent",
        ...     instructions="You are a helpful assistant.",
        ...     model=model,
        ... )
        >>> response = await agent.ask("Hello!")

        Structured output with Pydantic model:

        >>> from pydantic import BaseModel, Field
        >>>
        >>> class Analysis(BaseModel):
        ...     summary: str = Field(description="Brief summary")
        ...     score: float = Field(description="Score from 0-10", ge=0, le=10)
        ...
        >>> agent = BondAgent[None, Analysis](
        ...     name="analyzer",
        ...     instructions="You analyze content and provide structured output.",
        ...     model=model,
        ...     output_type=Analysis,
        ... )
        >>> result = await agent.ask("Analyze this product")

        Dynamic instructions per request:

        >>> agent = BondAgent(
        ...     name="flexible-agent",
        ...     instructions="Base instructions",
        ...     model=model,
        ... )
        >>> response = await agent.ask(
        ...     "Analyze this code",
        ...     dynamic_instructions="You are a senior code reviewer focusing on security.",
        ... )

        Streaming with JSON mode for WebSocket/SSE:

        >>> handlers = StreamHandlers(
        ...     text=lambda chunk: websocket.send_json({"type": "text", "content": chunk}),
        ...     tool_call=lambda event: websocket.send_json({"type": "tool", **event.model_dump()}),
        ...     json_mode=True,
        ... )
        >>> response = await agent.ask("Tell me a story", handlers=handlers)
    """

    def __init__(
        self,
        name: str,
        instructions: str,
        model: Model,
        toolsets: Sequence[AbstractToolset[DepsT]] | None = None,
        dependency: DepsT = None,
        output_type: OutputSpec[OutputDataT] = str,
        max_retries: int = 3,
    ):
        self._base_instructions = instructions
        self._message_history: list[ModelMessage] = []
        self._dependency = dependency

        self._agent = Agent(
            name=name,
            model=model,
            instructions=instructions,
            deps_type=type(dependency),
            toolsets=toolsets,
            output_type=output_type,
            retries=max_retries,
        )

    async def ask(
        self,
        user_prompt: str,
        /,
        *,
        handlers: StreamHandlers | None = None,
        dynamic_instructions: str | None = None,
    ) -> OutputDataT:
        """Ask the agent a question with optional streaming support.

        Args:
            user_prompt: The user prompt to the agent
            handlers: Optional StreamHandlers instance for streaming callbacks
            dynamic_instructions: Override base instructions for this specific request
                Useful for domain-specific orchestrators that need different system
                prompts per operation (e.g., hypothesis generation vs synthesis)

        Returns:
            The complete response from the agent, typed according to output_type

        Examples:
            Simple query:

            >>> response = await agent.ask("What's 2+2?")

            With streaming:

            >>> handlers = StreamHandlers(text=lambda chunk: print(chunk, end=""))
            >>> response = await agent.ask("Tell me a story", handlers=handlers)

            With dynamic instructions (orchestrator pattern):

            >>> response = await agent.ask(
            ...     "Generate 5 hypotheses for this anomaly",
            ...     dynamic_instructions=build_hypothesis_prompt(alert, context),
            ... )

            With all handlers in JSON mode:

            >>> handlers = StreamHandlers(
            ...     text=lambda chunk: buffer.write(chunk),
            ...     tool_call=lambda event: log_tool(event.tool_name, event.status),
            ...     thinking=lambda chunk: debug_log(chunk),
            ...     json_mode=True,
            ... )
            >>> response = await agent.ask("Complex task", handlers=handlers)
        """
        event_stream_handler = (
            self._create_event_stream_handler(handlers) if handlers and handlers.has_any() else None
        )

        # Use dynamic instructions if provided, otherwise fall back to base
        effective_instructions = dynamic_instructions if dynamic_instructions else self._base_instructions

        response = await self._agent.run(
            user_prompt=user_prompt,
            deps=self._dependency,
            message_history=self._message_history,
            event_stream_handler=event_stream_handler,
            instructions=effective_instructions,
        )

        self._message_history = response.all_messages()

        return response.output

    def _create_event_stream_handler(
        self, handlers: StreamHandlers
    ) -> Callable[[RunContext[DepsT], AsyncIterable[AgentStreamEvent | HandleResponseEvent]], None]:
        """Create event stream handler from StreamHandlers configuration."""

        async def event_stream_handler(
            _: RunContext[DepsT],
            event_stream: AsyncIterable[AgentStreamEvent | HandleResponseEvent],
        ) -> None:
            tool_call_registry: dict[str, str] = {}

            async for event in event_stream:
                self._handle_text_events(event, handlers)
                self._handle_thinking_events(event, handlers)
                self._handle_tool_events(event, handlers, tool_call_registry)

        return event_stream_handler

    @staticmethod
    def _handle_text_events(event: AgentStreamEvent | HandleResponseEvent, handlers: StreamHandlers) -> None:
        """Process text streaming events."""
        if handlers.text is None:
            return

        if isinstance(event, PartStartEvent) and isinstance(event.part, TextPart):
            handlers.text(event.part.content)

        if isinstance(event, PartDeltaEvent) and isinstance(event.delta, TextPartDelta):
            handlers.text(event.delta.content_delta)

    @staticmethod
    def _handle_thinking_events(event: AgentStreamEvent | HandleResponseEvent, handlers: StreamHandlers) -> None:
        """Process thinking/reasoning streaming events."""
        if handlers.thinking is None:
            return

        if isinstance(event, PartStartEvent) and isinstance(event.part, ThinkingPart):
            handlers.thinking(event.part.content)

        if isinstance(event, PartDeltaEvent) and isinstance(event.delta, ThinkingPartDelta):
            if event.delta.content_delta is not None:
                handlers.thinking(event.delta.content_delta)

    @staticmethod
    def _handle_tool_events(
        event: AgentStreamEvent | HandleResponseEvent,
        handlers: StreamHandlers,
        tool_call_registry: dict[str, str],
    ) -> None:
        """Process tool call events and maintain call registry."""
        if handlers.tool_call is None:
            return

        if isinstance(event, FunctionToolCallEvent):
            tool_call_registry[event.part.tool_call_id] = event.part.tool_name
            handlers.emit_tool_call(event.part.tool_name, "calling", event.part.args)

        if isinstance(event, FunctionToolResultEvent):
            tool_name = tool_call_registry.get(event.tool_call_id, "unknown")
            handlers.emit_tool_call(tool_name, "completed", None)

    def get_message_history(self) -> list[ModelMessage]:
        """Get the current message history for inspection or persistence."""
        return self._message_history.copy()

    def set_message_history(self, history: list[ModelMessage]) -> None:
        """Set the message history for conversation continuation."""
        self._message_history = history.copy()

    def clear_history(self) -> None:
        """Clear the message history to start fresh."""
        self._message_history = []

    def clone_with_history(self, history: list[ModelMessage]) -> "BondAgent[DepsT, OutputDataT]":
        """Create a new agent instance with copied configuration and specified history.

        Useful for conversation branching or A/B testing different paths.
        """
        new_agent = BondAgent(
            name=self._agent.name,
            instructions=self._base_instructions,
            model=self._agent.model,
            toolsets=self._agent.toolsets,
            dependency=self._dependency,
            output_type=self._agent.output_type,
            max_retries=self._agent.retries,
        )
        new_agent.set_message_history(history)
        return new_agent



from pydantic_ai.models import Model
from pydantic_ai.output import PromptedOutput

from dataing.core.domain_types import (
    AnomalyAlert,
    Evidence,
    Finding,
    Hypothesis,
    InvestigationContext,
)
from dataing.core.exceptions import LLMError
from dataing.agent import BondAgent, StreamHandlers

from .response_models import (
    HypothesesResponse,
    InterpretationResponse,
    QueryResponse,
    SynthesisResponse,
)


class InvestigationOrchestrator:
    """Orchestrates data quality investigation workflows using specialized agents.

    Composes BondAgent instances to provide domain-specific investigation
    capabilities while leveraging infrastructure features like streaming,
    history management, and standardized logging.

    This is the Domain Layer that uses BondAgent (Infrastructure Layer).
    """

    def __init__(
        self,
        model: Model,
        max_retries: int = 3,
    ) -> None:
        """Initialize the investigation orchestrator.

        Args:
            model: PydanticAI-compatible model instance
            max_retries: Max retries on validation failure
        """
        self._model = model
        self._max_retries = max_retries

        self._hypothesis_agent: BondAgent[None, HypothesesResponse] = BondAgent(
            name="hypothesis-generator",
            instructions="You are a data quality investigator.",
            model=self._model,
            output_type=PromptedOutput(HypothesesResponse),
            max_retries=max_retries,
        )

        self._query_agent: BondAgent[None, QueryResponse] = BondAgent(
            name="sql-generator",
            instructions="You are a SQL expert.",
            model=self._model,
            output_type=PromptedOutput(QueryResponse),
            max_retries=max_retries,
        )

        self._interpretation_agent: BondAgent[None, InterpretationResponse] = BondAgent(
            name="evidence-interpreter",
            instructions="You analyze query results.",
            model=self._model,
            output_type=PromptedOutput(InterpretationResponse),
            max_retries=max_retries,
        )

        self._synthesis_agent: BondAgent[None, SynthesisResponse] = BondAgent(
            name="finding-synthesizer",
            instructions="You synthesize investigation findings.",
            model=self._model,
            output_type=PromptedOutput(SynthesisResponse),
            max_retries=max_retries,
        )

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        num_hypotheses: int = 5,
        handlers: StreamHandlers | None = None,
    ) -> list[Hypothesis]:
        """Generate hypotheses for an anomaly.

        Args:
            alert: The anomaly alert to investigate
            context: Available schema and lineage context
            num_hypotheses: Target number of hypotheses
            handlers: Optional streaming handlers for real-time updates

        Returns:
            List of validated Hypothesis objects

        Raises:
            LLMError: If LLM call fails after retries
        """
        system_prompt = self._build_hypothesis_system_prompt(num_hypotheses)
        user_prompt = self._build_hypothesis_user_prompt(alert, context)

        try:
            result = await self._hypothesis_agent.ask(
                user_prompt,
                dynamic_instructions=system_prompt,
                handlers=handlers,
            )

            return [
                Hypothesis(
                    id=h.id,
                    title=h.title,
                    category=h.category,
                    reasoning=h.reasoning,
                    suggested_query=h.suggested_query,
                )
                for h in result.hypotheses
            ]

        except Exception as e:
            raise LLMError(
                f"Hypothesis generation failed: {e}",
                retryable=False,
            ) from e

    async def generate_query(
        self,
        hypothesis: Hypothesis,
        schema: "SchemaResponse",
        previous_error: str | None = None,
        handlers: StreamHandlers | None = None,
    ) -> str:
        """Generate SQL query to test a hypothesis.

        Args:
            hypothesis: The hypothesis to test
            schema: Available database schema
            previous_error: Error from previous attempt (for reflexion)
            handlers: Optional streaming handlers

        Returns:
            Validated SQL query string

        Raises:
            LLMError: If query generation fails
        """
        if previous_error:
            prompt = self._build_reflexion_prompt(hypothesis, previous_error)
            system = self._build_reflexion_system_prompt(schema)
        else:
            prompt = self._build_query_prompt(hypothesis)
            system = self._build_query_system_prompt(schema)

        try:
            result = await self._query_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )
            query: str = result.query
            return query

        except Exception as e:
            raise LLMError(
                f"Query generation failed: {e}",
                retryable=True,
            ) from e

    async def interpret_evidence(
        self,
        hypothesis: Hypothesis,
        query: str,
        results: "QueryResult",
        handlers: StreamHandlers | None = None,
    ) -> Evidence:
        """Interpret query results as evidence.

        Args:
            hypothesis: The hypothesis being tested
            query: The query that was executed
            results: The query results
            handlers: Optional streaming handlers

        Returns:
            Evidence with validated interpretation
        """
        prompt = self._build_interpretation_prompt(hypothesis, query, results)
        system = self._build_interpretation_system_prompt()

        try:
            result = await self._interpretation_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )

            return Evidence(
                hypothesis_id=hypothesis.id,
                query=query,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=result.supports_hypothesis,
                confidence=result.confidence,
                interpretation=result.interpretation,
            )

        except Exception as e:
            return Evidence(
                hypothesis_id=hypothesis.id,
                query=query,
                result_summary=results.to_summary(),
                row_count=results.row_count,
                supports_hypothesis=None,
                confidence=0.3,
                interpretation=f"Interpretation failed: {e}",
            )

    async def synthesize_findings(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
        handlers: StreamHandlers | None = None,
    ) -> Finding:
        """Synthesize all evidence into a root cause finding.

        Args:
            alert: The original anomaly alert
            evidence: All collected evidence
            handlers: Optional streaming handlers

        Returns:
            Finding with validated root cause and recommendations

        Raises:
            LLMError: If synthesis fails
        """
        prompt = self._build_synthesis_prompt(alert, evidence)
        system = self._build_synthesis_system_prompt()

        try:
            result = await self._synthesis_agent.ask(
                prompt,
                dynamic_instructions=system,
                handlers=handlers,
            )

            return Finding(
                investigation_id="",
                status="completed" if result.root_cause else "inconclusive",
                root_cause=result.root_cause,
                confidence=result.confidence,
                evidence=evidence,
                recommendations=result.recommendations,
                duration_seconds=0.0,
            )

        except Exception as e:
            raise LLMError(
                f"Synthesis failed: {e}",
                retryable=False,
            ) from e

    def _build_metric_context(self, alert: AnomalyAlert) -> str:
        """Build context string based on metric_spec type."""
        spec = alert.metric_spec

        if spec.metric_type == "column":
            return f"""The anomaly is on column `{spec.expression}` in table `{alert.dataset_id}`.
Investigate why this column's {alert.anomaly_type} changed.
Focus on: NULL introduction, upstream joins, filtering changes, application bugs.
All hypotheses MUST focus on the `{spec.expression}` column specifically."""

        elif spec.metric_type == "sql_expression":
            cols = ", ".join(spec.columns_referenced) if spec.columns_referenced else "unknown"
            return f"""The anomaly is on a computed metric: {spec.expression}
This expression references columns: {cols}
Investigate why this calculation's result changed.
Focus on: input column changes, expression logic errors, upstream data shifts."""

        elif spec.metric_type == "dbt_metric":
            url_info = f"\nDefinition: {spec.source_url}" if spec.source_url else ""
            return f"""The anomaly is on dbt metric `{spec.expression}`.{url_info}
Investigate the metric's upstream models and their data quality.
Focus on: upstream model failures, source data changes, metric definition issues."""

        else:
            return f"""The anomaly is described as: {spec.expression}
This is a free-text description. Infer which columns/tables are involved
from the schema and investigate accordingly.
Focus on: matching the description to actual schema elements."""

    def _build_hypothesis_system_prompt(self, num_hypotheses: int) -> str:
        """Build system prompt for hypothesis generation."""
        return f"""You are a data quality investigator. Given an anomaly alert and database context,
generate {num_hypotheses} hypotheses about what could have caused the anomaly.

CRITICAL: Pay close attention to the METRIC NAME in the alert:
- "null_count": Investigate what causes NULL values (app bugs, missing required fields, ETL drops)
- "row_count" or "volume": Investigate missing/extra records (filtering bugs, data loss, duplicates)
- "duplicate_count": Investigate what causes duplicate records
- Other metrics: Investigate value changes, data corruption, calculation errors

HYPOTHESIS CATEGORIES:
- upstream_dependency: Source table missing data, late arrival, schema change
- transformation_bug: ETL logic error, incorrect aggregation, wrong join
- data_quality: Nulls, duplicates, invalid values, schema drift
- infrastructure: Job failure, timeout, resource exhaustion
- expected_variance: Seasonality, holiday, known business event

REQUIRED FIELDS FOR EACH HYPOTHESIS:

1. id: Unique identifier like 'h1', 'h2', etc.
2. title: Short, specific title describing the potential cause (10-200 chars)
3. category: One of the categories listed above
4. reasoning: Why this could be the cause (20+ chars)
5. suggested_query: SQL query to investigate (must include LIMIT, SELECT only)
6. expected_if_true: What query results would CONFIRM this hypothesis
7. expected_if_false: What query results would REFUTE this hypothesis

TESTABILITY IS CRITICAL:
- A good hypothesis is FALSIFIABLE
- expected_if_true and expected_if_false should be mutually exclusive
- Avoid vague expectations

Generate diverse hypotheses covering multiple categories when plausible."""

    def _build_hypothesis_user_prompt(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
    ) -> str:
        """Build user prompt for hypothesis generation."""
        lineage_section = ""
        if context.lineage:
            lineage_section = f"""
## Data Lineage
{context.lineage.to_prompt_string()}
"""

        metric_context = self._build_metric_context(alert)

        return f"""## Anomaly Alert
- Dataset: {alert.dataset_id}
- Metric: {alert.metric_spec.display_name}
- Anomaly Type: {alert.anomaly_type}
- Expected: {alert.expected_value}
- Actual: {alert.actual_value}
- Deviation: {alert.deviation_pct}%
- Anomaly Date: {alert.anomaly_date}
- Severity: {alert.severity}

## What To Investigate
{metric_context}

## Available Schema
{context.schema.to_prompt_string()}
{lineage_section}
Generate hypotheses to investigate why {alert.metric_spec.display_name} deviated
from {alert.expected_value} to {alert.actual_value} ({alert.deviation_pct}% change)."""

    def _build_query_system_prompt(self, schema: "SchemaResponse") -> str:
        """Build system prompt for query generation."""
        return f"""You are a SQL expert generating investigative queries.

CRITICAL RULES:
1. Use ONLY tables from the schema: {schema.get_table_names()}
2. Use ONLY columns that exist in those tables
3. SELECT queries ONLY - no mutations
4. Always include LIMIT clause (max 10000)
5. Use fully qualified table names (schema.table)

SCHEMA:
{schema.to_prompt_string()}"""

    def _build_query_prompt(self, hypothesis: Hypothesis) -> str:
        """Build user prompt for query generation."""
        return f"""Generate a SQL query to test this hypothesis:

Hypothesis: {hypothesis.title}
Category: {hypothesis.category.value}
Reasoning: {hypothesis.reasoning}

Generate a query that would confirm or refute this hypothesis."""

    def _build_reflexion_system_prompt(self, schema: "SchemaResponse") -> str:
        """Build system prompt for reflexion (query correction)."""
        return f"""You are debugging a failed SQL query. Analyze the error and fix the query.

AVAILABLE SCHEMA:
{schema.to_prompt_string()}

COMMON FIXES:
- "column does not exist": Check column name spelling, use correct table
- "relation does not exist": Use fully qualified name (schema.table)
- "type mismatch": Cast values appropriately
- "syntax error": Check SQL syntax for the target database

CRITICAL: Only use tables and columns from the schema above."""

    def _build_reflexion_prompt(
        self,
        hypothesis: Hypothesis,
        previous_error: str,
    ) -> str:
        """Build user prompt for reflexion."""
        return f"""The previous query failed. Generate a corrected version.

ORIGINAL QUERY:
{hypothesis.suggested_query}

ERROR MESSAGE:
{previous_error}

HYPOTHESIS BEING TESTED:
{hypothesis.title}

Generate a corrected SQL query that avoids this error."""

    def _build_interpretation_system_prompt(self) -> str:
        """Build system prompt for evidence interpretation."""
        return """You are analyzing query results to determine if they support a hypothesis.

CRITICAL - Understanding "supports hypothesis":
- If investigating NULLs and query FINDS NULLs -> supports=true (we found the problem)
- If investigating NULLs and query finds NO NULLs -> supports=false (not the cause)
- "Supports" means evidence helps explain the anomaly, NOT that the situation is good

IMPORTANT: Do not just confirm that the symptom exists. Your job is to:
1. Identify the TRIGGER (what specific change caused this?)
2. Explain the MECHANISM (how did that trigger lead to this symptom?)
3. Provide TIMELINE (when did each step in the causal chain occur?)

REQUIRED FIELDS:
1. supports_hypothesis: True if evidence supports, False if refutes, None if inconclusive
2. confidence: Score from 0.0 to 1.0
3. interpretation: What the results reveal about the ROOT CAUSE
4. causal_chain: MUST include (1) TRIGGER, (2) MECHANISM, (3) TIMELINE
5. trigger_identified: The specific trigger
6. differentiating_evidence: What points to THIS hypothesis over alternatives
7. key_findings: Specific findings with data points
8. next_investigation_step: REQUIRED if confidence < 0.8 OR trigger_identified is null

Be objective and base your assessment solely on the data returned."""

    def _build_interpretation_prompt(
        self,
        hypothesis: Hypothesis,
        query: str,
        results: "QueryResult",
    ) -> str:
        """Build user prompt for interpretation."""
        return f"""HYPOTHESIS: {hypothesis.title}
REASONING: {hypothesis.reasoning}

QUERY EXECUTED:
{query}

RESULTS ({results.row_count} rows):
{results.to_summary()}

Analyze whether these results support or refute the hypothesis."""

    def _build_synthesis_system_prompt(self) -> str:
        """Build system prompt for synthesis."""
        return """You are synthesizing investigation findings to determine root cause.

CRITICAL: Your root cause MUST directly explain the specific metric anomaly.

REQUIRED FIELDS:

1. root_cause: The UPSTREAM cause, not the symptom (20+ chars, or null if inconclusive)
2. confidence: Score from 0.0 to 1.0
3. causal_chain: Step-by-step list from root cause to observed symptom (2-6 steps)
4. estimated_onset: When the issue started
5. affected_scope: Blast radius - what else is affected
6. supporting_evidence: Specific evidence with data points (1-10 items)
7. recommendations: Actionable items with specific targets (1-5 items)"""

    def _build_synthesis_prompt(
        self,
        alert: AnomalyAlert,
        evidence: list[Evidence],
    ) -> str:
        """Build user prompt for synthesis."""
        evidence_text = "\n\n".join(
            [
                f"""### Hypothesis: {e.hypothesis_id}
- Query: {e.query[:200]}...
- Interpretation: {e.interpretation}
- Confidence: {e.confidence}
- Supports hypothesis: {e.supports_hypothesis}"""
                for e in evidence
            ]
        )

        metric_context = self._build_metric_context(alert)

        return f"""## Original Anomaly
- Dataset: {alert.dataset_id}
- Metric: {alert.metric_spec.display_name} deviated by {alert.deviation_pct}%
- Anomaly Type: {alert.anomaly_type}
- Expected: {alert.expected_value}
- Actual: {alert.actual_value}
- Date: {alert.anomaly_date}

## What Was Investigated
{metric_context}

## Investigation Findings
{evidence_text}

Synthesize these findings into a root cause determination."""



"""Examples demonstrating the layered architecture: BondAgent + InvestigationOrchestrator."""

import asyncio
from typing import Any

from pydantic_ai.models.anthropic import AnthropicModel

from dataing.core.domain_types import AnomalyAlert, InvestigationContext, MetricSpec
from investigation_orchestrator import InvestigationOrchestrator
from dataing.agent import StreamHandlers, ToolCallEvent


async def example_1_basic_investigation():
    """Example 1: Basic autonomous investigation (no streaming)."""
    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model, max_retries=3)

    alert = AnomalyAlert(
        dataset_id="analytics.orders",
        metric_spec=MetricSpec(
            metric_type="column",
            expression="user_id",
            display_name="null_count",
        ),
        anomaly_type="spike",
        expected_value=0.0,
        actual_value=1250.0,
        deviation_pct=125000.0,
        anomaly_date="2024-01-15",
        severity="critical",
    )

    context = InvestigationContext(
        schema=schema_response,
        lineage=lineage_response,
    )

    hypotheses = await orchestrator.generate_hypotheses(alert, context, num_hypotheses=5)

    print(f"Generated {len(hypotheses)} hypotheses:")
    for h in hypotheses:
        print(f"  [{h.id}] {h.title} ({h.category})")


async def example_2_streaming_to_console():
    """Example 2: Stream investigation progress to console."""
    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model)

    alert = create_anomaly_alert()
    context = create_investigation_context()

    handlers = StreamHandlers(
        text=lambda chunk: print(chunk, end="", flush=True),
        thinking=lambda chunk: print(f"[THINKING] {chunk}", flush=True),
        tool_call=lambda name, status, args: print(f"\n[TOOL] {name}: {status}\n", flush=True),
    )

    print("Generating hypotheses with streaming...\n")
    hypotheses = await orchestrator.generate_hypotheses(
        alert,
        context,
        num_hypotheses=5,
        handlers=handlers,
    )

    print(f"\n\nGenerated {len(hypotheses)} hypotheses")


async def example_3_streaming_to_websocket():
    """Example 3: Stream investigation to WebSocket (JSON mode)."""
    from fastapi import WebSocket

    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model)

    async def handle_investigation(websocket: WebSocket):
        await websocket.accept()

        alert = create_anomaly_alert()
        context = create_investigation_context()

        async def send_text(chunk: str) -> None:
            await websocket.send_json({"type": "text", "content": chunk})

        async def send_thinking(chunk: str) -> None:
            await websocket.send_json({"type": "thinking", "content": chunk})

        async def send_tool(event: ToolCallEvent) -> None:
            await websocket.send_json(
                {
                    "type": "tool_call",
                    "tool_name": event.tool_name,
                    "status": event.status,
                    "args": event.args,
                }
            )

        handlers = StreamHandlers(
            text=send_text,
            thinking=send_thinking,
            tool_call=send_tool,
            json_mode=True,
        )

        hypotheses = await orchestrator.generate_hypotheses(
            alert,
            context,
            handlers=handlers,
        )

        await websocket.send_json(
            {
                "type": "complete",
                "hypotheses": [h.model_dump() for h in hypotheses],
            }
        )


async def example_4_full_investigation_pipeline():
    """Example 4: Full investigation pipeline with streaming at each stage."""
    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model)

    alert = create_anomaly_alert()
    context = create_investigation_context()

    console_handlers = StreamHandlers(
        text=lambda chunk: print(chunk, end=""),
        thinking=lambda chunk: print(f"[THINKING] {chunk[:50]}..."),
    )

    print("Stage 1: Generating hypotheses...")
    hypotheses = await orchestrator.generate_hypotheses(
        alert,
        context,
        handlers=console_handlers,
    )
    print(f"\nGenerated {len(hypotheses)} hypotheses\n")

    print("Stage 2: Generating queries...")
    for hypothesis in hypotheses[:3]:
        query = await orchestrator.generate_query(
            hypothesis,
            context.schema,
            handlers=console_handlers,
        )
        print(f"\nQuery for {hypothesis.id}: {query[:100]}...\n")

    print("Stage 3: Interpreting evidence...")
    evidence_list = []
    for hypothesis in hypotheses[:3]:
        query_result = execute_query(hypothesis.suggested_query)
        evidence = await orchestrator.interpret_evidence(
            hypothesis,
            hypothesis.suggested_query,
            query_result,
            handlers=console_handlers,
        )
        evidence_list.append(evidence)
        print(f"\nEvidence for {hypothesis.id}: confidence={evidence.confidence}\n")

    print("Stage 4: Synthesizing findings...")
    finding = await orchestrator.synthesize_findings(
        alert,
        evidence_list,
        handlers=console_handlers,
    )
    print(f"\n\nRoot cause: {finding.root_cause}")
    print(f"Confidence: {finding.confidence}")


async def example_5_custom_streaming_aggregator():
    """Example 5: Custom streaming aggregator that collects and analyzes stream."""

    class StreamingAnalyzer:
        """Analyzes streaming output for quality metrics."""

        def __init__(self):
            self.text_chunks: list[str] = []
            self.thinking_chunks: list[str] = []
            self.tool_calls: list[tuple[str, str]] = []
            self.total_chars = 0
            self.thinking_chars = 0

        def on_text(self, chunk: str) -> None:
            self.text_chunks.append(chunk)
            self.total_chars += len(chunk)

        def on_thinking(self, chunk: str) -> None:
            self.thinking_chunks.append(chunk)
            self.thinking_chars += len(chunk)

        def on_tool_call(self, name: str, status: str, args: Any) -> None:
            self.tool_calls.append((name, status))

        def get_metrics(self) -> dict[str, Any]:
            return {
                "total_text_chunks": len(self.text_chunks),
                "total_thinking_chunks": len(self.thinking_chunks),
                "total_tool_calls": len([t for t in self.tool_calls if t[1] == "completed"]),
                "total_chars": self.total_chars,
                "thinking_chars": self.thinking_chars,
                "thinking_ratio": self.thinking_chars / max(self.total_chars, 1),
            }

    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model)

    alert = create_anomaly_alert()
    context = create_investigation_context()

    analyzer = StreamingAnalyzer()

    handlers = StreamHandlers(
        text=analyzer.on_text,
        thinking=analyzer.on_thinking,
        tool_call=analyzer.on_tool_call,
    )

    hypotheses = await orchestrator.generate_hypotheses(
        alert,
        context,
        handlers=handlers,
    )

    metrics = analyzer.get_metrics()
    print(f"Streaming metrics: {metrics}")
    print(f"Generated {len(hypotheses)} hypotheses")


async def example_6_error_handling_with_reflexion():
    """Example 6: Demonstrate reflexion pattern for query correction."""
    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model)

    alert = create_anomaly_alert()
    context = create_investigation_context()

    hypotheses = await orchestrator.generate_hypotheses(alert, context)
    hypothesis = hypotheses[0]

    max_attempts = 3
    for attempt in range(max_attempts):
        query = await orchestrator.generate_query(
            hypothesis,
            context.schema,
            previous_error=error if attempt > 0 else None,
        )

        try:
            result = execute_query(query)
            print(f"Query succeeded on attempt {attempt + 1}")
            break
        except Exception as e:
            error = str(e)
            print(f"Attempt {attempt + 1} failed: {error}")
            if attempt == max_attempts - 1:
                print("Max attempts reached, giving up")


async def example_7_parallel_hypothesis_testing():
    """Example 7: Test multiple hypotheses in parallel."""
    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model)

    alert = create_anomaly_alert()
    context = create_investigation_context()

    hypotheses = await orchestrator.generate_hypotheses(alert, context)

    async def test_hypothesis(hypothesis):
        """Test a single hypothesis end-to-end."""
        query = await orchestrator.generate_query(hypothesis, context.schema)
        result = execute_query(query)
        evidence = await orchestrator.interpret_evidence(hypothesis, query, result)
        return evidence

    evidence_list = await asyncio.gather(*[test_hypothesis(h) for h in hypotheses[:3]])

    finding = await orchestrator.synthesize_findings(alert, evidence_list)

    print(f"Root cause: {finding.root_cause}")
    print(f"Confidence: {finding.confidence}")


async def example_8_monitoring_and_observability():
    """Example 8: Add comprehensive monitoring to investigation."""
    import time

    class InvestigationMonitor:
        """Monitor investigation progress and performance."""

        def __init__(self):
            self.stage_timings: dict[str, float] = {}
            self.stage_start: float | None = None
            self.current_stage: str | None = None

        def start_stage(self, stage: str) -> None:
            if self.current_stage:
                self.end_stage()
            self.current_stage = stage
            self.stage_start = time.time()
            print(f"\n=== Starting: {stage} ===")

        def end_stage(self) -> None:
            if self.current_stage and self.stage_start:
                duration = time.time() - self.stage_start
                self.stage_timings[self.current_stage] = duration
                print(f"=== Completed: {self.current_stage} ({duration:.2f}s) ===\n")
                self.current_stage = None
                self.stage_start = None

        def get_summary(self) -> dict[str, Any]:
            return {
                "total_duration": sum(self.stage_timings.values()),
                "stage_timings": self.stage_timings,
                "slowest_stage": max(self.stage_timings.items(), key=lambda x: x[1]),
            }

    model = AnthropicModel("claude-sonnet-4-20250514")
    orchestrator = InvestigationOrchestrator(model=model)
    monitor = InvestigationMonitor()

    alert = create_anomaly_alert()
    context = create_investigation_context()

    monitor.start_stage("hypothesis_generation")
    hypotheses = await orchestrator.generate_hypotheses(alert, context)
    monitor.end_stage()

    monitor.start_stage("query_generation")
    queries = []
    for h in hypotheses[:3]:
        query = await orchestrator.generate_query(h, context.schema)
        queries.append(query)
    monitor.end_stage()

    monitor.start_stage("evidence_interpretation")
    evidence_list = []
    for h, q in zip(hypotheses[:3], queries):
        result = execute_query(q)
        evidence = await orchestrator.interpret_evidence(h, q, result)
        evidence_list.append(evidence)
    monitor.end_stage()

    monitor.start_stage("finding_synthesis")
    finding = await orchestrator.synthesize_findings(alert, evidence_list)
    monitor.end_stage()

    summary = monitor.get_summary()
    print(f"\nInvestigation Summary:")
    print(f"  Total duration: {summary['total_duration']:.2f}s")
    print(f"  Slowest stage: {summary['slowest_stage'][0]} ({summary['slowest_stage'][1]:.2f}s)")


def create_anomaly_alert() -> AnomalyAlert:
    """Helper to create example anomaly alert."""
    return AnomalyAlert(
        dataset_id="analytics.orders",
        metric_spec=MetricSpec(
            metric_type="column",
            expression="user_id",
            display_name="null_count",
        ),
        anomaly_type="spike",
        expected_value=0.0,
        actual_value=1250.0,
        deviation_pct=125000.0,
        anomaly_date="2024-01-15",
        severity="critical",
    )


def create_investigation_context() -> InvestigationContext:
    """Helper to create example investigation context."""
    pass


def execute_query(query: str):
    """Helper to execute SQL query."""
    pass


if __name__ == "__main__":
    asyncio.run(example_2_streaming_to_console())



# Architecture Analysis: Infrastructure + Domain Layer Composition

## The LLM Was Absolutely Right

The feedback correctly identified that you have **two complementary layers** that should compose, not compete:

### Infrastructure Layer: `BondAgent`
**Purpose:** Generic agent runtime
- Handles *HOW* agents run (streaming, history, retries)
- Domain-agnostic
- Reusable across any use case

### Domain Layer: `InvestigationOrchestrator`
**Purpose:** Data quality investigation logic
- Handles *WHAT* the agent does (hypotheses, SQL, evidence)
- Domain-specific
- Encapsulates investigation expertise

## The Problem You Had

```python
# OLD: AnthropicClient manually instantiates raw pydantic_ai.Agent
class AnthropicClient:
    def __init__(self, api_key: str, model: str):
        self._hypothesis_agent = Agent(...)  # Raw PydanticAI
        self._query_agent = Agent(...)       # Missing your infrastructure
        # ...
```

**Consequences:**
- Domain layer bypassed infrastructure layer
- No streaming support in investigations
- No conversation history management
- Duplicated configuration across both layers
- Can't leverage future BondAgent features

## The Solution: Composition

```python
# NEW: InvestigationOrchestrator composes BondAgent instances
class InvestigationOrchestrator:
    def __init__(self, model: Model):
        self._hypothesis_agent = BondAgent(...)  # Uses your infrastructure
        self._query_agent = BondAgent(...)       # Gets all features
        # ...

    async def generate_hypotheses(
        self,
        alert: AnomalyAlert,
        context: InvestigationContext,
        handlers: StreamHandlers | None = None,  # Now supported!
    ) -> list[Hypothesis]:
        # Use dynamic instructions for domain-specific prompts
        system_prompt = self._build_hypothesis_system_prompt(5)
        user_prompt = self._build_hypothesis_user_prompt(alert, context)

        result = await self._hypothesis_agent.ask(
            user_prompt,
            dynamic_instructions=system_prompt,  # Override per-request
            handlers=handlers,                    # Stream to UI!
        )

        return [Hypothesis(...) for h in result.hypotheses]
```

## Key Architectural Improvements

### 1. Dynamic Instructions Support

**Before:**
```python
# Had to build system prompt into __init__, couldn't change per request
agent = Agent(instructions="You are a data investigator...")
```

**After:**
```python
# Base instructions in __init__, override per operation
agent = BondAgent(
    instructions="You are a data investigator.",  # Base
)

# Different prompts for different operations
result = await agent.ask(
    "Generate hypotheses",
    dynamic_instructions=build_hypothesis_prompt(alert),  # Override
)

result = await agent.ask(
    "Generate SQL",
    dynamic_instructions=build_query_prompt(schema),  # Different override
)
```

**Why This Matters:**
- Same agent instance can serve multiple roles
- Each operation gets optimized prompt engineering
- Your sophisticated prompt builders remain valuable
- Infrastructure stays generic, domain logic stays specific

### 2. StreamHandlers with JSON Mode

**Feature:** `json_mode=True` enables structured streaming for WebSocket/SSE

**Before:**
```python
# Had to implement custom serialization
def on_tool_call(name: str, status: str, args: Any):
    websocket.send(json.dumps({
        "type": "tool_call",
        "name": name,
        "status": status,
        "args": serialize_args(args),
    }))
```

**After:**
```python
# Automatic structured events
handlers = StreamHandlers(
    tool_call=lambda event: websocket.send_json({
        "type": "tool_call",
        **event.model_dump()
    }),
    json_mode=True,  # Receives ToolCallEvent objects
)
```

**Benefits:**
- Type-safe streaming events
- No manual serialization
- Easy WebSocket/SSE integration
- Frontend gets structured data stream

### 3. Streaming Throughout Investigation Pipeline

**Now possible:**
```python
# Stream hypothesis generation to UI
hypotheses = await orchestrator.generate_hypotheses(
    alert,
    context,
    handlers=StreamHandlers(
        text=lambda chunk: websocket.send_text(chunk),
        thinking=lambda chunk: log_thinking(chunk),
    ),
)

# Stream query generation
query = await orchestrator.generate_query(
    hypothesis,
    schema,
    handlers=handlers,
)

# Stream evidence interpretation
evidence = await orchestrator.interpret_evidence(
    hypothesis,
    query,
    result,
    handlers=handlers,
)

# Stream synthesis
finding = await orchestrator.synthesize_findings(
    alert,
    evidence_list,
    handlers=handlers,
)
```

**Impact:**
- Users see investigation progress in real-time
- Better UX for long-running investigations
- Can show "thinking" process (valuable for debugging)
- Tool calls visible (shows SQL being generated/executed)

## What You Keep vs What Changes

### ✅ Keep (These Are Excellent)

**Domain Logic:**
- All your prompt building methods (`_build_hypothesis_system_prompt`, etc.)
- Domain types (AnomalyAlert, Evidence, Finding, Hypothesis)
- Response models (HypothesesResponse, QueryResponse, etc.)
- Investigation workflow orchestration
- Reflexion pattern for query correction

**Why:** This is your core IP and domain expertise.

### 🔄 Change (These Get Better)

**Agent Instantiation:**
```python
# Before
self._hypothesis_agent = Agent(
    model=self._model,
    output_type=PromptedOutput(HypothesesResponse),
    retries=max_retries,
)

# After
self._hypothesis_agent = BondAgent(
    name="hypothesis-generator",
    instructions="You are a data quality investigator.",
    model=self._model,
    output_type=PromptedOutput(HypothesesResponse),
    max_retries=max_retries,
)
```

**Agent Invocation:**
```python
# Before
result = await self._hypothesis_agent.run(
    user_prompt,
    instructions=system_prompt,  # Override
)

# After
result = await self._hypothesis_agent.ask(
    user_prompt,
    dynamic_instructions=system_prompt,  # Override
    handlers=handlers,                    # Now supported!
)
```

**Why:** Same domain logic, better infrastructure.

## Benefits of This Architecture

### For Development
- **Separation of concerns:** Infrastructure vs domain logic
- **Testability:** Mock BondAgent for unit testing orchestrator
- **Maintainability:** Change infrastructure without touching domain
- **Reusability:** BondAgent works for chat, coding, analysis, etc.

### For Production
- **Streaming:** Real-time progress updates to users
- **Monitoring:** Structured events for observability
- **Debugging:** See thinking process, tool calls
- **Scaling:** Conversation history enables multi-session agents

### For DataDr Specifically
- **Autonomous investigations:** Works as-is (no handlers)
- **Interactive debugging:** Add handlers for UI streaming
- **Human-in-the-loop:** Conversation history enables back-and-forth
- **Multi-investigation sessions:** History management per user

## Migration Path

### Phase 1: Parallel Implementation (Week 1)
1. Keep existing `AnthropicClient`
2. Add `InvestigationOrchestrator` using `BondAgent`
3. Run both in production (A/B test)

### Phase 2: Feature Parity (Week 2)
1. Ensure orchestrator matches all client features
2. Add streaming to orchestrator
3. Validate outputs are identical

### Phase 3: Migration (Week 3)
1. Switch DataDr to orchestrator
2. Deprecate `AnthropicClient`
3. Remove old implementation

### Phase 4: Enhancement (Week 4+)
1. Add WebSocket streaming for UI
2. Implement conversation history persistence
3. Build interactive investigation mode

## Code Organization

```
dataing/
├── core/
│   ├── domain_types.py          # AnomalyAlert, Evidence, Finding
│   ├── response_models.py       # HypothesesResponse, etc.
│   └── exceptions.py            # LLMError
├── infrastructure/
│   └── agent.py                 # BondAgent (infrastructure layer)
├── orchestration/
│   └── investigation.py         # InvestigationOrchestrator (domain layer)
└── legacy/
    └── anthropic_client.py      # Old implementation (deprecated)
```

## Example: Full Investigation with Streaming

```python
from dataing.orchestration.investigation import InvestigationOrchestrator
from dataing.infrastructure.agent import StreamHandlers

orchestrator = InvestigationOrchestrator(model=model)

# Setup streaming to WebSocket
handlers = StreamHandlers(
    text=lambda chunk: websocket.send_json({
        "type": "text",
        "content": chunk,
    }),
    thinking=lambda chunk: websocket.send_json({
        "type": "thinking",
        "content": chunk,
    }),
    tool_call=lambda event: websocket.send_json({
        "type": "tool_call",
        **event.model_dump(),
    }),
    json_mode=True,
)

# Run investigation with real-time streaming
hypotheses = await orchestrator.generate_hypotheses(
    alert, context, handlers=handlers
)

for hypothesis in hypotheses[:3]:
    query = await orchestrator.generate_query(
        hypothesis, schema, handlers=handlers
    )

    result = execute_query(query)

    evidence = await orchestrator.interpret_evidence(
        hypothesis, query, result, handlers=handlers
    )

finding = await orchestrator.synthesize_findings(
    alert, evidence_list, handlers=handlers
)

# User saw entire investigation unfold in real-time!
```

## Conclusion

The LLM's feedback was spot-on. You have:

1. **BondAgent** - Generic agent runtime (infrastructure)
2. **InvestigationOrchestrator** - Investigation logic (domain)

They should **compose** via dependency injection, not compete. This gives you:

- Keep your domain expertise (prompts, workflow)
- Gain infrastructure features (streaming, history, monitoring)
- Clear separation of concerns
- Easy to test, maintain, extend

The refactored architecture is production-ready and positions DataDr for interactive investigation modes, UI streaming, and future enhancements.
