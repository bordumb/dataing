//! Domain types for data quality investigations.
//!
//! Foundational types used across the investigation state machine.
//! All types are serializable with serde for protocol stability.

use serde::{Deserialize, Serialize};
use serde_json::Value;
use std::collections::BTreeMap;

/// Security scope for an investigation.
///
/// Contains identity and permission information for access control.
/// Uses BTreeMap for deterministic serialization order.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct Scope {
    /// User identifier.
    pub user_id: String,
    /// Tenant identifier for multi-tenancy.
    pub tenant_id: String,
    /// List of permission strings.
    pub permissions: Vec<String>,
    /// Additional fields for forward compatibility.
    #[serde(default)]
    pub extra: BTreeMap<String, Value>,
}

/// Kind of external call being tracked.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
#[serde(rename_all = "snake_case")]
pub enum CallKind {
    /// LLM inference call.
    Llm,
    /// Tool invocation (SQL query, API call, etc.).
    Tool,
}

/// Metadata about a pending external call.
///
/// Tracks calls that have been initiated but not yet completed,
/// enabling resume-from-snapshot capability.
#[derive(Debug, Clone, Serialize, Deserialize, PartialEq)]
pub struct CallMeta {
    /// Unique identifier for this call.
    pub id: String,
    /// Human-readable name of the call.
    pub name: String,
    /// Kind of call (LLM or Tool).
    pub kind: CallKind,
    /// Phase context when call was initiated.
    pub phase_context: String,
    /// Step number when call was created.
    pub created_at_step: u64,
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_scope_serialization_roundtrip() {
        let mut extra = BTreeMap::new();
        extra.insert("custom_field".to_string(), Value::Bool(true));

        let scope = Scope {
            user_id: "user123".to_string(),
            tenant_id: "tenant456".to_string(),
            permissions: vec!["read".to_string(), "write".to_string()],
            extra,
        };

        let json = serde_json::to_string(&scope).expect("serialize");
        let deserialized: Scope = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(scope, deserialized);
    }

    #[test]
    fn test_scope_extra_defaults_to_empty() {
        let json = r#"{"user_id":"u","tenant_id":"t","permissions":[]}"#;
        let scope: Scope = serde_json::from_str(json).expect("deserialize");

        assert!(scope.extra.is_empty());
    }

    #[test]
    fn test_call_kind_serialization() {
        let llm = CallKind::Llm;
        let tool = CallKind::Tool;

        assert_eq!(serde_json::to_string(&llm).expect("ser"), "\"llm\"");
        assert_eq!(serde_json::to_string(&tool).expect("ser"), "\"tool\"");

        let llm_deser: CallKind = serde_json::from_str("\"llm\"").expect("deser");
        let tool_deser: CallKind = serde_json::from_str("\"tool\"").expect("deser");

        assert_eq!(llm_deser, CallKind::Llm);
        assert_eq!(tool_deser, CallKind::Tool);
    }

    #[test]
    fn test_call_meta_serialization_roundtrip() {
        let meta = CallMeta {
            id: "call_001".to_string(),
            name: "generate_hypotheses".to_string(),
            kind: CallKind::Llm,
            phase_context: "hypothesis_generation".to_string(),
            created_at_step: 5,
        };

        let json = serde_json::to_string(&meta).expect("serialize");
        let deserialized: CallMeta = serde_json::from_str(&json).expect("deserialize");

        assert_eq!(meta, deserialized);
    }

    #[test]
    fn test_btreemap_ordering() {
        // BTreeMap ensures deterministic serialization order
        let mut extra = BTreeMap::new();
        extra.insert("zebra".to_string(), Value::String("z".to_string()));
        extra.insert("alpha".to_string(), Value::String("a".to_string()));
        extra.insert("beta".to_string(), Value::String("b".to_string()));

        let scope = Scope {
            user_id: "u".to_string(),
            tenant_id: "t".to_string(),
            permissions: vec![],
            extra,
        };

        let json = serde_json::to_string(&scope).expect("serialize");
        // BTreeMap should order keys alphabetically
        assert!(json.contains(r#""alpha":"a""#));
        assert!(json.find("alpha").expect("alpha") < json.find("beta").expect("beta"));
        assert!(json.find("beta").expect("beta") < json.find("zebra").expect("zebra"));
    }
}
