fn main() {
    println!("cargo:rerun-if-changed=cpp/utf8.cc");
    println!("cargo:rerun-if-changed=asm/has_nul_x86_64.S");
    println!("cargo:rustc-check-cfg=cfg(brainstem_linux_x86_64_asm)");

    cc::Build::new().cpp(true).file("cpp/utf8.cc").flag_if_supported("-std=c++17").compile("brainstem_utf8");

    let target_arch = std::env::var("CARGO_CFG_TARGET_ARCH").unwrap_or_default();
    let target_os = std::env::var("CARGO_CFG_TARGET_OS").unwrap_or_default();
    if target_arch == "x86_64" && target_os == "linux" {
        cc::Build::new().file("asm/has_nul_x86_64.S").compile("brainstem_nul_asm");
        println!("cargo:rustc-cfg=brainstem_linux_x86_64_asm");
    }
}
