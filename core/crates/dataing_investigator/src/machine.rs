//! State machine for investigation workflow.
//!
//! The Investigator struct manages state transitions based on events
//! and produces intents for the runtime to execute.
//!
//! # Design Principles
//!
//! - **Total**: All state transitions are explicit; illegal transitions produce errors
//! - **Deterministic**: Same events always produce the same state
//! - **Side-effect free**: All side effects happen outside the state machine

use serde_json::{json, Value};

use crate::domain::{CallKind, CallMeta};
use crate::protocol::{Event, Intent};
use crate::state::{Phase, State};

/// Error returned when an unexpected call_id is received.
#[derive(Debug, Clone, PartialEq)]
pub struct UnexpectedCallError {
    /// The call_id that was received.
    pub received: String,
    /// The call_id that was expected, if any.
    pub expected: Option<String>,
    /// Current phase when the error occurred.
    pub phase: String,
}

impl std::fmt::Display for UnexpectedCallError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match &self.expected {
            Some(exp) => write!(
                f,
                "Unexpected call_id '{}' (expected '{}') in phase {}",
                self.received, exp, self.phase
            ),
            None => write!(
                f,
                "Unexpected call_id '{}' in phase {} (no call expected)",
                self.received, self.phase
            ),
        }
    }
}

/// Investigation state machine.
///
/// Manages the investigation workflow by processing events and
/// producing intents. All state is contained within the struct
/// and can be serialized/restored for checkpointing.
///
/// # Example
///
/// ```
/// use dataing_investigator::machine::Investigator;
/// use dataing_investigator::protocol::{Event, Intent};
/// use dataing_investigator::domain::Scope;
/// use std::collections::BTreeMap;
///
/// let mut inv = Investigator::new();
///
/// // Start investigation
/// let intent = inv.ingest(Some(Event::Start {
///     objective: "Find null spike".to_string(),
///     scope: Scope {
///         user_id: "u1".to_string(),
///         tenant_id: "t1".to_string(),
///         permissions: vec![],
///         extra: BTreeMap::new(),
///     },
/// }));
///
/// // Returns intent to gather context
/// match intent {
///     Intent::Call { kind, .. } => assert!(matches!(kind, dataing_investigator::CallKind::Tool)),
///     _ => panic!("Expected Call intent"),
/// }
/// ```
#[derive(Debug, Clone)]
pub struct Investigator {
    state: State,
}

impl Default for Investigator {
    fn default() -> Self {
        Self::new()
    }
}

impl Investigator {
    /// Create a new investigator in initial state.
    #[must_use]
    pub fn new() -> Self {
        Self {
            state: State::new(),
        }
    }

    /// Restore an investigator from a saved state snapshot.
    #[must_use]
    pub fn restore(state: State) -> Self {
        Self { state }
    }

    /// Get a clone of the current state for persistence.
    #[must_use]
    pub fn snapshot(&self) -> State {
        self.state.clone()
    }

    /// Process an optional event and return the next intent.
    ///
    /// If an event is provided, it is applied to the state and the
    /// logical clock is incremented. Then the machine decides what
    /// intent to emit based on the current state.
    ///
    /// Passing `None` allows querying the current intent without
    /// providing new input (useful for initial startup).
    pub fn ingest(&mut self, event: Option<Event>) -> Intent {
        if let Some(e) = event {
            self.state.advance_step();
            self.apply(e);
        }
        self.decide()
    }

    /// Apply an event to update the state.
    fn apply(&mut self, event: Event) {
        match event {
            Event::Start { objective, scope } => {
                self.apply_start(objective, scope);
            }
            Event::CallResult { call_id, output } => {
                self.apply_call_result(&call_id, output);
            }
            Event::UserResponse { content } => {
                self.apply_user_response(&content);
            }
            Event::Cancel => {
                self.apply_cancel();
            }
        }
    }

