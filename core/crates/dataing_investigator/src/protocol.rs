//! Protocol types for state machine communication.
//!
//! Defines the Event, Intent, and Envelope types that form the contract between
//! the Python runtime and Rust state machine.
//!
//! # Wire Format
//!
//! All events are wrapped in an Envelope:
//! ```json
//! {
//!   "protocol_version": 1,
//!   "event_id": "evt_abc123",
//!   "step": 5,
//!   "event": {"type": "CallResult", "payload": {...}}
//! }
//! ```
//!
//! # Stability
//!
//! These types form a versioned protocol contract. Changes must be
//! backwards-compatible (use `#[serde(default)]` for new fields).

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::domain::{CallKind, Scope};

/// Envelope wrapping all events with protocol metadata.
///
/// The envelope provides:
/// - Protocol versioning for compatibility checks
/// - Event IDs for idempotency/deduplication
/// - Step numbers for ordering and monotonicity validation
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Envelope {
    /// Protocol version (must match state machine's expected version).
    pub protocol_version: u32,

    /// Unique ID for this event (for deduplication).
    pub event_id: String,

    /// Workflow-owned step counter (must be monotonically increasing).
    pub step: u64,

    /// The actual event payload.
    pub event: Event,
}

/// Events sent from Python runtime to the Rust state machine.
///
/// Each event represents an external occurrence that may trigger
/// a state transition.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", content = "payload")]
pub enum Event {
    /// Start a new investigation.
    Start {
        /// Description of what to investigate.
        objective: String,
        /// Security scope for access control.
        scope: Scope,
    },

    /// Workflow has scheduled a call and assigned it an ID.
    ///
    /// This event is sent by the workflow after it receives a RequestCall
    /// intent and generates a call_id.
    CallScheduled {
        /// Workflow-generated unique ID for this call.
        call_id: String,
        /// Name of the operation (must match the RequestCall).
        name: String,
    },

    /// Result of an external call (LLM or tool).
    CallResult {
        /// ID matching the CallScheduled event.
        call_id: String,
        /// Result payload from the call.
        output: Value,
    },

    /// User response to a RequestUser intent.
    UserResponse {
        /// ID of the question being answered.
        question_id: String,
        /// User's response content.
        content: String,
    },

    /// Cancel the current investigation.
    Cancel,
}

/// Intents emitted by the state machine to request actions.
///
/// Each intent represents something the Python runtime should do.
/// The state machine cannot perform side effects directly.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(tag = "type", content = "payload")]
pub enum Intent {
    /// No action needed; state machine is waiting.
    Idle,

    /// Request an external call (LLM inference or tool invocation).
    ///
    /// The workflow generates the call_id and sends back a CallScheduled event.
    RequestCall {
        /// Type of call (LLM or Tool).
        kind: CallKind,
        /// Human-readable name of the operation.
        name: String,
        /// Arguments for the call.
        args: Value,
        /// Explanation of why this call is being made.
        reasoning: String,
    },

    /// Request user input (human-in-the-loop).
    RequestUser {
        /// Workflow-generated unique ID for this question.
        question_id: String,
        /// Question/prompt to present to the user.
        prompt: String,
        /// Timeout in seconds (0 means no timeout).
        #[serde(default)]
        timeout_seconds: u64,
    },

    /// Investigation finished successfully.
    Finish {
        /// Final insight/conclusion.
        insight: String,
    },

    /// Investigation ended with an error (non-retryable).
    Error {
        /// Error message.
        message: String,
    },
}

/// Error kinds for typed error handling.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum ErrorKind {
    /// Event received in wrong phase.
    InvalidTransition,
    /// JSON serialization/deserialization error.
    Serialization,
    /// Protocol version mismatch.
    ProtocolMismatch,
    /// Duplicate event ID (already processed).
    DuplicateEvent,
    /// Step not monotonically increasing.
    StepViolation,
    /// Unexpected call_id received.
    UnexpectedCall,
    /// Internal invariant violated.
    Invariant,
}

/// Typed machine error for Result-based API.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct MachineError {
    /// Error classification for retry decisions.
    pub kind: ErrorKind,
    /// Human-readable error message.
    pub message: String,
    /// Current phase when error occurred.
    #[serde(default)]
    pub phase: Option<String>,
    /// Current step when error occurred.
    #[serde(default)]
    pub step: Option<u64>,
}

impl MachineError {
    /// Create a new machine error.
    pub fn new(kind: ErrorKind, message: impl Into<String>) -> Self {
        Self {
            kind,
            message: message.into(),
            phase: None,
            step: None,
        }
    }

    /// Add phase context to the error.
    #[must_use]
    pub fn with_phase(mut self, phase: impl Into<String>) -> Self {
        self.phase = Some(phase.into());
        self
    }

    /// Add step context to the error.
    #[must_use]
    pub fn with_step(mut self, step: u64) -> Self {
        self.step = Some(step);
        self
    }

    /// Check if this error is retryable.
    #[must_use]
    pub fn is_retryable(&self) -> bool {
        // Only serialization errors might be retryable (e.g., transient I/O)
        // All logic errors are permanent failures
        matches!(self.kind, ErrorKind::Serialization)
    }
}

