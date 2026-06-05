# Bevy Reference Snippets

These files are reference code to copy/adapt into the engine repo. They are intentionally not a pinned Bevy plugin.

Files:

- `direction.rs` — world-yaw binning and reduced-N collapse.
- `hit_test.rs` — frame-local hit-test and Bevy anchor conversion formulas.
- `manifest_types.rs` — serde-compatible manifest types for the M1/M2 debug subset.

You will need to add these dependencies in your engine if you copy `manifest_types.rs`:

```toml
serde = { version = "1", features = ["derive"] }
serde_json = "1"
```

The Bevy sprite anchor conversion assumes Bevy custom anchor coordinates are center-origin normalized, with bottom-left `(-0.5, -0.5)` and top-right `(0.5, 0.5)`.
