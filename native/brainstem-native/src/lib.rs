//! Optional native source-ingest accelerator for Brainstem.
//!
//! The Python graph/parser remains the portable authority. Rust performs the
//! independent, parallelizable portion of indexing: reading safe file paths,
//! rejecting binary or malformed UTF-8 input, and calculating SHA-256 content
//! hashes. C++ owns strict UTF-8 validation; Linux x86-64 uses one isolated
//! assembly NUL scan, with a C++ fallback everywhere else.

use pyo3::prelude::*;
use pyo3::types::PyDict;
use rayon::prelude::*;
use sha2::{Digest, Sha256};

const ABI_VERSION: u8 = 1;

unsafe extern "C" {
    fn brainstem_utf8_validate(data: *const u8, length: usize) -> i32;
    fn brainstem_has_nul_fallback(data: *const u8, length: usize) -> i32;
}

#[cfg(brainstem_linux_x86_64_asm)]
unsafe extern "C" {
    fn brainstem_has_nul_asm(data: *const u8, length: usize) -> i32;
}

fn has_nul(bytes: &[u8]) -> bool {
    #[cfg(brainstem_linux_x86_64_asm)]
    unsafe {
        return brainstem_has_nul_asm(bytes.as_ptr(), bytes.len()) != 0;
    }
    #[cfg(not(brainstem_linux_x86_64_asm))]
    unsafe {
        brainstem_has_nul_fallback(bytes.as_ptr(), bytes.len()) != 0
    }
}

fn is_utf8(bytes: &[u8]) -> bool {
    unsafe { brainstem_utf8_validate(bytes.as_ptr(), bytes.len()) != 0 }
}

#[pyfunction]
fn backend_status(py: Python<'_>) -> PyResult<Py<PyDict>> {
    let status = PyDict::new(py);
    // This module accelerates source ingest, not complete graph construction.
    // Keeping `ready` false prevents native.py from ever claiming native graph
    // parity or selecting it as the full indexing engine.
    status.set_item("ready", false)?;
    status.set_item("source_batch_reader", true)?;
    status.set_item("abi_version", ABI_VERSION)?;
    status.set_item("integrity_verified", false)?;
    status.set_item("reason", "Native source ingest is optional; Python remains the graph authority.")?;
    Ok(status.unbind())
}

#[pyfunction]
fn read_utf8_sources(py: Python<'_>, paths: Vec<String>) -> Vec<(String, Vec<u8>, String)> {
    py.allow_threads(|| {
        paths
            .par_iter()
            .filter_map(|path| {
                let bytes = std::fs::read(path).ok()?;
                if has_nul(&bytes) || !is_utf8(&bytes) {
                    return None;
                }
                let hash = format!("{:x}", Sha256::digest(&bytes));
                Some((path.clone(), bytes, hash))
            })
            .collect()
    })
}

#[pymodule]
fn brainstem_native(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(backend_status, module)?)?;
    module.add_function(wrap_pyfunction!(read_utf8_sources, module)?)?;
    module.add("__version__", env!("CARGO_PKG_VERSION"))?;
    Ok(())
}