impl std::fmt::Display for MachineError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{:?}: {}", self.kind, self.message)?;
        if let Some(phase) = &self.phase {
            write!(f, " (phase: {})", phase)?;
        }
        if let Some(step) = self.step {
            write!(f, " (step: {})", step)?;
        }
        Ok(())
    }
}

impl std::error::Error for MachineError {}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::domain::Scope;
    use std::collections::BTreeMap;

    fn test_scope() -> Scope {
        Scope {
            user_id: "user1".to_string(),
            tenant_id: "tenant1".to_string(),
            permissions: vec!["read".to_string()],
            extra: BTreeMap::new(),
        }
    }

    #[test]
    fn test_envelope_serialization() {
        let envelope = Envelope {
            protocol_version: 1,
            event_id: "evt_001".to_string(),
            step: 5,
            event: Event::Start {
                objective: "Find root cause".to_string(),
                scope: test_scope(),
            },
        };

        let json = serde_json::to_string(&envelope).expect("serialize");
        assert!(json.contains(r#""protocol_version":1"#));
        assert!(json.contains(r#""event_id":"evt_001""#));
        assert!(json.contains(r#""step":5"#));

        let deser: Envelope = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(envelope, deser);
    }

    #[test]
    fn test_event_call_scheduled_serialization() {
        let event = Event::CallScheduled {
            call_id: "call_001".to_string(),
            name: "get_schema".to_string(),
        };

        let json = serde_json::to_string(&event).expect("serialize");
        assert!(json.contains(r#""type":"CallScheduled""#));

        let deser: Event = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(event, deser);
    }

    #[test]
    fn test_event_user_response_with_question_id() {
        let event = Event::UserResponse {
            question_id: "q_001".to_string(),
            content: "Yes, proceed".to_string(),
        };

        let json = serde_json::to_string(&event).expect("serialize");
        assert!(json.contains(r#""question_id":"q_001""#));

        let deser: Event = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(event, deser);
    }

    #[test]
    fn test_intent_request_call_no_id() {
        let intent = Intent::RequestCall {
            kind: CallKind::Tool,
            name: "get_schema".to_string(),
            args: serde_json::json!({"table": "orders"}),
            reasoning: "Need schema context".to_string(),
        };

        let json = serde_json::to_string(&intent).expect("serialize");
        assert!(json.contains(r#""type":"RequestCall""#));
        // Should NOT contain call_id
        assert!(!json.contains("call_id"));

        let deser: Intent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(intent, deser);
    }

    #[test]
    fn test_intent_request_user_with_fields() {
        let intent = Intent::RequestUser {
            question_id: "q_001".to_string(),
            prompt: "Should we proceed with the risky query?".to_string(),
            timeout_seconds: 3600,
        };

        let json = serde_json::to_string(&intent).expect("serialize");
        assert!(json.contains(r#""question_id":"q_001""#));
        assert!(json.contains(r#""timeout_seconds":3600"#));

        let deser: Intent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(intent, deser);
    }

    #[test]
    fn test_machine_error_display() {
        let err = MachineError::new(ErrorKind::InvalidTransition, "Start in wrong phase")
            .with_phase("gathering_context")
            .with_step(5);

        let display = err.to_string();
        assert!(display.contains("InvalidTransition"));
        assert!(display.contains("Start in wrong phase"));
        assert!(display.contains("gathering_context"));
        assert!(display.contains("step: 5"));
    }

    #[test]
    fn test_error_kind_retryable() {
        assert!(!MachineError::new(ErrorKind::InvalidTransition, "").is_retryable());
        assert!(!MachineError::new(ErrorKind::ProtocolMismatch, "").is_retryable());
        assert!(!MachineError::new(ErrorKind::DuplicateEvent, "").is_retryable());
        assert!(MachineError::new(ErrorKind::Serialization, "").is_retryable());
    }

    #[test]
    fn test_all_events_roundtrip() {
        let events = vec![
            Event::Start {
                objective: "test".to_string(),
                scope: test_scope(),
            },
            Event::CallScheduled {
                call_id: "c1".to_string(),
                name: "get_schema".to_string(),
            },
            Event::CallResult {
                call_id: "c1".to_string(),
                output: Value::Null,
            },
            Event::UserResponse {
                question_id: "q1".to_string(),
                content: "ok".to_string(),
            },
            Event::Cancel,
        ];

        for event in events {
            let json = serde_json::to_string(&event).expect("serialize");
            let deser: Event = serde_json::from_str(&json).expect("deserialize");
            assert_eq!(event, deser);
        }
    }

    #[test]
    fn test_all_intents_roundtrip() {
        let intents = vec![
            Intent::Idle,
            Intent::RequestCall {
                kind: CallKind::Tool,
                name: "n".to_string(),
                args: Value::Null,
                reasoning: "r".to_string(),
            },
            Intent::RequestUser {
                question_id: "q".to_string(),
                prompt: "p".to_string(),
                timeout_seconds: 0,
            },
            Intent::Finish {
                insight: "i".to_string(),
            },
            Intent::Error {
                message: "e".to_string(),
            },
        ];

        for intent in intents {
            let json = serde_json::to_string(&intent).expect("serialize");
            let deser: Intent = serde_json::from_str(&json).expect("deserialize");
            assert_eq!(intent, deser);
        }
    }
}
