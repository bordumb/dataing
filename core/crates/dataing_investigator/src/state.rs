//! Investigation state and phase tracking.
//!
//! Contains the core State struct and Phase enum for tracking
//! investigation progress. The state is versioned and serializable
//! for snapshot persistence.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::{BTreeMap, BTreeSet};

use crate::domain::{CallMeta, Scope};
use crate::PROTOCOL_VERSION;

/// Pending call awaiting scheduling by the workflow.
///
/// When the machine emits a RequestCall intent, it transitions to a
/// "pending" sub-state. The workflow generates a call_id and sends
/// a CallScheduled event, which completes the scheduling.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct PendingCall {
    /// Name of the requested operation.
    pub name: String,
    /// Whether we're waiting for CallScheduled (true) or CallResult (false).
    pub awaiting_schedule: bool,
}

/// Current phase of an investigation.
///
/// Each phase represents a distinct step in the investigation workflow.
/// Phases with data use tagged serialization for explicit type identification.
#[derive(Debug, Clone, Default, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", content = "data")]
pub enum Phase {
    /// Initial state before investigation starts.
    #[default]
    Init,

    /// Gathering schema and context from the data source.
    GatheringContext {
        /// Pending call info, if any.
        #[serde(default)]
        pending: Option<PendingCall>,
        /// Assigned call_id after CallScheduled, if scheduled.
        #[serde(default)]
        call_id: Option<String>,
    },

    /// Generating hypotheses using LLM.
    GeneratingHypotheses {
        /// Pending call info, if any.
        #[serde(default)]
        pending: Option<PendingCall>,
        /// Assigned call_id after CallScheduled.
        #[serde(default)]
        call_id: Option<String>,
    },

    /// Evaluating hypotheses by executing queries.
    EvaluatingHypotheses {
        /// Pending call info for next evaluation.
        #[serde(default)]
        pending: Option<PendingCall>,
        /// IDs of calls awaiting results.
        #[serde(default)]
        awaiting_results: Vec<String>,
        /// Total hypotheses to evaluate.
        #[serde(default)]
        total_hypotheses: usize,
        /// Completed evaluations.
        #[serde(default)]
        completed: usize,
    },

    /// Waiting for user input (human-in-the-loop).
    AwaitingUser {
        /// Unique ID for this question (workflow-generated).
        question_id: String,
        /// Prompt presented to the user.
        prompt: String,
        /// Timeout in seconds (0 = no timeout).
        #[serde(default)]
        timeout_seconds: u64,
    },

    /// Synthesizing findings into final insight.
    Synthesizing {
        /// Pending call info, if any.
        #[serde(default)]
        pending: Option<PendingCall>,
        /// Assigned call_id after CallScheduled.
        #[serde(default)]
        call_id: Option<String>,
    },

    /// Investigation completed successfully.
    Finished {
        /// Final insight/conclusion.
        insight: String,
    },

    /// Investigation failed with error.
    Failed {
        /// Error message describing the failure.
        error: String,
    },
}

/// Versioned investigation state.
///
/// Contains all data needed to reconstruct an investigation's progress.
/// The state is designed to be serializable for persistence and
/// resumption from snapshots.
///
/// # Workflow-Owned IDs and Steps
///
/// The workflow (Temporal) owns ID generation and step counting.
/// The state machine validates but does not generate these values.
/// This ensures deterministic replay.
///
/// # Idempotency
///
/// The `seen_event_ids` set enables event deduplication. Duplicate
/// events are silently ignored (returns current intent without
/// state change).
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct State {
    /// Protocol version for this state snapshot.
    pub version: u32,

    /// Last processed step (workflow-owned, validated for monotonicity).
    pub step: u64,

    /// Investigation objective/description.
    #[serde(default)]
    pub objective: Option<String>,

    /// Security scope for access control.
    #[serde(default)]
    pub scope: Option<Scope>,

    /// Current phase of the investigation.
    pub phase: Phase,

    /// Collected evidence keyed by identifier.
    #[serde(default)]
    pub evidence: BTreeMap<String, Value>,

    /// Metadata for pending/completed calls.
    #[serde(default)]
    pub call_index: BTreeMap<String, CallMeta>,

    /// Order in which calls were completed.
    #[serde(default)]
    pub call_order: Vec<String>,

    /// Event IDs that have been processed (for deduplication).
    #[serde(default)]
    pub seen_event_ids: BTreeSet<String>,
}

