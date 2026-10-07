# ZwartFlow

Router AI agent untuk Windows: satu task masuk → sistem menilai kompleksitas → memilih provider/model yang tepat → menjalankan CLI agent di console baru.

**Framework: C# WinForms (.NET Framework 4.8 bawaan Windows).** Exe native ~60 KB, start instan, RAM kecil — tanpa Python, tanpa PyInstaller, tanpa runtime tambahan. UI alur 3 langkah (tulis task → analyze → run) dengan logo asli provider, aman di DPI >100%.

## Provider (app & CLI dipisah)

| Provider | Jenis | Deteksi model |
|---|---|---|
| Codex CLI | CLI | live (`codex debug models`, JSON) |
| Codex App | desktop | deteksi paket Microsoft Store + buka via AUMID |
| Claude CLI | CLI | alias resmi (`haiku` / `sonnet` / `opus`) |
| Claude App | desktop | alias `claude-desktop.exe` / paket Store |
| Antigravity CLI | CLI | live (`agy models`) |
| Antigravity IDE | desktop | path standar / paket Store |
| Gemini CLI | CLI | alias resmi |
| OpenCode CLI | CLI | live (`opencode models`) |
| Command Code CLI | CLI | live (`cmdc --list-models`, 90+ model) |
| Custom agent | CLI | isi path di config |

Deteksi CLI mendukung **wildcard path** (mis. `%LOCALAPPDATA%\OpenAI\Codex\bin\*\codex.exe` untuk CLI terinstal di folder versi) dan **paket Microsoft Store** via inventori `Get-AppxPackage`.

## Fitur

- **Auto routing lokal** — task dinilai dari panjang context, jumlah langkah, keyword kompleksitas, paralelisasi, dan safety floor (task destruktif dipaksa ke model berat). Tanpa API call, tanpa telemetry.
- **Rekomendasi delegasi** — langsung / worker paralel / planner → workers → reviewer.
- **UI responsif** — pemindaian CLI per-provider di background thread; layout Dock/TableLayoutPanel yang aman di DPI 125–150%.
- **Live model catalog** — dibaca langsung dari CLI yang terpasang, tidak ada daftar model palsu.
- **Custom provider** — tambah agent baru hanya dengan meng-edit `config.json`.
- **Aman** — tanpa shell chaining (`.cmd` dibungkus `cmd /c` hanya untuk discovery), tanpa bypass permission, tanpa penyimpanan credential.

## Cara pakai

1. Jalankan `dist/ZwartFlow.exe` (jika `config.json` tidak ada, exe menulis default sendiri).
2. Ketik task → **Analyze & Route** → kartu hasil menampilkan tier (FAST / BALANCED / HEAVY), model terpilih, dan rekomendasi delegasi.
3. **Run Selected** → agent dijalankan di console baru (dialog konfirmasi detail command dulu). Klik **Use** pada model mana pun untuk pilih manual.

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
  "executable_candidates": ["path / di PATH / dengan * wildcard"],
  "desktop_candidates": [],
  "store": "^NamaPaketStore$",
  "discover": {
    "type": "command_json | command_table | aliases",
    "command": ["sub", "command"]
  },
  "run": {
    "command": ["{model}", "{prompt}"]
  }
}
```

- `kind: "cli"` + `desktop_candidates` terisi & app ketemu → kartu CLI dan kartu App otomatis dibedakan.
- `store` → khusus kind desktop: regex nama paket Appx untuk deteksi & launch via `shell:appsFolder`.
- `command_json` → output JSON dipindai untuk field model.
- `command_table` → dipindai per-baris (kolom pertama dianggap ID).
- `aliases` → daftar model statis `{ "id", "label", "tier" }`.