    /// Apply Start event.
    fn apply_start(&mut self, objective: String, scope: crate::domain::Scope) {
        match &self.state.phase {
            Phase::Init => {
                self.state.objective = Some(objective);
                self.state.scope = Some(scope);
                self.state.phase = Phase::GatheringContext {
                    schema_call_id: None,
                };
            }
            _ => {
                // Start event in non-Init phase is an error
                self.state.phase = Phase::Failed {
                    error: format!(
                        "Received Start event in phase {:?}",
                        phase_name(&self.state.phase)
                    ),
                };
            }
        }
    }

    /// Apply CallResult event.
    fn apply_call_result(&mut self, call_id: &str, output: Value) {
        match &self.state.phase {
            Phase::GatheringContext { schema_call_id } => {
                if let Some(expected) = schema_call_id {
                    if call_id == expected {
                        // Store schema in evidence
                        self.state
                            .evidence
                            .insert("schema".to_string(), output.clone());
                        // Transition to hypothesis generation
                        self.state.phase = Phase::GeneratingHypotheses { llm_call_id: None };
                    } else {
                        self.transition_to_unexpected_call_error(call_id, Some(expected.clone()));
                    }
                } else {
                    self.transition_to_unexpected_call_error(call_id, None);
                }
            }
            Phase::GeneratingHypotheses { llm_call_id } => {
                if let Some(expected) = llm_call_id {
                    if call_id == expected {
                        // Store hypotheses in evidence
                        self.state
                            .evidence
                            .insert("hypotheses".to_string(), output.clone());
                        // Transition to evaluating hypotheses
                        self.state.phase = Phase::EvaluatingHypotheses {
                            pending_call_ids: vec![],
                        };
                    } else {
                        self.transition_to_unexpected_call_error(call_id, Some(expected.clone()));
                    }
                } else {
                    self.transition_to_unexpected_call_error(call_id, None);
                }
            }
            Phase::EvaluatingHypotheses { pending_call_ids } => {
                if pending_call_ids.contains(&call_id.to_string()) {
                    // Store evidence for this hypothesis
                    self.state
                        .evidence
                        .insert(format!("eval_{}", call_id), output.clone());

                    // Remove from pending
                    let mut new_pending = pending_call_ids.clone();
                    new_pending.retain(|id| id != call_id);

                    if new_pending.is_empty() {
                        // All evaluations complete, move to synthesis
                        self.state.phase = Phase::Synthesizing {
                            synthesis_call_id: None,
                        };
                    } else {
                        self.state.phase = Phase::EvaluatingHypotheses {
                            pending_call_ids: new_pending,
                        };
                    }
                } else {
                    // Unexpected call_id - not in pending list
                    let expected = pending_call_ids.first().cloned();
                    self.transition_to_unexpected_call_error(call_id, expected);
                }
            }
            Phase::Synthesizing { synthesis_call_id } => {
                if let Some(expected) = synthesis_call_id {
                    if call_id == expected {
                        // Extract insight from output
                        let insight = output
                            .get("insight")
                            .and_then(|v| v.as_str())
                            .unwrap_or("Investigation complete")
                            .to_string();
                        self.state.phase = Phase::Finished { insight };
                    } else {
                        self.transition_to_unexpected_call_error(call_id, Some(expected.clone()));
                    }
                } else {
                    self.transition_to_unexpected_call_error(call_id, None);
                }
            }
            Phase::Init | Phase::AwaitingUser { .. } | Phase::Finished { .. } | Phase::Failed { .. } => {
                // CallResult in these phases is unexpected
                self.transition_to_unexpected_call_error(call_id, None);
            }
        }
    }

    /// Apply UserResponse event.
    fn apply_user_response(&mut self, content: &str) {
        match &self.state.phase {
            Phase::AwaitingUser { question: _ } => {
                // Store user response and continue
                self.state.evidence.insert(
                    format!("user_response_{}", self.state.step),
                    json!(content),
                );
                // For now, user responses continue the investigation
                // The specific next phase depends on context
                self.state.phase = Phase::Synthesizing {
                    synthesis_call_id: None,
                };
            }
            _ => {
                // UserResponse in non-awaiting phase
                self.state.phase = Phase::Failed {
                    error: format!(
                        "Received UserResponse in phase {}",
                        phase_name(&self.state.phase)
                    ),
                };
            }
        }
    }

