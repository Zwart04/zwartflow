ZwartFlow v2.1
==============

Router AI agent untuk Windows. Task masuk -> dinilai kompleksitasnya (lokal, tanpa API)
-> dipilihkan provider/model (FAST/BALANCED/HEAVY) -> CLI agent
(codex / claude / agy / gemini / opencode) dijalankan di console baru.

v2.1: ganti framework ke C# WinForms (.NET Framework 4.8 bawaan Windows).
Exe native ~60 KB, start instan, tanpa Python/PyInstaller.
CLI dan desktop app (Codex, Claude) sekarang menjadi entri terpisah.

Cara pakai:
1. Jalankan ZwartFlow.exe (config.json opsional - exe menulis default sendiri jika tidak ada)
2. Ketik task -> Analyze & Route
3. Run Selected

Rebuild dari source: jalankan build_windows.ps1 (cukup csc.exe bawaan Windows 10).
