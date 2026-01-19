//! Python bindings for dataing_investigator.
//!
//! This module exposes the Rust state machine to Python via PyO3.
//! All functions use panic-free error handling via `PyResult`.

use pyo3::prelude::*;

// Import the core crate (renamed to avoid conflict with pymodule name)
use ::dataing_investigator as core;

/// Returns the protocol version used by the state machine.
#[pyfunction]
fn protocol_version() -> u32 {
    core::PROTOCOL_VERSION
}

/// Python wrapper for the Rust Investigator state machine.
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
    #[staticmethod]
    fn restore(state_json: &str) -> PyResult<Self> {
        let state: core::State = serde_json::from_str(state_json)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
        Ok(Investigator {
            inner: core::Investigator::restore(state),
        })
    }

    /// Get a JSON snapshot of the current state.
    fn snapshot(&self) -> PyResult<String> {
        let state = self.inner.snapshot();
        serde_json::to_string(&state)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))
    }

    /// Process an optional event and return the next intent.
    ///
    /// Args:
    ///     event_json: JSON string of the event, or None for query-only
    ///
    /// Returns:
    ///     JSON string of the resulting intent
    #[pyo3(signature = (event_json=None))]
    fn ingest(&mut self, event_json: Option<&str>) -> PyResult<String> {
        let event = match event_json {
            Some(json) => {
                let e: core::Event = serde_json::from_str(json)
                    .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))?;
                Some(e)
            }
            None => None,
        };

        let intent = self.inner.ingest(event);

        serde_json::to_string(&intent)
            .map_err(|e| PyErr::new::<pyo3::exceptions::PyValueError, _>(e.to_string()))
    }

    /// Get the current phase as a string.
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
    fn current_step(&self) -> u64 {
        self.inner.snapshot().step
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
    m.add_function(wrap_pyfunction!(protocol_version, m)?)?;
    m.add_class::<Investigator>()?;
    Ok(())
}
