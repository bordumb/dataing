//! Protocol types for state machine communication.
//!
//! Defines the Event and Intent types that form the contract between
//! the Python runtime and Rust state machine.
//!
//! # Wire Format
//!
//! Events and Intents use tagged JSON serialization:
//! ```json
//! {"type": "Start", "payload": {"objective": "...", "scope": {...}}}
//! {"type": "Call", "payload": {"call_id": "...", "kind": "llm", ...}}
//! ```
//!
//! # Stability
//!
//! These types form a versioned protocol contract. Changes must be
//! backwards-compatible (use `#[serde(default)]` for new fields).

use serde::{Deserialize, Serialize};
use serde_json::Value;

use crate::domain::{CallKind, Scope};

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

    /// Result of an external call (LLM or tool).
    CallResult {
        /// ID matching the originating Intent::Call.
        call_id: String,
        /// Result payload from the call.
        output: Value,
    },

    /// User response to a RequestUser intent.
    UserResponse {
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
    Call {
        /// Unique identifier for this call (for correlating results).
        call_id: String,
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
        /// Question to present to the user.
        question: String,
    },

    /// Investigation finished successfully.
    Finish {
        /// Final insight/conclusion.
        insight: String,
    },

    /// Investigation ended with an error.
    Error {
        /// Error message.
        message: String,
    },
}

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
    fn test_event_start_serialization() {
        let event = Event::Start {
            objective: "Find root cause".to_string(),
            scope: test_scope(),
        };

        let json = serde_json::to_string(&event).expect("serialize");
        assert!(json.contains(r#""type":"Start""#));
        assert!(json.contains(r#""payload""#));
        assert!(json.contains(r#""objective":"Find root cause""#));

        let deser: Event = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(event, deser);
    }

    #[test]
    fn test_event_call_result_serialization() {
        let event = Event::CallResult {
            call_id: "call_001".to_string(),
            output: serde_json::json!({"hypotheses": ["h1", "h2"]}),
        };

        let json = serde_json::to_string(&event).expect("serialize");
        assert!(json.contains(r#""type":"CallResult""#));

        let deser: Event = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(event, deser);
    }

    #[test]
    fn test_event_user_response_serialization() {
        let event = Event::UserResponse {
            content: "Yes, proceed".to_string(),
        };

        let json = serde_json::to_string(&event).expect("serialize");
        assert!(json.contains(r#""type":"UserResponse""#));

        let deser: Event = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(event, deser);
    }

    #[test]
    fn test_event_cancel_serialization() {
        let event = Event::Cancel;

        let json = serde_json::to_string(&event).expect("serialize");
        // Unit variant with tag but no content
        assert!(json.contains(r#""type":"Cancel""#));

        let deser: Event = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(event, deser);
    }

    #[test]
    fn test_intent_idle_serialization() {
        let intent = Intent::Idle;

        let json = serde_json::to_string(&intent).expect("serialize");
        assert!(json.contains(r#""type":"Idle""#));

        let deser: Intent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(intent, deser);
    }

    #[test]
    fn test_intent_call_serialization() {
        let intent = Intent::Call {
            call_id: "call_002".to_string(),
            kind: CallKind::Llm,
            name: "generate_hypotheses".to_string(),
            args: serde_json::json!({"prompt": "Analyze anomaly"}),
            reasoning: "Need to generate initial hypotheses".to_string(),
        };

        let json = serde_json::to_string(&intent).expect("serialize");
        assert!(json.contains(r#""type":"Call""#));
        assert!(json.contains(r#""kind":"llm""#));

        let deser: Intent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(intent, deser);
    }

    #[test]
    fn test_intent_request_user_serialization() {
        let intent = Intent::RequestUser {
            question: "Should I proceed with the risky query?".to_string(),
        };

        let json = serde_json::to_string(&intent).expect("serialize");
        assert!(json.contains(r#""type":"RequestUser""#));

        let deser: Intent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(intent, deser);
    }

    #[test]
    fn test_intent_finish_serialization() {
        let intent = Intent::Finish {
            insight: "Root cause: upstream ETL job failed".to_string(),
        };

        let json = serde_json::to_string(&intent).expect("serialize");
        assert!(json.contains(r#""type":"Finish""#));

        let deser: Intent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(intent, deser);
    }

    #[test]
    fn test_intent_error_serialization() {
        let intent = Intent::Error {
            message: "Maximum retries exceeded".to_string(),
        };

        let json = serde_json::to_string(&intent).expect("serialize");
        assert!(json.contains(r#""type":"Error""#));

        let deser: Intent = serde_json::from_str(&json).expect("deserialize");
        assert_eq!(intent, deser);
    }

    #[test]
    fn test_all_events_roundtrip() {
        let events = vec![
            Event::Start {
                objective: "test".to_string(),
                scope: test_scope(),
            },
            Event::CallResult {
                call_id: "c1".to_string(),
                output: Value::Null,
            },
            Event::UserResponse {
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
            Intent::Call {
                call_id: "c".to_string(),
                kind: CallKind::Tool,
                name: "n".to_string(),
                args: Value::Null,
                reasoning: "r".to_string(),
            },
            Intent::RequestUser {
                question: "q".to_string(),
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
