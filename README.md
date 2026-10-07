# ZwartFlow

Router AI agent untuk Windows: satu task masuk → sistem menilai kompleksitas → memilih provider/model yang tepat → menjalankan CLI agent di console baru.

**Framework: C# WinForms (.NET Framework 4.8 bawaan Windows).** Exe native ~60 KB, start instan, RAM kecil — tanpa Python, tanpa PyInstaller, tanpa runtime tambahan.

## Provider (app & CLI dipisah)

| Provider | Jenis | Deteksi model |
|---|---|---|
| Codex CLI | CLI | live (`codex debug models`, JSON) |
| Codex App | desktop | buka langsung app |
| Claude CLI | CLI | alias resmi (`haiku` / `sonnet` / `opus` — tidak ada command list resmi) |
| Claude App | desktop | buka langsung app |
| Antigravity | CLI | live (`agy models`) |
| Gemini CLI | CLI | alias resmi |
| OpenCode | CLI | live (`opencode models`) |
| Custom agent | CLI | isi path di config |

## Fitur

- **Auto routing lokal** — task dinilai dari panjang context, jumlah langkah, keyword kompleksitas, paralelisasi, dan safety floor (task destruktif dipaksa ke model berat). Tanpa API call, tanpa telemetry.
- **Rekomendasi delegasi** — langsung / worker paralel / planner → workers → reviewer.
- **Discovery tanpa buat UI freeze** — pemindaian CLI berjalan per-provider di background thread; UI tetap responsif, hasil masuk satu-satu.
- **Live model catalog** — dibaca langsung dari CLI yang terpasang, tidak ada daftar model palsu.
- **Custom provider** — tambah agent baru hanya dengan meng-edit `config.json` (path CLI, command discovery, run args).
- **Aman** — tanpa shell chaining, `.cmd` dibungkus `cmd /c` hanya untuk discovery, tanpa bypass permission, tanpa penyimpanan credential.

## Cara pakai

1. Jalankan `dist/ZwartFlow.exe` (jika `config.json` tidak ada, exe menulis default sendiri).
2. Ketik task → **Analyze & Route** → router memilih tier (FAST / BALANCED / HEAVY) + model.
3. **Run Selected** → agent dijalankan di console baru (dialog konfirmasi detail command dulu).

Semua CLI diberlakukan sebagai command asli milik provider-knya (codex/claude/agy melakukan auth sendiri; ZwartFlow hanya memanggil command-nya).

## Build dari source

```powershell
.\build_windows.ps1
# hasil: dist\ZwartFlow.exe + dist\config.json
```

Kebutuhan build: cukup Windows 10 (csc.exe .NET Framework 4.8 bawaan Windows). Tanpa SDK, tanpa install.

## Format provider baru di config.json

```json
"nama": {
  "name": "Nama Agent",
  "kind": "cli",
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

- `kind: "cli"` + `desktop_candidates` terisi & app ketemu → kartu CLI dan kartu App otomatis dibedakan.
- `command_json` → output JSON dipindai untuk field model.
- `command_table` → dipindai per-baris (kolom pertama dianggap ID).
- `aliases` → daftar model statis `{ "id", "label", "tier" }`.
