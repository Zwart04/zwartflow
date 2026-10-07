ZwartFlow v2.2
==============

Router AI agent untuk Windows. Task masuk -> dinilai kompleksitasnya (lokal, tanpa API)
-> dipilihkan provider/model (FAST/BALANCED/HEAVY) -> CLI agent
(codex / claude / agy / gemini / opencode / cmdc) dijalankan di console baru.

v2.2: tampilan dirancang ulang (alur 3 langkah, logo asli provider, layout aman di DPI >100%),
deteksi CLI wildcard path (Codex/Claude terinstal di folder versi), deteksi app Microsoft
Store + buka via AUMID, provider baru Command Code CLI (live --list-models).

Cara pakai:
1. Jalankan ZwartFlow.exe (config.json opsional - exe menulis default sendiri jika tidak ada)
2. Ketik task -> Analyze & Route
3. Run Selected

Rebuild dari source: jalankan build_windows.ps1 (cukup csc.exe bawaan Windows 10).
