# ZwartFlow

Router AI agent untuk Windows: satu task masuk → sistem menilai kompleksitas → memilih provider/model yang tepat → menjalankan CLI agent di console baru.

Provider yang didukung:

| Provider | Deteksi CLI | Deteksi model |
|---|---|---|
| Codex (OpenAI) | ✓ | live (`codex debug models`, JSON) |
| Claude Code (Anthropic) | ✓ | alias (`haiku` / `sonnet` / `opus` — tidak ada command list yang resmi) |
| Antigravity (Google) | ✓ | live (`agy models`) |
| Gemini CLI (Google) | ✓ | alias resmi |
| OpenCode | ✓ | live (`opencode models`) |
| Custom agent | isi path di config | alias / command kustom |

## Fitur

- **Auto routing lokal** — task dinilai dari panjang context, jumlah langkah, keyword kompleksitas, paralelisasi, dan safety floor (task destruktif dipaksa ke model berat). Tanpa API call, tanpa telemetry.
- **Rekomendasi delegasi** — langsung / worker paralel / planner → workers → reviewer.
- **Live model catalog** — dibaca langsung dari CLI yang terpasang, tidak ada daftar model palsu.
- **Custom provider** — tambah agent baru hanya dengan meng-edit `config.json` (path CLI, command discovery, run args).
- **Aman** — `shell=False`, tanpa bypass permission, tanpa penyimpanan credential.

## Cara pakai

1. Jalankan `dist/ZwartFlow.exe` (tidak butuh Python; jika config.json tidak ada, exe menulis default).
2. Ketik task → **Analyze & Route** → router memilih tier (FAST / BALANCED / HEAVY) + model.
3. **Run Selected** → agent dijalankan di console baru (ada dialog konfirmasi detail command dulu).

Semua CLI diberlakukan sebagai command asli milik provider-knya (codex/claude/agy melakukan auth sendiri; app ini hanya memanggil command-nya).

## Build dari source

```powershell
.\build_windows.ps1
# hasil: dist\ZwartFlow.exe + dist\config.json
```

Kebutuhan build: Python 3.10+. `PyInstaller` diinstal otomatis ke `.venv` oleh script.

## Format provider baru di config.json

```json
"nama": {
  "name": "Nama Agent",
  "executable_candidates": ["path / di PATH"],
  "desktop_candidates": [],
  "discover": {
    "type": "command_json | command_table | aliases",
    "command": ["sub", "command"]
  },
  "run": {
    "command": ["{model}", "{prompt}"]   // {model} dan {prompt} di-substitute
  }
}
```

- `command_json` → output JSON dipindai untuk field model.
- `command_table` → dipindai per-baris (kolom pertama dianggap ID).
- `aliases` → daftar model statis `{ "id", "label", "tier" }`.
