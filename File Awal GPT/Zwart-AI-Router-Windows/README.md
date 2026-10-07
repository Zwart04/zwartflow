# Zwart AI Router

MVP Windows 10+ untuk routing task ke Codex CLI, Claude Code, Antigravity CLI, atau agent custom.

## Yang dilakukan

- Menilai kompleksitas task secara lokal dengan heuristic.
- Memilih tier `fast`, `balanced`, atau `heavy`.
- Setiap tier punya model yang bisa kamu ganti sendiri di `config.json`.
- Agent juga bisa diganti: `codex`, `claude`, `antigravity`, `custom`.
- Tidak memakai `shell=True`.
- Tidak memakai network call dari router.
- Tidak meminta atau menyimpan API key.
- Ada konfirmasi sebelum menjalankan command.
- Tidak memakai `--dangerously-skip-permissions`.
- Claude Desktop tersedia sebagai UI launcher: task disalin ke clipboard lalu kamu paste sendiri; pemilihan model tetap manual karena desktop UI tidak menyediakan kontrak CLI untuk routing model.

## Jalankan tanpa build

```bat
run_windows.bat
```

## Build EXE di Windows

Klik kanan PowerShell di folder ini:

```powershell
Set-ExecutionPolicy -Scope Process Bypass
.\build_windows.ps1
```

EXE akan muncul di:

```text
dist\Zwart-AI-Router.exe
```

## Konfigurasi model

Semua model ada di `config.json`, contoh:

```json
"models": {
  "fast": "MODEL_RINGAN",
  "balanced": "MODEL_SEDANG",
  "heavy": "MODEL_BERAT"
}
```

Ganti sesuai model yang ingin kamu gunakan. Tidak ada model yang dikunci oleh aplikasi.

## Adapter

Contoh CLI:

- Codex: `codex exec ...`
- Claude Code: `claude -p ...`
- Antigravity: `agy -p ...`
- Custom: bebas

Argumen juga bisa diganti sendiri dengan placeholder:

- `{model}`
- `{prompt}`

## Batasan penting

Aplikasi ini adalah router/orchestrator, bukan patcher terhadap aplikasi proprietary.

Artinya:
- Codex/Claude Code/Antigravity bisa diroute ketika CLI mereka tersedia dan mendukung `--model`.
- Claude Desktop GUI tidak dipaksa berganti model secara otomatis. Router hanya membuka app + menaruh prompt di clipboard. Ini sengaja dibuat agar tidak melakukan UI automation yang rapuh atau membaca credential/session internal.
- Agent custom tinggal ditambahkan di `config.json`.

Untuk task yang berisiko tinggi, router menaikkan tier ke `heavy` sebagai safety floor. Ini hanya memilih model; permission/sandbox tetap mengikuti agent yang kamu jalankan.