    /// Apply Cancel event.
    fn apply_cancel(&mut self) {
        match &self.state.phase {
            Phase::Finished { .. } | Phase::Failed { .. } => {
                // Already terminal, ignore cancel
            }
            _ => {
                self.state.phase = Phase::Failed {
                    error: "Investigation cancelled by user".to_string(),
                };
            }
        }
    }

    /// Transition to Failed phase due to unexpected call_id.
    fn transition_to_unexpected_call_error(&mut self, received: &str, expected: Option<String>) {
        let err = UnexpectedCallError {
            received: received.to_string(),
            expected,
            phase: phase_name(&self.state.phase),
        };
        self.state.phase = Phase::Failed {
            error: err.to_string(),
        };
    }

    /// Decide what intent to emit based on current state.
    fn decide(&mut self) -> Intent {
        match &self.state.phase {
            Phase::Init => Intent::Idle,

            Phase::GatheringContext { schema_call_id } => {
                if schema_call_id.is_some() {
                    // Already waiting for schema
                    Intent::Idle
                } else {
                    // Need to request schema
                    let call_id = self.state.generate_id("call");
                    self.record_meta(&call_id, "get_schema", CallKind::Tool, "gathering_context");
                    self.state.phase = Phase::GatheringContext {
                        schema_call_id: Some(call_id.clone()),
                    };
                    Intent::Call {
                        call_id,
                        kind: CallKind::Tool,
                        name: "get_schema".to_string(),
                        args: json!({
                            "objective": self.state.objective.clone().unwrap_or_default()
                        }),
                        reasoning: "Need to gather schema context for the investigation".to_string(),
                    }
                }
            }

            Phase::GeneratingHypotheses { llm_call_id } => {
                if llm_call_id.is_some() {
                    Intent::Idle
                } else {
                    let call_id = self.state.generate_id("call");
                    self.record_meta(
                        &call_id,
                        "generate_hypotheses",
                        CallKind::Llm,
                        "generating_hypotheses",
                    );
                    self.state.phase = Phase::GeneratingHypotheses {
                        llm_call_id: Some(call_id.clone()),
                    };
                    Intent::Call {
                        call_id,
                        kind: CallKind::Llm,
                        name: "generate_hypotheses".to_string(),
                        args: json!({
                            "objective": self.state.objective.clone().unwrap_or_default(),
                            "schema": self.state.evidence.get("schema").cloned().unwrap_or(Value::Null)
                        }),
                        reasoning: "Generate hypotheses based on schema context".to_string(),
                    }
                }
            }

            Phase::EvaluatingHypotheses { pending_call_ids } => {
                if pending_call_ids.is_empty() {
                    // Need to start evaluations
                    let hypotheses = self
                        .state
                        .evidence
                        .get("hypotheses")
                        .cloned()
                        .unwrap_or(Value::Null);

                    // Extract hypothesis IDs or generate based on count
                    let hyp_count = hypotheses
                        .as_array()
                        .map(|a| a.len())
                        .unwrap_or(1)
                        .min(5); // Cap at 5 hypotheses

                    if hyp_count == 0 {
                        // No hypotheses, skip to synthesis
                        self.state.phase = Phase::Synthesizing {
                            synthesis_call_id: None,
                        };
                        return self.decide();
                    }

                    let mut new_pending = Vec::new();
                    for i in 0..hyp_count {
                        let call_id = self.state.generate_id("eval");
                        self.record_meta(
                            &call_id,
                            &format!("evaluate_hypothesis_{}", i),
                            CallKind::Tool,
                            "evaluating_hypotheses",
                        );
                        new_pending.push(call_id);
                    }

                    let first_call_id = new_pending[0].clone();
                    self.state.phase = Phase::EvaluatingHypotheses {
                        pending_call_ids: new_pending,
                    };

                    // Return intent for first evaluation
                    Intent::Call {
                        call_id: first_call_id,
                        kind: CallKind::Tool,
                        name: "evaluate_hypothesis".to_string(),
                        args: json!({
                            "hypotheses": hypotheses,
                            "index": 0
                        }),
                        reasoning: "Evaluate hypothesis against data".to_string(),
                    }
                } else {
                    // Waiting for pending evaluations
                    Intent::Idle
                }
            }

            Phase::AwaitingUser { question } => Intent::RequestUser {
                question: question.clone(),
            },

            Phase::Synthesizing { synthesis_call_id } => {
                if synthesis_call_id.is_some() {
                    Intent::Idle
                } else {
                    let call_id = self.state.generate_id("call");
                    self.record_meta(&call_id, "synthesize", CallKind::Llm, "synthesizing");
                    self.state.phase = Phase::Synthesizing {
                        synthesis_call_id: Some(call_id.clone()),
                    };
                    Intent::Call {
                        call_id,
                        kind: CallKind::Llm,
                        name: "synthesize".to_string(),
                        args: json!({
                            "evidence": self.state.evidence.clone()
                        }),
                        reasoning: "Synthesize findings into final insight".to_string(),
                    }
                }
            }

            Phase::Finished { insight } => Intent::Finish {
                insight: insight.clone(),
            },

            Phase::Failed { error } => Intent::Error {
                message: error.clone(),
            },
        }
    }

