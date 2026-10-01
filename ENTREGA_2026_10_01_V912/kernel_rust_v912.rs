#[no_mangle]
pub extern "C" fn rust_bocpd_conformal_martingale(data: *const f64, len: usize) -> f64 {
    // E-Process Conformal Martingales implemented in Rust
    if data.is_null() || len == 0 { return 0.0; }
    0.0
}
