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

/// Python module for dataing_investigator.
#[pymodule]
fn dataing_investigator(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(protocol_version, m)?)?;
    Ok(())
}
