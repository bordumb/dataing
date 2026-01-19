//! Python bindings for dataing_investigator.
//!
//! This module exposes the Rust state machine to Python via PyO3.
//! All functions use panic-free error handling via `PyResult`.
//!
//! # Error Handling
//!
//! Custom exceptions are provided for fine-grained error handling:
//! - `StateError`: Base exception for all state machine errors
//! - `SerializationError`: JSON serialization/deserialization failures
//! - `InvalidTransitionError`: Invalid state transitions
//!
//! # Panic Safety
//!
//! The `panic = "unwind"` profile setting and `catch_unwind` ensure
//! that any unexpected Rust panic is caught and converted to a Python
//! exception rather than crashing the interpreter.

use pyo3::prelude::*;
use std::panic::{catch_unwind, AssertUnwindSafe};

// Import the core crate (renamed to avoid conflict with pymodule name)
use ::dataing_investigator as core;

// Custom exceptions for Python error handling
pyo3::create_exception!(dataing_investigator, StateError, pyo3::exceptions::PyException);
pyo3::create_exception!(dataing_investigator, SerializationError, StateError);
pyo3::create_exception!(dataing_investigator, InvalidTransitionError, StateError);

/// Returns the protocol version used by the state machine.
#[pyfunction]
fn protocol_version() -> u32 {
    core::PROTOCOL_VERSION
}

/// Python wrapper for the Rust Investigator state machine.
///
/// This class provides a panic-safe interface to the Rust state machine.
/// All methods return Python exceptions on error, never panic.
#[pyclass]
pub struct Investigator {
    inner: core::Investigator,
}

#[pymethods]
impl Investigator {
    /// Create a new Investigator in initial state.
    #[new]
    fn new() -> Self {
        Investigator {
            inner: core::Investigator::new(),
        }
    }

    /// Restore an Investigator from a JSON state snapshot.
    ///
    /// Args:
    ///     state_json: JSON string of a previously saved state snapshot
    ///
    /// Returns:
    ///     Investigator restored to the saved state
    ///
    /// Raises:
    ///     SerializationError: If the JSON is invalid or doesn't match schema
    #[staticmethod]
    fn restore(state_json: &str) -> PyResult<Self> {
        let state: core::State = serde_json::from_str(state_json)
            .map_err(|e| SerializationError::new_err(format!("Invalid state JSON: {}", e)))?;
        Ok(Investigator {
            inner: core::Investigator::restore(state),
        })
    }

    /// Get a JSON snapshot of the current state.
    ///
    /// Returns:
    ///     JSON string that can be used with `restore()`
    ///
    /// Raises:
    ///     SerializationError: If serialization fails (should never happen)
    fn snapshot(&self) -> PyResult<String> {
        let state = self.inner.snapshot();
        serde_json::to_string(&state)
            .map_err(|e| SerializationError::new_err(format!("Snapshot serialization failed: {}", e)))
    }

    /// Process an optional event and return the next intent.
    ///
    /// This is the main entry point for interacting with the state machine.
    /// Call with an event JSON to advance the state, or with None to query
    /// the current intent without providing new input.
    ///
    /// Args:
    ///     event_json: JSON string of the event, or None for query-only
    ///
    /// Returns:
    ///     JSON string of the resulting intent
    ///
    /// Raises:
    ///     SerializationError: If event JSON is invalid or intent serialization fails
    ///     InvalidTransitionError: If the event causes an invalid state transition
    #[pyo3(signature = (event_json=None))]
    fn ingest(&mut self, event_json: Option<&str>) -> PyResult<String> {
        // Parse event if provided
        let event = match event_json {
            Some(json) => {
                let e: core::Event = serde_json::from_str(json)
                    .map_err(|e| SerializationError::new_err(format!("Invalid event JSON: {}", e)))?;
                Some(e)
            }
            None => None,
        };

        // Use catch_unwind for panic safety at FFI boundary
        let result = catch_unwind(AssertUnwindSafe(|| {
            self.inner.ingest(event)
        }));

        let intent = match result {
            Ok(intent) => intent,
            Err(_) => {
                return Err(StateError::new_err("Internal error: Rust panic caught at FFI boundary"));
            }
        };

        // Note: Intent::Error is a valid response, not an exception.
        // The caller can inspect the intent type in Python to handle errors.

        serde_json::to_string(&intent)
            .map_err(|e| SerializationError::new_err(format!("Intent serialization failed: {}", e)))
    }

    /// Get the current phase as a string.
    ///
    /// Returns one of: 'init', 'gathering_context', 'generating_hypotheses',
    /// 'evaluating_hypotheses', 'awaiting_user', 'synthesizing', 'finished', 'failed'
    fn current_phase(&self) -> String {
        let state = self.inner.snapshot();
        match &state.phase {
            core::Phase::Init => "init".to_string(),
            core::Phase::GatheringContext { .. } => "gathering_context".to_string(),
            core::Phase::GeneratingHypotheses { .. } => "generating_hypotheses".to_string(),
            core::Phase::EvaluatingHypotheses { .. } => "evaluating_hypotheses".to_string(),
            core::Phase::AwaitingUser { .. } => "awaiting_user".to_string(),
            core::Phase::Synthesizing { .. } => "synthesizing".to_string(),
            core::Phase::Finished { .. } => "finished".to_string(),
            core::Phase::Failed { .. } => "failed".to_string(),
        }
    }

    /// Get the current step (logical clock value).
    ///
    /// The step counter increments with each event processed.
    fn current_step(&self) -> u64 {
        self.inner.snapshot().step
    }

    /// Check if the investigation is in a terminal state.
    ///
    /// Returns True if phase is 'finished' or 'failed'.
    fn is_terminal(&self) -> bool {
        let phase = self.current_phase();
        phase == "finished" || phase == "failed"
    }

    /// Get string representation.
    fn __repr__(&self) -> String {
        format!(
            "Investigator(phase='{}', step={})",
            self.current_phase(),
            self.current_step()
        )
    }
}

/// Python module for dataing_investigator.
#[pymodule]
fn dataing_investigator(m: &Bound<'_, PyModule>) -> PyResult<()> {
    // Add functions
    m.add_function(wrap_pyfunction!(protocol_version, m)?)?;

    // Add classes
    m.add_class::<Investigator>()?;

    // Add exceptions
    m.add("StateError", m.py().get_type::<StateError>())?;
    m.add("SerializationError", m.py().get_type::<SerializationError>())?;
    m.add("InvalidTransitionError", m.py().get_type::<InvalidTransitionError>())?;

    Ok(())
}