impl Default for State {
    fn default() -> Self {
        Self::new()
    }
}

impl State {
    /// Create a new state with default values.
    ///
    /// Initializes with current protocol version, zero step,
    /// and Init phase.
    #[must_use]
    pub fn new() -> Self {
        State {
            version: PROTOCOL_VERSION,
            step: 0,
            objective: None,
            scope: None,
            phase: Phase::Init,
            evidence: BTreeMap::new(),
            call_index: BTreeMap::new(),
            call_order: Vec::new(),
            seen_event_ids: BTreeSet::new(),
        }
    }

    /// Check if an event ID has already been processed.
    #[must_use]
    pub fn is_duplicate_event(&self, event_id: &str) -> bool {
        self.seen_event_ids.contains(event_id)
    }

    /// Mark an event ID as processed.
    pub fn mark_event_processed(&mut self, event_id: String) {
        self.seen_event_ids.insert(event_id);
    }

    /// Update the step counter (workflow-owned).
    pub fn set_step(&mut self, step: u64) {
        self.step = step;
    }

    /// Check if state is in a terminal phase.
    #[must_use]
    pub fn is_terminal(&self) -> bool {
        matches!(self.phase, Phase::Finished { .. } | Phase::Failed { .. })
    }
}

impl PartialEq for State {
    fn eq(&self, other: &Self) -> bool {
        self.version == other.version
            && self.step == other.step
            && self.objective == other.objective
            && self.scope == other.scope
            && self.phase == other.phase
            && self.evidence == other.evidence
            && self.call_index == other.call_index
            && self.call_order == other.call_order
            && self.seen_event_ids == other.seen_event_ids
    }
}