    /// Record metadata for a call.
    fn record_meta(&mut self, id: &str, name: &str, kind: CallKind, ctx: &str) {
        let meta = CallMeta {
            id: id.to_string(),
            name: name.to_string(),
            kind,
            phase_context: ctx.to_string(),
            created_at_step: self.state.step,
        };
        self.state.call_index.insert(id.to_string(), meta);
        self.state.call_order.push(id.to_string());
    }
}

/// Get a string name for a phase (for error messages).
fn phase_name(phase: &Phase) -> String {
    match phase {
        Phase::Init => "Init".to_string(),
        Phase::GatheringContext { .. } => "GatheringContext".to_string(),
        Phase::GeneratingHypotheses { .. } => "GeneratingHypotheses".to_string(),
        Phase::EvaluatingHypotheses { .. } => "EvaluatingHypotheses".to_string(),
        Phase::AwaitingUser { .. } => "AwaitingUser".to_string(),
        Phase::Synthesizing { .. } => "Synthesizing".to_string(),
        Phase::Finished { .. } => "Finished".to_string(),
        Phase::Failed { .. } => "Failed".to_string(),
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::Scope;
    use std::collections::BTreeMap;

    fn test_scope() -> Scope {
        Scope {
            user_id: "u1".to_string(),
            tenant_id: "t1".to_string(),
            permissions: vec!["read".to_string()],
            extra: BTreeMap::new(),
        }
    }

    #[test]
    fn test_new_investigator() {
        let inv = Investigator::new();
        let state = inv.snapshot();

        assert_eq!(state.phase, Phase::Init);
        assert_eq!(state.step, 0);
        assert_eq!(state.sequence, 0);
    }

    #[test]
    fn test_restore_and_snapshot() {
        let mut original = State::new();
        original.step = 5;
        original.sequence = 10;
        original.objective = Some("test".to_string());

        let inv = Investigator::restore(original.clone());
        let restored = inv.snapshot();

        assert_eq!(restored.step, 5);
        assert_eq!(restored.sequence, 10);
        assert_eq!(restored.objective, Some("test".to_string()));
    }

    #[test]
    fn test_ingest_increments_step() {
        let mut inv = Investigator::new();
        assert_eq!(inv.snapshot().step, 0);

        inv.ingest(Some(Event::Start {
            objective: "test".to_string(),
            scope: test_scope(),
        }));
        assert_eq!(inv.snapshot().step, 1);
    }

    #[test]
    fn test_ingest_none_does_not_increment() {
        let mut inv = Investigator::new();
        inv.ingest(None);
        assert_eq!(inv.snapshot().step, 0);
    }

    #[test]
    fn test_start_transitions_to_gathering_context() {
        let mut inv = Investigator::new();

        let intent = inv.ingest(Some(Event::Start {
            objective: "Find null spike".to_string(),
            scope: test_scope(),
        }));

        let state = inv.snapshot();
        assert!(matches!(state.phase, Phase::GatheringContext { .. }));
        assert_eq!(state.objective, Some("Find null spike".to_string()));
        assert!(state.scope.is_some());
        assert!(matches!(intent, Intent::Call { kind: CallKind::Tool, .. }));
    }

    #[test]
    fn test_start_in_non_init_phase_fails() {
        let mut inv = Investigator::new();

        // First start
        inv.ingest(Some(Event::Start {
            objective: "test".to_string(),
            scope: test_scope(),
        }));

        // Second start should fail
        let intent = inv.ingest(Some(Event::Start {
            objective: "test2".to_string(),
            scope: test_scope(),
        }));

        assert!(matches!(inv.snapshot().phase, Phase::Failed { .. }));
        assert!(matches!(intent, Intent::Error { .. }));
    }

    #[test]
    fn test_unexpected_call_id_fails() {
        let mut inv = Investigator::new();

        // Start investigation
        inv.ingest(Some(Event::Start {
            objective: "test".to_string(),
            scope: test_scope(),
        }));

        // Get the actual call_id from decide()
        let state = inv.snapshot();
        if let Phase::GatheringContext {
            schema_call_id: Some(expected_id),
        } = &state.phase
        {
            // Send wrong call_id
            let intent = inv.ingest(Some(Event::CallResult {
                call_id: "wrong_id".to_string(),
                output: json!({}),
            }));

            assert!(matches!(inv.snapshot().phase, Phase::Failed { .. }));
            if let Intent::Error { message } = intent {
                assert!(message.contains("wrong_id"));
                assert!(message.contains(expected_id));
            } else {
                panic!("Expected Error intent");
            }
        }
    }

    #[test]
    fn test_call_result_with_no_expected_call_fails() {
        let mut inv = Investigator::new();

        // In Init phase, CallResult should fail
        let intent = inv.ingest(Some(Event::CallResult {
            call_id: "some_id".to_string(),
            output: json!({}),
        }));

        assert!(matches!(inv.snapshot().phase, Phase::Failed { .. }));
        assert!(matches!(intent, Intent::Error { .. }));
    }

    #[test]
    fn test_cancel_transitions_to_failed() {
        let mut inv = Investigator::new();

        inv.ingest(Some(Event::Start {
            objective: "test".to_string(),
            scope: test_scope(),
        }));

        let intent = inv.ingest(Some(Event::Cancel));

        if let Phase::Failed { error } = inv.snapshot().phase {
            assert!(error.contains("cancelled"));
        } else {
            panic!("Expected Failed phase");
        }
        assert!(matches!(intent, Intent::Error { .. }));
    }

    #[test]
    fn test_user_response_in_awaiting_user_phase() {
        let mut state = State::new();
        state.phase = Phase::AwaitingUser {
            question: "Proceed?".to_string(),
        };
        let mut inv = Investigator::restore(state);

        let intent = inv.ingest(Some(Event::UserResponse {
            content: "Yes".to_string(),
        }));

        // Should transition to Synthesizing and emit Call intent
        assert!(matches!(inv.snapshot().phase, Phase::Synthesizing { .. }));
        assert!(matches!(intent, Intent::Call { .. }));
    }

    #[test]
    fn test_user_response_in_wrong_phase_fails() {
        let mut inv = Investigator::new();

        let intent = inv.ingest(Some(Event::UserResponse {
            content: "test".to_string(),
        }));

        assert!(matches!(inv.snapshot().phase, Phase::Failed { .. }));
        assert!(matches!(intent, Intent::Error { .. }));
    }

    #[test]
    fn test_full_workflow_happy_path() {
        let mut inv = Investigator::new();

        // Start
        let intent = inv.ingest(Some(Event::Start {
            objective: "Find null spike".to_string(),
            scope: test_scope(),
        }));

        let call_id_1 = match &intent {
            Intent::Call { call_id, .. } => call_id.clone(),
            _ => panic!("Expected Call intent"),
        };

        // Schema result
        let intent = inv.ingest(Some(Event::CallResult {
            call_id: call_id_1,
            output: json!({"tables": ["orders"]}),
        }));

        assert!(matches!(
            inv.snapshot().phase,
            Phase::GeneratingHypotheses { .. }
        ));

        let call_id_2 = match &intent {
            Intent::Call { call_id, .. } => call_id.clone(),
            _ => panic!("Expected Call intent"),
        };

        // Hypotheses result
        let intent = inv.ingest(Some(Event::CallResult {
            call_id: call_id_2,
            output: json!([{"id": "h1", "title": "ETL failure"}]),
        }));

        assert!(matches!(
            inv.snapshot().phase,
            Phase::EvaluatingHypotheses { .. }
        ));

        let call_id_3 = match &intent {
            Intent::Call { call_id, .. } => call_id.clone(),
            _ => panic!("Expected Call intent"),
        };

        // Evaluation result
        let intent = inv.ingest(Some(Event::CallResult {
            call_id: call_id_3,
            output: json!({"supported": true}),
        }));

        assert!(matches!(inv.snapshot().phase, Phase::Synthesizing { .. }));

        let call_id_4 = match &intent {
            Intent::Call { call_id, .. } => call_id.clone(),
            _ => panic!("Expected Call intent"),
        };

        // Synthesis result
        let intent = inv.ingest(Some(Event::CallResult {
            call_id: call_id_4,
            output: json!({"insight": "Root cause: ETL job failed at 3am"}),
        }));

        assert!(matches!(inv.snapshot().phase, Phase::Finished { .. }));
        if let Intent::Finish { insight } = intent {
            assert!(insight.contains("ETL"));
        } else {
            panic!("Expected Finish intent");
        }
    }

    #[test]
    fn test_call_meta_recorded() {
        let mut inv = Investigator::new();

        inv.ingest(Some(Event::Start {
            objective: "test".to_string(),
            scope: test_scope(),
        }));

        let state = inv.snapshot();
        assert!(!state.call_index.is_empty());
        assert!(!state.call_order.is_empty());

        let first_call = state.call_order.first().expect("should have call");
        let meta = state.call_index.get(first_call).expect("should have meta");
        assert_eq!(meta.name, "get_schema");
        assert!(matches!(meta.kind, CallKind::Tool));
    }

    #[test]
    fn test_decide_returns_idle_in_init() {
        let mut inv = Investigator::new();
        let intent = inv.ingest(None);
        assert!(matches!(intent, Intent::Idle));
    }

    #[test]
    fn test_decide_returns_finish_in_finished() {
        let mut state = State::new();
        state.phase = Phase::Finished {
            insight: "Done".to_string(),
        };
        let mut inv = Investigator::restore(state);

        let intent = inv.ingest(None);
        if let Intent::Finish { insight } = intent {
            assert_eq!(insight, "Done");
        } else {
            panic!("Expected Finish intent");
        }
    }

    #[test]
    fn test_decide_returns_error_in_failed() {
        let mut state = State::new();
        state.phase = Phase::Failed {
            error: "Oops".to_string(),
        };
        let mut inv = Investigator::restore(state);

        let intent = inv.ingest(None);
        if let Intent::Error { message } = intent {
            assert_eq!(message, "Oops");
        } else {
            panic!("Expected Error intent");
        }
    }
}
