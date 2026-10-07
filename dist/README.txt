ZwartFlow v2.0
==============

Router AI agent untuk Windows. Task masuk -> dinilai kompleksitasnya (lokal, tanpa API) -> dipilihkan provider/model (FAST/BALANCED/HEAVY) -> CLI agent (codex / claude / agy / gemini / opencode) dijalankan di console baru.

Cara pakai:
1. Jalankan ZwartFlow.exe (config.json opsional - exe menulis default sendiri jika tidak ada)
2. Ketik task -> Analyze & Route
3. Run Selected

Rebuild dari source: jalankan build_windows.ps1 (butuh Python 3.10+).
