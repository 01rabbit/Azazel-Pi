# API Reference

This reference documents the Python modules that make up the Azazel control
plane. The intent is to provide enough context for operators to extend or mock
the behaviour during testing.

## `azctl.tui_zero` - Unified Textual TUI

Azazel-Edge now uses the Azazel-Zero style unified Textual TUI.  
The legacy `azctl/menu` modular implementation was removed.

### Runtime modules

```
azctl/tui_zero.py
azctl/tui_zero_textual.py
```

### Entry point

- CLI: `python3 -m azctl.cli menu`
- Internally, `azctl.cli.cmd_menu()` calls `azctl.tui_zero.run_menu()`

### Primary behaviors

- Loads state from `runtime/ui_snapshot.json` when available.
- Falls back to `python3 -m azctl.cli status --json`.
- Menu actions map to mode events:
  - `stage_open` -> `portal`
  - `reprobe` -> `shield`
  - `contain` -> `lockdown`

### Dependencies

- `textual` (required for menu TUI)
- `rich` (status/TUI rendering helpers used elsewhere)

## `azazel_core.state_machine`

- `State(name: str, description: str = "")`
- `Event(name: str, severity: int = 0)`
- `Transition(source, target, condition, action=None)`
- `StateMachine(initial_state, config_path=None, window_size=5)` provides:
  - `add_transition(transition)` – register a new transition.
  - `dispatch(event)` – evaluate transitions from the current state.
  - `reset()` – return to the initial state and clear score history.
  - `summary()` – dictionary suitable for API responses.
  - `get_thresholds()` – read shield/lockdown thresholds and unlock timers
    from `azazel.yaml`.
  - `get_actions_preset()` – fetch the delay/shape/block preset for the
    current mode.
  - `apply_score(severity)` – update the moving-average score window,
    transition to the correct mode, and return evaluation metadata.

## `azazel_core.scorer`

`ScoreEvaluator` computes cumulative severity and provides `classify(score)`
which returns `normal`, `guarded`, `elevated`, or `critical`.

## `azazel_core.actions`

`DelayAction`, `ShapeAction`, `BlockAction`, and `RedirectAction` derive from the
common `Action` interface and expose `plan(target)` iterators. Each yields
`ActionResult` objects that describe tc/nftables commands without executing
side-effects.

## `azazel_core.ingest`

`SuricataTail` and `CanaryTail` read JSON logs from disk and emit `Event`
instances. They are intentionally deterministic, easing unit test coverage.

## `azazel_core.api`

`APIServer` is a minimal dispatcher used by future HTTP front-ends. The bundled
handler `add_health_route(version)` returns a `HealthResponse` dataclass.

## `azctl.cli`

`build_machine()` wires the portal/shield/lockdown states. `load_events(path)`
loads YAML describing synthetic events. `main(argv)` powers the systemd service
by feeding events into `AzazelDaemon`, which applies score-based decisions and
writes `decisions.log` entries containing the chosen mode and action presets.

## HTTP endpoints

### `POST /v1/mode`

The controller exposes a minimal HTTP interface for supervised overrides. A
`POST` request to `/v1/mode` with a JSON body such as `{ "mode": "shield" }`
will transition the daemon to the requested state. The handler immediately
applies the corresponding preset from `azazel.yaml` (delay, shaping rate, and
block flag) and records the outcome to `decisions.log` alongside operator
metadata. Preset values are documented in the operations guide's
[mode action table](OPERATIONS.md#mode-presets).

## Scripts

- `scripts/suricata_generate.py` renders the Suricata YAML template.
- `scripts/nft_apply.sh` and `scripts/tc_reset.sh` manage enforcement tools.
- `scripts/sanity_check.sh` prints warnings if dependent services are inactive.
- `scripts/rollback.sh` removes installed assets.
- `scripts/resolve_allowlist.py` resolves medical FQDNs to CIDRs and writes the
  lockdown nftables allowlist used by the generated template.
