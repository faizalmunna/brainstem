//! Optional, deliberately inactive Rust extension boundary for Brainstem.
//!
//! The Python engine remains the complete production implementation. This
//! module exposes a stable ABI/status contract so a future measured accelerator
//! can be distributed as a separate wheel without changing the MCP protocol.

use pyo3::prelude::*;
use pyo3::types::PyDict;

const ABI_VERSION: u8 = 1;

#[pyfunction]
fn backend_status(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let status = PyDict::new(py);
    status.set_item("ready", false)?;
    status.set_item("abi_version", ABI_VERSION)?;
    status.set_item("integrity_verified", false)?;
    status.set_item(
        "reason",
        "Rust extension foundation is not promoted: graph-parity and cross-platform benchmarks are required.",
    )?;
    Ok(status.unbind())
}

#[pymodule]
fn brainstem_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(backend_status, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
