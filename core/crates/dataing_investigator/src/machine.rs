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
//! - **Workflow owns IDs**: The machine never generates call_ids or question_ids
//!
//! # Call Scheduling Handshake
//!
//! When the machine needs to make an external call:
//! 1. Machine emits `Intent::RequestCall { name, kind, args, reasoning }`
//! 2. Workflow generates a call_id and sends `Event::CallScheduled { call_id, name }`
//! 3. Machine stores the call_id and returns `Intent::Idle`
//! 4. Workflow executes the call and sends `Event::CallResult { call_id, output }`
//! 5. Machine processes the result and advances

use serde_json::{json, Value};

use crate::domain::{CallKind, CallMeta};
use crate::protocol::{Envelope, ErrorKind, Event, Intent, MachineError};
use crate::state::{phase_name, PendingCall, Phase, State};
use crate::PROTOCOL_VERSION;

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
/// use dataing_investigator::protocol::{Envelope, Event, Intent};
/// use dataing_investigator::domain::Scope;
/// use std::collections::BTreeMap;
///
/// let mut inv = Investigator::new();
///
/// // Start investigation with envelope
/// let envelope = Envelope {
///     protocol_version: 1,
///     event_id: "evt_001".to_string(),
///     step: 1,
///     event: Event::Start {
///         objective: "Find null spike".to_string(),
///         scope: Scope {
///             user_id: "u1".to_string(),
///             tenant_id: "t1".to_string(),
///             permissions: vec![],
///             extra: BTreeMap::new(),
///         },
///     },
/// };
///
/// let result = inv.ingest(envelope);
/// assert!(result.is_ok());
///
/// // Returns intent to request a call (no call_id yet)
/// match result.unwrap() {
///     Intent::RequestCall { name, .. } => assert_eq!(name, "get_schema"),
///     _ => panic!("Expected RequestCall intent"),
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

    /// Get the current phase name.
    #[must_use]
    pub fn current_phase(&self) -> &'static str {
        phase_name(&self.state.phase)
    }

    /// Get the current step.
    #[must_use]
    pub fn current_step(&self) -> u64 {
        self.state.step
    }

    /// Check if in a terminal state.
    #[must_use]
    pub fn is_terminal(&self) -> bool {
        self.state.is_terminal()
    }

    /// Process an event envelope and return the next intent.
    ///
    /// Validates:
    /// - Protocol version matches
    /// - Event ID is not a duplicate
    /// - Step is monotonically increasing
    ///
    /// On success, applies the event and returns the next intent.
    /// On error, returns a typed MachineError for retry decisions.
    pub fn ingest(&mut self, envelope: Envelope) -> Result<Intent, MachineError> {
        // Validate protocol version
        if envelope.protocol_version != PROTOCOL_VERSION {
            return Err(MachineError::new(
                ErrorKind::ProtocolMismatch,
                format!(
                    "Expected protocol version {}, got {}",
                    PROTOCOL_VERSION, envelope.protocol_version
                ),
            )
            .with_step(envelope.step));
        }

        // Check for duplicate event
        if self.state.is_duplicate_event(&envelope.event_id) {
            // Silently return current intent (idempotency)
            return Ok(self.decide());
        }

        // Validate step monotonicity (must be > current step)
        if envelope.step <= self.state.step {
            return Err(MachineError::new(
                ErrorKind::StepViolation,
                format!(
                    "Step {} is not greater than current step {}",
                    envelope.step, self.state.step
                ),
            )
            .with_phase(self.current_phase())
            .with_step(envelope.step));
        }

        // Mark event as processed and update step
        self.state.mark_event_processed(envelope.event_id);
        self.state.set_step(envelope.step);

        // Apply the event
        self.apply(envelope.event)?;

        // Return the next intent
        Ok(self.decide())
    }

    /// Query the current intent without providing an event.
    ///
    /// Useful for getting the initial intent or checking state.
    #[must_use]
    pub fn query(&self) -> Intent {
        // Create a temporary clone to avoid mutating state
        let mut temp = self.clone();
        temp.decide()
    }

    /// Apply an event to update the state.
    fn apply(&mut self, event: Event) -> Result<(), MachineError> {
        match event {
            Event::Start { objective, scope } => self.apply_start(objective, scope),
            Event::CallScheduled { call_id, name } => self.apply_call_scheduled(&call_id, &name),
            Event::CallResult { call_id, output } => self.apply_call_result(&call_id, output),
            Event::UserResponse {
                question_id,
                content,
            } => self.apply_user_response(&question_id, &content),
            Event::Cancel => {
                self.apply_cancel();
                Ok(())
            }
        }
    }

    /// Apply Start event.
    fn apply_start(
        &mut self,
        objective: String,
        scope: crate::domain::Scope,
    ) -> Result<(), MachineError> {
        match &self.state.phase {
            Phase::Init => {
                self.state.objective = Some(objective);
                self.state.scope = Some(scope);
                self.state.phase = Phase::GatheringContext {
                    pending: None,
                    call_id: None,
                };
                Ok(())
            }
            _ => Err(MachineError::new(
                ErrorKind::InvalidTransition,
                format!(
                    "Received Start event in phase {}",
                    self.current_phase()
                ),
            )
            .with_phase(self.current_phase())
            .with_step(self.state.step)),
        }
    }

    /// Apply CallScheduled event (workflow assigned a call_id).
    fn apply_call_scheduled(&mut self, call_id: &str, name: &str) -> Result<(), MachineError> {
        match &self.state.phase {
            Phase::GatheringContext {
                pending: Some(pending),
                call_id: None,
            } if pending.awaiting_schedule && pending.name == name => {
                // Record the call metadata
                self.record_meta(call_id, name, CallKind::Tool, "gathering_context");
                self.state.phase = Phase::GatheringContext {
                    pending: None,
                    call_id: Some(call_id.to_string()),
                };
                Ok(())
            }
            Phase::GeneratingHypotheses {
                pending: Some(pending),
                call_id: None,
            } if pending.awaiting_schedule && pending.name == name => {
                self.record_meta(call_id, name, CallKind::Llm, "generating_hypotheses");
                self.state.phase = Phase::GeneratingHypotheses {
                    pending: None,
                    call_id: Some(call_id.to_string()),
                };
                Ok(())
            }
            Phase::EvaluatingHypotheses {
                pending: Some(pending),
                awaiting_results,
                total_hypotheses,
                completed,
            } if pending.awaiting_schedule && pending.name == name => {
                // Clone values before mutable operations to satisfy borrow checker
                let mut new_awaiting = awaiting_results.clone();
                new_awaiting.push(call_id.to_string());
                let total = *total_hypotheses;
                let done = *completed;
                self.record_meta(call_id, name, CallKind::Tool, "evaluating_hypotheses");
                self.state.phase = Phase::EvaluatingHypotheses {
                    pending: None,
                    awaiting_results: new_awaiting,
                    total_hypotheses: total,
                    completed: done,
                };
                Ok(())
            }
            Phase::Synthesizing {
                pending: Some(pending),
                call_id: None,
            } if pending.awaiting_schedule && pending.name == name => {
                self.record_meta(call_id, name, CallKind::Llm, "synthesizing");
                self.state.phase = Phase::Synthesizing {
                    pending: None,
                    call_id: Some(call_id.to_string()),
                };
                Ok(())
            }
            _ => Err(MachineError::new(
                ErrorKind::UnexpectedCall,
                format!(
                    "Unexpected CallScheduled(call_id={}, name={}) in phase {}",
                    call_id,
                    name,
                    self.current_phase()
                ),
            )
            .with_phase(self.current_phase())
            .with_step(self.state.step)),
        }
    }

    /// Apply CallResult event.
    fn apply_call_result(&mut self, call_id: &str, output: Value) -> Result<(), MachineError> {
        match &self.state.phase {
            Phase::GatheringContext {
                pending: None,
                call_id: Some(expected),
            } if call_id == expected => {
                // Store schema in evidence
                self.state
                    .evidence
                    .insert("schema".to_string(), output.clone());
                self.state.call_order.push(call_id.to_string());
                // Transition to hypothesis generation
                self.state.phase = Phase::GeneratingHypotheses {
                    pending: None,
                    call_id: None,
                };
                Ok(())
            }
            Phase::GeneratingHypotheses {
                pending: None,
                call_id: Some(expected),
            } if call_id == expected => {
                // Store hypotheses in evidence
                self.state
                    .evidence
                    .insert("hypotheses".to_string(), output.clone());
                self.state.call_order.push(call_id.to_string());
                // Count hypotheses for evaluation
                let hypothesis_count = output.as_array().map(|a| a.len()).unwrap_or(0);
                // Transition to evaluating hypotheses
                self.state.phase = Phase::EvaluatingHypotheses {
                    pending: None,
                    awaiting_results: vec![],
                    total_hypotheses: hypothesis_count,
                    completed: 0,
                };
                Ok(())
            }
            Phase::EvaluatingHypotheses {
                pending: None,
                awaiting_results,
                total_hypotheses,
                completed,
            } if awaiting_results.contains(&call_id.to_string()) => {
                // Store evidence for this evaluation
                self.state
                    .evidence
                    .insert(format!("eval_{}", call_id), output.clone());
                self.state.call_order.push(call_id.to_string());

                // Remove from awaiting
                let mut new_awaiting = awaiting_results.clone();
                new_awaiting.retain(|id| id != call_id);
                let new_completed = completed + 1;

                if new_completed >= *total_hypotheses && new_awaiting.is_empty() {
                    // All evaluations complete, move to synthesis
                    self.state.phase = Phase::Synthesizing {
                        pending: None,
                        call_id: None,
                    };
                } else {
                    self.state.phase = Phase::EvaluatingHypotheses {
                        pending: None,
                        awaiting_results: new_awaiting,
                        total_hypotheses: *total_hypotheses,
                        completed: new_completed,
                    };
                }
                Ok(())
            }
            Phase::Synthesizing {
                pending: None,
                call_id: Some(expected),
            } if call_id == expected => {
                self.state.call_order.push(call_id.to_string());
                // Extract insight from output
                let insight = output
                    .get("insight")
                    .and_then(|v| v.as_str())
                    .unwrap_or("Investigation complete")
                    .to_string();
                self.state.phase = Phase::Finished { insight };
                Ok(())
            }
            _ => Err(MachineError::new(
                ErrorKind::UnexpectedCall,
                format!(
                    "Unexpected CallResult(call_id={}) in phase {}",
                    call_id,
                    self.current_phase()
                ),
            )
            .with_phase(self.current_phase())
            .with_step(self.state.step)),
        }
    }

    /// Apply UserResponse event.
    fn apply_user_response(
        &mut self,
        question_id: &str,
        content: &str,
    ) -> Result<(), MachineError> {
        match &self.state.phase {
            Phase::AwaitingUser {
                question_id: expected,
                ..
            } if question_id == expected => {
                // Store user response
                self.state.evidence.insert(
                    format!("user_response_{}", question_id),
                    json!(content),
                );
                // Continue to synthesis
                self.state.phase = Phase::Synthesizing {
                    pending: None,
                    call_id: None,
                };
                Ok(())
            }
            _ => Err(MachineError::new(
                ErrorKind::InvalidTransition,
                format!(
                    "Unexpected UserResponse(question_id={}) in phase {}",
                    question_id,
                    self.current_phase()
                ),
            )
            .with_phase(self.current_phase())
            .with_step(self.state.step)),
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

    /// Record metadata for a call.
    fn record_meta(&mut self, call_id: &str, name: &str, kind: CallKind, phase_context: &str) {
        self.state.call_index.insert(
            call_id.to_string(),
            CallMeta {
                id: call_id.to_string(),
                name: name.to_string(),
                kind,
                phase_context: phase_context.to_string(),
                created_at_step: self.state.step,
            },
        );
    }

    /// Decide what intent to emit based on current state.
    fn decide(&mut self) -> Intent {
        match &self.state.phase {
            Phase::Init => Intent::Idle,

            Phase::GatheringContext { pending, call_id } => {
                if pending.is_some() {
                    // Waiting for CallScheduled
                    Intent::Idle
                } else if call_id.is_some() {
                    // Waiting for CallResult
                    Intent::Idle
                } else {
                    // Need to request schema call
                    self.state.phase = Phase::GatheringContext {
                        pending: Some(PendingCall {
                            name: "get_schema".to_string(),
                            awaiting_schedule: true,
                        }),
                        call_id: None,
                    };
                    Intent::RequestCall {
                        kind: CallKind::Tool,
                        name: "get_schema".to_string(),
                        args: json!({
                            "objective": self.state.objective.clone().unwrap_or_default()
                        }),
                        reasoning: "Need to gather schema context for the investigation".to_string(),
                    }
                }
            }

            Phase::GeneratingHypotheses { pending, call_id } => {
                if pending.is_some() || call_id.is_some() {
                    Intent::Idle
                } else {
                    self.state.phase = Phase::GeneratingHypotheses {
                        pending: Some(PendingCall {
                            name: "generate_hypotheses".to_string(),
                            awaiting_schedule: true,
                        }),
                        call_id: None,
                    };
                    Intent::RequestCall {
                        kind: CallKind::Llm,
                        name: "generate_hypotheses".to_string(),
                        args: json!({
                            "objective": self.state.objective.clone().unwrap_or_default(),
                            "schema": self.state.evidence.get("schema").cloned().unwrap_or(Value::Null)
                        }),
                        reasoning: "Generate hypotheses to explain the observed anomaly".to_string(),
                    }
                }
            }

            Phase::EvaluatingHypotheses {
                pending,
                awaiting_results,
                total_hypotheses,
                completed,
            } => {
                if pending.is_some() {
                    // Waiting for CallScheduled
                    Intent::Idle
                } else if !awaiting_results.is_empty() {
                    // Waiting for CallResults
                    Intent::Idle
                } else if *completed < *total_hypotheses {
                    // Need to request next evaluation
                    // Clone values before mutable operations to satisfy borrow checker
                    let hypothesis_idx = *completed;
                    let total = *total_hypotheses;
                    self.state.phase = Phase::EvaluatingHypotheses {
                        pending: Some(PendingCall {
                            name: "evaluate_hypothesis".to_string(),
                            awaiting_schedule: true,
                        }),
                        awaiting_results: vec![],
                        total_hypotheses: total,
                        completed: hypothesis_idx,
                    };
                    Intent::RequestCall {
                        kind: CallKind::Tool,
                        name: "evaluate_hypothesis".to_string(),
                        args: json!({
                            "hypothesis_index": hypothesis_idx,
                            "hypotheses": self.state.evidence.get("hypotheses").cloned().unwrap_or(Value::Null)
                        }),
                        reasoning: format!("Evaluate hypothesis {} of {}", hypothesis_idx + 1, total),
                    }
                } else {
                    // Should have transitioned to Synthesizing
                    Intent::Idle
                }
            }

            Phase::AwaitingUser { .. } => {
                // Waiting for user response (signal)
                Intent::Idle
            }

            Phase::Synthesizing { pending, call_id } => {
                if pending.is_some() || call_id.is_some() {
                    Intent::Idle
                } else {
                    self.state.phase = Phase::Synthesizing {
                        pending: Some(PendingCall {
                            name: "synthesize".to_string(),
                            awaiting_schedule: true,
                        }),
                        call_id: None,
                    };
                    Intent::RequestCall {
                        kind: CallKind::Llm,
                        name: "synthesize".to_string(),
                        args: json!({
                            "objective": self.state.objective.clone().unwrap_or_default(),
                            "evidence": self.state.evidence.clone()
                        }),
                        reasoning: "Synthesize all evidence into a final insight".to_string(),
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
            permissions: vec![],
            extra: BTreeMap::new(),
        }
    }

    fn make_envelope(event_id: &str, step: u64, event: Event) -> Envelope {
        Envelope {
            protocol_version: PROTOCOL_VERSION,
            event_id: event_id.to_string(),
            step,
            event,
        }
    }

    #[test]
    fn test_new_investigator() {
        let inv = Investigator::new();
        assert_eq!(inv.current_phase(), "init");
        assert_eq!(inv.current_step(), 0);
        assert!(!inv.is_terminal());
    }

    #[test]
    fn test_start_event() {
        let mut inv = Investigator::new();

        let envelope = make_envelope(
            "evt_1",
            1,
            Event::Start {
                objective: "Test".to_string(),
                scope: test_scope(),
            },
        );

        let intent = inv.ingest(envelope).expect("should succeed");

        // Should emit RequestCall (no call_id)
        match intent {
            Intent::RequestCall { name, kind, .. } => {
                assert_eq!(name, "get_schema");
                assert_eq!(kind, CallKind::Tool);
            }
            _ => panic!("Expected RequestCall intent"),
        }

        assert_eq!(inv.current_phase(), "gathering_context");
        assert_eq!(inv.current_step(), 1);
    }

    #[test]
    fn test_protocol_version_mismatch() {
        let mut inv = Investigator::new();

        let envelope = Envelope {
            protocol_version: 999,
            event_id: "evt_1".to_string(),
            step: 1,
            event: Event::Cancel,
        };

        let err = inv.ingest(envelope).expect_err("should fail");
        assert_eq!(err.kind, ErrorKind::ProtocolMismatch);
    }

    #[test]
    fn test_duplicate_event_idempotent() {
        let mut inv = Investigator::new();

        let envelope1 = make_envelope(
            "evt_1",
            1,
            Event::Start {
                objective: "Test".to_string(),
                scope: test_scope(),
            },
        );

        let intent1 = inv.ingest(envelope1).expect("first should succeed");

        // Same event_id again (but different step to pass monotonicity)
        let envelope2 = Envelope {
            protocol_version: PROTOCOL_VERSION,
            event_id: "evt_1".to_string(), // duplicate
            step: 2,
            event: Event::Cancel,
        };

        // Should return current intent without applying Cancel
        let intent2 = inv.ingest(envelope2).expect("duplicate should succeed");

        // State should NOT have changed
        assert_eq!(inv.current_phase(), "gathering_context");
        // Step should NOT have advanced
        assert_eq!(inv.current_step(), 1);
    }

    #[test]
    fn test_step_violation() {
        let mut inv = Investigator::new();

        let envelope1 = make_envelope(
            "evt_1",
            5,
            Event::Start {
                objective: "Test".to_string(),
                scope: test_scope(),
            },
        );
        inv.ingest(envelope1).expect("first should succeed");

        // Step 3 is less than current step 5
        let envelope2 = make_envelope("evt_2", 3, Event::Cancel);

        let err = inv.ingest(envelope2).expect_err("should fail");
        assert_eq!(err.kind, ErrorKind::StepViolation);
    }

    #[test]
    fn test_call_scheduling_handshake() {
        let mut inv = Investigator::new();

        // Start
        let start = make_envelope(
            "evt_1",
            1,
            Event::Start {
                objective: "Test".to_string(),
                scope: test_scope(),
            },
        );
        let intent = inv.ingest(start).expect("start");

        // Should request get_schema (no call_id)
        match intent {
            Intent::RequestCall { name, .. } => assert_eq!(name, "get_schema"),
            _ => panic!("Expected RequestCall"),
        }

        // Now workflow assigns call_id via CallScheduled
        let scheduled = make_envelope(
            "evt_2",
            2,
            Event::CallScheduled {
                call_id: "call_001".to_string(),
                name: "get_schema".to_string(),
            },
        );
        let intent = inv.ingest(scheduled).expect("scheduled");
        assert!(matches!(intent, Intent::Idle));

        // Now send result
        let result = make_envelope(
            "evt_3",
            3,
            Event::CallResult {
                call_id: "call_001".to_string(),
                output: json!({"tables": []}),
            },
        );
        let intent = inv.ingest(result).expect("result");

        // Should advance to next phase and request generate_hypotheses
        match intent {
            Intent::RequestCall { name, .. } => assert_eq!(name, "generate_hypotheses"),
            _ => panic!("Expected RequestCall for generate_hypotheses"),
        }
    }

    #[test]
    fn test_unexpected_call_scheduled() {
        let mut inv = Investigator::new();

        // Start
        let start = make_envelope(
            "evt_1",
            1,
            Event::Start {
                objective: "Test".to_string(),
                scope: test_scope(),
            },
        );
        inv.ingest(start).expect("start");

        // Wrong name in CallScheduled
        let scheduled = make_envelope(
            "evt_2",
            2,
            Event::CallScheduled {
                call_id: "call_001".to_string(),
                name: "wrong_name".to_string(),
            },
        );

        let err = inv.ingest(scheduled).expect_err("should fail");
        assert_eq!(err.kind, ErrorKind::UnexpectedCall);
    }

    #[test]
    fn test_cancel_in_progress() {
        let mut inv = Investigator::new();

        let start = make_envelope(
            "evt_1",
            1,
            Event::Start {
                objective: "Test".to_string(),
                scope: test_scope(),
            },
        );
        inv.ingest(start).expect("start");

        let cancel = make_envelope("evt_2", 2, Event::Cancel);
        let intent = inv.ingest(cancel).expect("cancel");

        match intent {
            Intent::Error { message } => assert!(message.contains("cancelled")),
            _ => panic!("Expected Error intent"),
        }
        assert!(inv.is_terminal());
    }

    #[test]
    fn test_full_investigation_cycle() {
        let mut inv = Investigator::new();
        let mut step = 0u64;

        // Helper to make envelopes with incrementing steps
        let mut next_envelope = |event: Event| {
            step += 1;
            make_envelope(&format!("evt_{}", step), step, event)
        };

        // Start
        let intent = inv
            .ingest(next_envelope(Event::Start {
                objective: "Find bug".to_string(),
                scope: test_scope(),
            }))
            .expect("start");
        assert!(matches!(intent, Intent::RequestCall { name, .. } if name == "get_schema"));

        // CallScheduled for get_schema
        inv.ingest(next_envelope(Event::CallScheduled {
            call_id: "c1".to_string(),
            name: "get_schema".to_string(),
        }))
        .expect("scheduled");

        // CallResult for get_schema
        let intent = inv
            .ingest(next_envelope(Event::CallResult {
                call_id: "c1".to_string(),
                output: json!({"tables": []}),
            }))
            .expect("result");
        assert!(matches!(intent, Intent::RequestCall { name, .. } if name == "generate_hypotheses"));

        // CallScheduled for generate_hypotheses
        inv.ingest(next_envelope(Event::CallScheduled {
            call_id: "c2".to_string(),
            name: "generate_hypotheses".to_string(),
        }))
        .expect("scheduled");

        // CallResult with 1 hypothesis
        let intent = inv
            .ingest(next_envelope(Event::CallResult {
                call_id: "c2".to_string(),
                output: json!([{"id": "h1", "title": "Bug in ETL"}]),
            }))
            .expect("result");
        assert!(matches!(intent, Intent::RequestCall { name, .. } if name == "evaluate_hypothesis"));

        // CallScheduled for evaluate_hypothesis
        inv.ingest(next_envelope(Event::CallScheduled {
            call_id: "c3".to_string(),
            name: "evaluate_hypothesis".to_string(),
        }))
        .expect("scheduled");

        // CallResult for evaluate
        let intent = inv
            .ingest(next_envelope(Event::CallResult {
                call_id: "c3".to_string(),
                output: json!({"supported": true}),
            }))
            .expect("result");
        assert!(matches!(intent, Intent::RequestCall { name, .. } if name == "synthesize"));

        // CallScheduled for synthesize
        inv.ingest(next_envelope(Event::CallScheduled {
            call_id: "c4".to_string(),
            name: "synthesize".to_string(),
        }))
        .expect("scheduled");

        // CallResult for synthesize
        let intent = inv
            .ingest(next_envelope(Event::CallResult {
                call_id: "c4".to_string(),
                output: json!({"insight": "Root cause found"}),
            }))
            .expect("result");

        assert!(matches!(intent, Intent::Finish { insight } if insight == "Root cause found"));
        assert!(inv.is_terminal());
    }

    #[test]
    fn test_snapshot_restore() {
        let mut inv = Investigator::new();

        let start = make_envelope(
            "evt_1",
            1,
            Event::Start {
                objective: "Test".to_string(),
                scope: test_scope(),
            },
        );
        inv.ingest(start).expect("start");

        let snapshot = inv.snapshot();
        let inv2 = Investigator::restore(snapshot);

        assert_eq!(inv.current_phase(), inv2.current_phase());
        assert_eq!(inv.current_step(), inv2.current_step());
    }

    #[test]
    fn test_query_without_event() {
        let inv = Investigator::new();

        // Query current intent without event
        let intent = inv.query();
        assert!(matches!(intent, Intent::Idle));
    }
}
