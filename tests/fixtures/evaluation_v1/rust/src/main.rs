use crate::config::parse_runtime_configuration;

mod config;

fn main() {
    let _ = parse_runtime_configuration("safe");
}
