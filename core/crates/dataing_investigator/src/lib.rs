//! Rust state machine for data quality investigations.
//!
//! This crate provides a deterministic, event-sourced state machine
//! for managing investigation workflows. It is designed to be:
//!
//! - **Total**: All state transitions are explicit; illegal transitions become errors
//! - **Deterministic**: Same events always produce the same state
//! - **Serializable**: State snapshots are versioned and backwards-compatible
//! - **Side-effect free**: All side effects happen outside the state machine
//!
//! # Protocol Stability
//!
//! The Event/Intent JSON format is a contract. Changes must be backwards-compatible:
//! - New fields use `#[serde(default)]` for forward compatibility
//! - Existing fields are never renamed without migration
//! - Protocol version is included in all snapshots

#![deny(clippy::unwrap_used, clippy::expect_used, clippy::panic)]

/// Current protocol version for state snapshots.
/// Increment when making breaking changes to serialization format.
pub const PROTOCOL_VERSION: u32 = 1;

pub mod domain;
pub mod protocol;
pub mod state;

// Modules will be added in subsequent tasks:
// pub mod machine;   // fn-17.5

// Re-export types for convenience
pub use domain::{CallKind, CallMeta, Scope};
pub use protocol::{Event, Intent};
pub use state::{Phase, State};

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_protocol_version() {
        assert_eq!(PROTOCOL_VERSION, 1);
    }
}
