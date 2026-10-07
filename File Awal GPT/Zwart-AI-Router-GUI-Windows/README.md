# Zwart AI Router — Windows GUI

A clean/minimal Windows GUI that detects AI coding agent CLIs, discovers live model catalogs when the provider exposes a machine-readable interface, and routes tasks to Fast/Balanced/Heavy tiers.

## Providers

### Codex
- Finds `codex.exe/codex.cmd` in PATH.
- Discovers catalog through `codex debug models`.
- Model IDs are read from JSON; the app does not hardcode a model list.

### Antigravity
- Finds `agy.exe` in PATH or `%LOCALAPPDATA%\agy\bin\agy.exe`.
- Uses the official `agy models` command.
- Passes the exact model slug to `--model`.

### Claude Code
- Finds `claude` CLI.
- Uses official model aliases `haiku`, `sonnet`, `opus`.
- Anthropic currently has no supported non-interactive `claude models` command, so the app intentionally does not pretend it knows an account-specific live list.
- Desktop App detection is separate and only launches the app; it does not inject credentials or UI-click model selectors.

### Custom agent
Edit `config.json` and define an executable plus a discovery command.

## Auto routing

The router itself is deterministic/local:
- Fast: scoped/simple work
- Balanced: normal implementation/review
- Heavy: architecture, root cause, refactor, production, security, etc.
- Sensitive/risky keywords raise a safety floor to Heavy.

Model tier is inferred from the detected model name. This mapping can be changed in source.

## Security

- `shell=False`
- no router-owned API keys
- no credential scraping
- no permission bypass flags
- confirmation before launch
- model discovery results remain in memory
- provider CLIs can still make their own network/auth calls as designed by the provider

## Build

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

Output:
`dist\Zwart-AI-Router.exe`
