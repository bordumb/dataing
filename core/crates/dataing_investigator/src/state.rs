//! Investigation state and phase tracking.
//!
//! Contains the core State struct and Phase enum for tracking
//! investigation progress. The state is versioned and serializable
//! for snapshot persistence.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

use crate::domain::{CallMeta, Scope};
use crate::PROTOCOL_VERSION;

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
        /// ID of the schema discovery call, if initiated.
        schema_call_id: Option<String>,
    },

    /// Generating hypotheses using LLM.
    GeneratingHypotheses {
        /// ID of the LLM call for hypothesis generation.
        llm_call_id: Option<String>,
    },

    /// Evaluating hypotheses by executing queries.
    EvaluatingHypotheses {
        /// IDs of pending evaluation calls.
        pending_call_ids: Vec<String>,
    },

    /// Waiting for user input (human-in-the-loop).
    AwaitingUser {
        /// Question presented to the user.
        question: String,
    },

    /// Synthesizing findings into final insight.
    Synthesizing {
        /// ID of the synthesis LLM call.
        synthesis_call_id: Option<String>,
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
/// # ID Generation
///
/// Uses `sequence` counter for generating unique IDs within an investigation.
/// Each call to `generate_id()` increments the sequence, ensuring uniqueness
/// even after snapshot restoration.
///
/// # Logical Clock
///
/// The `step` counter acts as a logical clock, incremented for each
/// event processed. This enables ordering of events and debugging.
#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct State {
    /// Protocol version for this state snapshot.
    pub version: u32,

    /// Sequence counter for ID generation (monotonically increasing).
    pub sequence: u64,

    /// Logical clock / step counter (events processed).
    pub step: u64,

    /// Investigation objective/description.
    #[serde(default)]
    pub objective: Option<String>,

    /// Security scope for access control.
    #[serde(default)]
    pub scope: Option<Scope>,

    /// Current phase of the investigation.
    pub phase: Phase,

    /// Collected evidence keyed by hypothesis ID.
    #[serde(default)]
    pub evidence: BTreeMap<String, Value>,

    /// Metadata for pending/completed calls.
    #[serde(default)]
    pub call_index: BTreeMap<String, CallMeta>,

    /// Order in which calls were initiated.
    #[serde(default)]
    pub call_order: Vec<String>,
}

impl Default for State {
    fn default() -> Self {
        Self::new()
    }
}

impl State {
    /// Create a new state with default values.
    ///
    /// Initializes with current protocol version, zero counters,
    /// and Init phase.
    #[must_use]
    pub fn new() -> Self {
        State {
            version: PROTOCOL_VERSION,
            sequence: 0,
            step: 0,
            objective: None,
            scope: None,
            phase: Phase::Init,
            evidence: BTreeMap::new(),
            call_index: BTreeMap::new(),
            call_order: Vec::new(),
        }
    }

    /// Generate a unique ID with the given prefix.
    ///
    /// Increments the sequence counter and returns a prefixed ID.
    /// Format: `{prefix}_{sequence}`
    ///
    /// # Example
    ///
    /// ```
    /// use dataing_investigator::state::State;
    ///
    /// let mut state = State::new();
    /// assert_eq!(state.generate_id("call"), "call_1");
    /// assert_eq!(state.generate_id("call"), "call_2");
    /// assert_eq!(state.generate_id("hyp"), "hyp_3");
    /// ```
    pub fn generate_id(&mut self, prefix: &str) -> String {
        self.sequence += 1;
        format!("{}_{}", prefix, self.sequence)
    }

    /// Increment the step counter.
    ///
    /// Called when processing each event to advance the logical clock.
    pub fn advance_step(&mut self) {
        self.step += 1;
    }
}

impl PartialEq for State {
    fn eq(&self, other: &Self) -> bool {
        self.version == other.version
            && self.sequence == other.sequence
            && self.step == other.step
            && self.objective == other.objective
            && self.scope == other.scope
            && self.phase == other.phase
            && self.evidence == other.evidence
            && self.call_index == other.call_index
            && self.call_order == other.call_order
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
        assert_eq!(state.sequence, 0);
        assert_eq!(state.step, 0);
        assert_eq!(state.phase, Phase::Init);
        assert!(state.objective.is_none());
        assert!(state.scope.is_none());
        assert!(state.evidence.is_empty());
        assert!(state.call_index.is_empty());
        assert!(state.call_order.is_empty());
    }

    #[test]
    fn test_generate_id() {
        let mut state = State::new();

        assert_eq!(state.generate_id("call"), "call_1");
        assert_eq!(state.generate_id("call"), "call_2");
        assert_eq!(state.generate_id("hyp"), "hyp_3");
        assert_eq!(state.sequence, 3);
    }

    #[test]
    fn test_advance_step() {
        let mut state = State::new();

        state.advance_step();
        assert_eq!(state.step, 1);

        state.advance_step();
        state.advance_step();
        assert_eq!(state.step, 3);
    }

    #[test]
    fn test_phase_serialization() {
        let phases = vec![
            Phase::Init,
            Phase::GatheringContext {
                schema_call_id: Some("call_1".to_string()),
            },
            Phase::GatheringContext {
                schema_call_id: None,
            },
            Phase::GeneratingHypotheses {
                llm_call_id: Some("call_2".to_string()),
            },
            Phase::EvaluatingHypotheses {
                pending_call_ids: vec!["call_3".to_string(), "call_4".to_string()],
            },
            Phase::AwaitingUser {
                question: "Proceed?".to_string(),
            },
            Phase::Synthesizing {
                synthesis_call_id: None,
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
    fn test_phase_tagged_format() {
        let phase = Phase::GatheringContext {
            schema_call_id: Some("call_1".to_string()),
        };
        let json = serde_json::to_string(&phase).expect("serialize");

        assert!(json.contains(r#""type":"GatheringContext""#));
        assert!(json.contains(r#""data""#));
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
            llm_call_id: Some("call_1".to_string()),
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
        state.sequence = 5;

        let json = serde_json::to_string(&state).expect("serialize");
        let deser: State = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(state, deser);
    }

    #[test]
    fn test_state_defaults_on_missing_fields() {
        // Simulate a minimal snapshot (forward compatibility test)
        let json = r#"{
            "version": 1,
            "sequence": 0,
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
    }

    #[test]
    fn test_btreemap_ordering() {
        let mut state = State::new();
        state
            .evidence
            .insert("z_hyp".to_string(), Value::Bool(true));
        state
            .evidence
            .insert("a_hyp".to_string(), Value::Bool(true));
        state
            .evidence
            .insert("m_hyp".to_string(), Value::Bool(true));

        let json = serde_json::to_string(&state).expect("serialize");

        // BTreeMap ensures alphabetical ordering
        let a_pos = json.find("a_hyp").expect("a_hyp");
        let m_pos = json.find("m_hyp").expect("m_hyp");
        let z_pos = json.find("z_hyp").expect("z_hyp");

        assert!(a_pos < m_pos);
        assert!(m_pos < z_pos);
    }
}