/// Get a human-readable name for a phase.
#[must_use]
pub fn phase_name(phase: &Phase) -> &'static str {
    match phase {
        Phase::Init => "init",
        Phase::GatheringContext { .. } => "gathering_context",
        Phase::GeneratingHypotheses { .. } => "generating_hypotheses",
        Phase::EvaluatingHypotheses { .. } => "evaluating_hypotheses",
        Phase::AwaitingUser { .. } => "awaiting_user",
        Phase::Synthesizing { .. } => "synthesizing",
        Phase::Finished { .. } => "finished",
        Phase::Failed { .. } => "failed",
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::CallKind;

    #[test]
    fn test_state_new() {
        let state = State::new();

        assert_eq!(state.version, PROTOCOL_VERSION);
        assert_eq!(state.step, 0);
        assert_eq!(state.phase, Phase::Init);
        assert!(state.objective.is_none());
        assert!(state.scope.is_none());
        assert!(state.evidence.is_empty());
        assert!(state.call_index.is_empty());
        assert!(state.call_order.is_empty());
        assert!(state.seen_event_ids.is_empty());
    }

    #[test]
    fn test_set_step() {
        let mut state = State::new();

        state.set_step(5);
        assert_eq!(state.step, 5);

        state.set_step(10);
        assert_eq!(state.step, 10);
    }

    #[test]
    fn test_duplicate_event_detection() {
        let mut state = State::new();

        assert!(!state.is_duplicate_event("evt_001"));

        state.mark_event_processed("evt_001".to_string());

        assert!(state.is_duplicate_event("evt_001"));
        assert!(!state.is_duplicate_event("evt_002"));
    }

    #[test]
    fn test_is_terminal() {
        let mut state = State::new();
        assert!(!state.is_terminal());

        state.phase = Phase::GatheringContext {
            pending: None,
            call_id: None,
        };
        assert!(!state.is_terminal());

        state.phase = Phase::Finished {
            insight: "done".to_string(),
        };
        assert!(state.is_terminal());

        state.phase = Phase::Failed {
            error: "error".to_string(),
        };
        assert!(state.is_terminal());
    }

    #[test]
    fn test_phase_serialization() {
        let phases = vec![
            Phase::Init,
            Phase::GatheringContext {
                pending: Some(PendingCall {
                    name: "get_schema".to_string(),
                    awaiting_schedule: true,
                }),
                call_id: None,
            },
            Phase::GatheringContext {
                pending: None,
                call_id: Some("call_1".to_string()),
            },
            Phase::GeneratingHypotheses {
                pending: None,
                call_id: Some("call_2".to_string()),
            },
            Phase::EvaluatingHypotheses {
                pending: None,
                awaiting_results: vec!["call_3".to_string(), "call_4".to_string()],
                total_hypotheses: 3,
                completed: 1,
            },
            Phase::AwaitingUser {
                question_id: "q_1".to_string(),
                prompt: "Proceed?".to_string(),
                timeout_seconds: 3600,
            },
            Phase::Synthesizing {
                pending: None,
                call_id: None,
            },
            Phase::Finished {
                insight: "Root cause found".to_string(),
            },
            Phase::Failed {
                error: "Timeout".to_string(),
            },
        ];

        for phase in phases {
            let json = serde_json::to_string(&phase).expect("serialize");
            let deser: Phase = serde_json::from_str(&json).expect("deserialize");
            assert_eq!(phase, deser);
        }
    }

    #[test]
    fn test_phase_name() {
        assert_eq!(phase_name(&Phase::Init), "init");
        assert_eq!(
            phase_name(&Phase::GatheringContext {
                pending: None,
                call_id: None
            }),
            "gathering_context"
        );
        assert_eq!(
            phase_name(&Phase::AwaitingUser {
                question_id: "q".to_string(),
                prompt: "p".to_string(),
                timeout_seconds: 0,
            }),
            "awaiting_user"
        );
    }

    #[test]
    fn test_state_serialization_roundtrip() {
        let mut state = State::new();
        state.objective = Some("Find null spike cause".to_string());
        state.scope = Some(Scope {
            user_id: "u1".to_string(),
            tenant_id: "t1".to_string(),
            permissions: vec!["read".to_string()],
            extra: BTreeMap::new(),
        });
        state.phase = Phase::GeneratingHypotheses {
            pending: None,
            call_id: Some("call_1".to_string()),
        };
        state.evidence.insert(
            "hyp_1".to_string(),
            serde_json::json!({"query_result": "5 nulls"}),
        );
        state.call_index.insert(
            "call_1".to_string(),
            CallMeta {
                id: "call_1".to_string(),
                name: "generate_hypotheses".to_string(),
                kind: CallKind::Llm,
                phase_context: "hypothesis_generation".to_string(),
                created_at_step: 2,
            },
        );
        state.call_order.push("call_1".to_string());
        state.step = 3;
        state.seen_event_ids.insert("evt_1".to_string());
        state.seen_event_ids.insert("evt_2".to_string());

        let json = serde_json::to_string(&state).expect("serialize");
        let deser: State = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(state, deser);
    }

    #[test]
    fn test_state_defaults_on_missing_fields() {
        // Simulate a minimal snapshot (forward compatibility test)
        let json = r#"{
            "version": 1,
            "step": 0,
            "phase": {"type": "Init"}
        }"#;

        let state: State = serde_json::from_str(json).expect("deserialize");

        assert_eq!(state.version, 1);
        assert!(state.objective.is_none());
        assert!(state.scope.is_none());
        assert!(state.evidence.is_empty());
        assert!(state.call_index.is_empty());
        assert!(state.call_order.is_empty());
        assert!(state.seen_event_ids.is_empty());
    }

    #[test]
    fn test_btreeset_ordering() {
        let mut state = State::new();
        state.mark_event_processed("evt_z".to_string());
        state.mark_event_processed("evt_a".to_string());
        state.mark_event_processed("evt_m".to_string());

        let json = serde_json::to_string(&state).expect("serialize");

        // BTreeSet ensures alphabetical ordering
        let a_pos = json.find("evt_a").expect("evt_a");
        let m_pos = json.find("evt_m").expect("evt_m");
        let z_pos = json.find("evt_z").expect("evt_z");

        assert!(a_pos < m_pos);
        assert!(m_pos < z_pos);
    }
}
