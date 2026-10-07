"""
Zwart AI Router
Windows 10+ local model router/orchestrator.

Design goals:
- No network calls from the router itself.
- No shell=True.
- User-editable model names and commands.
- Local deterministic routing by default.
- Safe defaults: confirmation before launch; no "dangerously skip permissions".
- Generic adapter architecture for Codex, Claude Code, Antigravity CLI and custom agents.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, filedialog


APP_DIR = Path(__file__).resolve().parent
CONFIG_PATH = APP_DIR / "config.json"

DEFAULT_CONFIG = {
    "version": 1,
    "general": {
        "default_agent": "auto",
        "default_mode": "auto",
        "auto_delegate": False,
        "confirm_before_run": True,
        "working_directory": ""
    },
    "agents": {}
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        CONFIG_PATH.write_text(json.dumps(DEFAULT_CONFIG, indent=2), encoding="utf-8")
    try:
        data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception as exc:
        raise RuntimeError(f"config.json tidak valid: {exc}") from exc
    if not isinstance(data, dict):
        raise RuntimeError("config.json harus berupa object JSON.")
    return data


def save_config(data: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".json.tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def which(executable: str) -> str | None:
    if not executable:
        return None
    return shutil.which(executable) or (executable if Path(executable).exists() else None)


# ---- Local deterministic router --------------------------------------------

FAST_PATTERNS = [
    r"\brename\b", r"\btypo\b", r"\bformat\b", r"\bprettier\b", r"\bgrep\b",
    r"\blist\b", r"\bwhere is\b", r"\bjelaskan\b", r"\bapa itu\b", r"\bartinya\b",
    r"\bsyntax\b", r"\bconvert\b", r"\bubah warna\b", r"\bbuat regex\b",
    r"\bgit status\b", r"\bgit diff\b", r"\bcek file\b", r"\bcari file\b",
]

HEAVY_PATTERNS = [
    r"\barchitecture\b", r"\barsitektur\b", r"\bredesign\b", r"\broot cause\b",
    r"\bmemory leak\b", r"\bconcurrency\b", r"\bperformance\b", r"\bsecurity\b",
    r"\bproduction\b", r"\bmigration\b", r"\bmigrasi\b", r"\brefactor\b",
    r"\bmulti[- ]file\b", r"\bmonorepo\b", r"\bfrom scratch\b", r"\bdari nol\b",
    r"\bfull stack\b", r"\bwhole repo\b", r"\brepo[- ]wide\b", r"\bdeep\b",
    r"\bkompleks\b", r"\bdebug.*mendalam\b", r"\bdebug.*root\b",
]

RISK_PATTERNS = [
    r"\bpassword\b", r"\bapi[_ -]?key\b", r"\bsecret\b", r"\bcredential\b",
    r"\btoken\b", r"\bdelete\b", r"\bhapus\b", r"\bdestroy\b", r"\bformat disk\b",
    r"\bproduction\b", r"\bdeploy\b", r"\bmigrate\b", r"\bssh\b",
    r"\bregistry\b", r"\bsystem32\b", r"\.env\b",
]


def score_route(prompt: str) -> tuple[str, int, list[str]]:
    text = prompt.strip().lower()
    score = 0
    reasons = []

    if len(prompt) > 1200:
        score += 2
        reasons.append("prompt panjang")
    elif len(prompt) > 500:
        score += 1
        reasons.append("prompt cukup panjang")

    for pat in HEAVY_PATTERNS:
        if re.search(pat, text):
            score += 3
            reasons.append("indikasi task berat")
            break

    for pat in FAST_PATTERNS:
        if re.search(pat, text):
            score -= 2
            reasons.append("indikasi task ringan")
            break

    if text.count("\n") >= 8:
        score += 1
        reasons.append("banyak langkah/konteks")

    if any(x in text for x in ["file ", "folder ", "repo", "repository", "codebase", "project"]):
        score += 1
        reasons.append("melibatkan project/file")

    if re.search(r"\b(and|dan|then|lalu|kemudian)\b", text):
        score += 1
        reasons.append("multi-step")

    risk_hit = False
    for pat in RISK_PATTERNS:
        if re.search(pat, text):
            score = max(score, 4)
            risk_hit = True
            break
    if risk_hit:
        reasons.append("safety floor aktif")

    # Conservative thresholds.
    if score <= -1:
        tier = "fast"
    elif score >= 4:
        tier = "heavy"
    else:
        tier = "balanced"

    if not reasons:
        reasons.append("klasifikasi default")
    return tier, score, reasons


def build_command(agent: dict, model: str, prompt: str) -> list[str]:
    executable = agent.get("executable", "")
    if not executable:
        raise ValueError("Executable agent belum diisi.")

    args = agent.get("args", [])
    if not isinstance(args, list):
        raise ValueError("agents.<name>.args harus berupa array.")

    values = {"{model}": model, "{prompt}": prompt}
    out = []
    for token in args:
        if not isinstance(token, str):
            raise ValueError("Setiap arg command harus string.")
        for k, v in values.items():
            token = token.replace(k, v)
        out.append(token)
    return [executable, *out]


def launch_cli(command: list[str], cwd: str) -> None:
    exe = which(command[0])
    if not exe:
        raise FileNotFoundError(
            f"Executable '{command[0]}' tidak ditemukan di PATH. "
            f"Atur executable di Settings/Models."
        )
    command[0] = exe

    # Never use shell=True. Start a separate console so agent stays interactive.
    creationflags = 0
    if os.name == "nt":
        creationflags = subprocess.CREATE_NEW_CONSOLE
    subprocess.Popen(
        command,
        cwd=cwd or None,
        shell=False,
        creationflags=creationflags,
        close_fds=False,
    )


def open_desktop_ui(executable: str, prompt: str) -> None:
    # Intentionally does NOT automate keystrokes or touch credentials.
    # It only opens the user-selected executable and copies the prompt to clipboard.
    root = tk._default_root
    if root is not None:
        root.clipboard_clear()
        root.clipboard_append(prompt)
        root.update()
    if executable:
        exe = which(executable)
        if not exe:
            raise FileNotFoundError(f"Executable '{executable}' tidak ditemukan.")
        flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
        subprocess.Popen([exe], shell=False, creationflags=flags, close_fds=False)


class RouterApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Zwart AI Router")
        self.geometry("1020x720")
        self.minsize(900, 620)
        self.config_data = load_config()

        self.agent_var = tk.StringVar(value="auto")
        self.mode_var = tk.StringVar(value="auto")
        self.route_var = tk.StringVar(value="AUTO")
        self.model_var = tk.StringVar(value="-")
        self.reason_var = tk.StringVar(value="Masukkan task.")
        self.cwd_var = tk.StringVar(value=self.config_data.get("general", {}).get("working_directory", ""))
        self.confirm_var = tk.BooleanVar(value=self.config_data.get("general", {}).get("confirm_before_run", True))

        self._build_ui()
        self._refresh_agents()

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("vista")
        except tk.TclError:
            pass

        outer = ttk.Frame(self, padding=14)
        outer.pack(fill="both", expand=True)

        top = ttk.Frame(outer)
        top.pack(fill="x")

        ttk.Label(top, text="Zwart AI Router", font=("Segoe UI", 18, "bold")).pack(side="left")
        ttk.Label(top, text="Local heuristic • one app • user-editable models",
                  foreground="#666").pack(side="left", padx=14)

        controls = ttk.LabelFrame(outer, text="Routing", padding=10)
        controls.pack(fill="x", pady=(12, 10))

        ttk.Label(controls, text="Agent").grid(row=0, column=0, sticky="w")
        self.agent_combo = ttk.Combobox(controls, textvariable=self.agent_var, state="readonly", width=24)
        self.agent_combo.grid(row=0, column=1, padx=(6, 18))
        self.agent_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_model_preview())

        ttk.Label(controls, text="Mode").grid(row=0, column=2, sticky="w")
        self.mode_combo = ttk.Combobox(
            controls, textvariable=self.mode_var, state="readonly",
            values=["auto", "fast", "balanced", "heavy"], width=14
        )
        self.mode_combo.grid(row=0, column=3, padx=(6, 18))
        self.mode_combo.bind("<<ComboboxSelected>>", lambda e: self._refresh_model_preview())

        ttk.Label(controls, text="Working directory").grid(row=0, column=4, sticky="w")
        ttk.Entry(controls, textvariable=self.cwd_var, width=34).grid(row=0, column=5, padx=6)
        ttk.Button(controls, text="Browse", command=self._browse_cwd).grid(row=0, column=6)

        ttk.Checkbutton(
            controls, text="Confirm before run", variable=self.confirm_var
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(8, 0))

        self.status = ttk.Label(
            controls,
            textvariable=self.reason_var,
            wraplength=820
        )
        self.status.grid(row=1, column=2, columnspan=5, sticky="w", pady=(8, 0))

        task_frame = ttk.LabelFrame(outer, text="Task", padding=10)
        task_frame.pack(fill="both", expand=True)

        self.task = tk.Text(task_frame, wrap="word", undo=True, font=("Consolas", 11))
        self.task.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(task_frame, orient="vertical", command=self.task.yview)
        scroll.pack(side="right", fill="y")
        self.task.configure(yscrollcommand=scroll.set)

        preview = ttk.LabelFrame(outer, text="Decision preview", padding=10)
        preview.pack(fill="x", pady=10)
        ttk.Label(preview, text="Tier").grid(row=0, column=0, sticky="w")
        ttk.Label(preview, textvariable=self.route_var, font=("Segoe UI", 11, "bold")).grid(row=0, column=1, padx=8)
        ttk.Label(preview, text="Model").grid(row=0, column=2, padx=(22, 0))
        ttk.Label(preview, textvariable=self.model_var, font=("Segoe UI", 10, "bold")).grid(row=0, column=3, padx=8)

        buttons = ttk.Frame(outer)
        buttons.pack(fill="x")
        ttk.Button(buttons, text="Analyze", command=self.analyze).pack(side="left")
        ttk.Button(buttons, text="Run with Router", command=self.run_router).pack(side="left", padx=8)
        ttk.Button(buttons, text="Settings / Models", command=self.open_settings).pack(side="left")
        ttk.Button(buttons, text="Clear", command=lambda: self.task.delete("1.0", "end")).pack(side="right")

        self.task.bind("<KeyRelease>", lambda e: self.after(80, self._refresh_model_preview))

    def _refresh_agents(self):
        agents = self.config_data.get("agents", {})
        values = ["auto", *agents.keys()]
        self.agent_combo["values"] = values
        if self.agent_var.get() not in values:
            self.agent_var.set("auto")
        self._refresh_model_preview()

    def _browse_cwd(self):
        folder = filedialog.askdirectory()
        if folder:
            self.cwd_var.set(folder)

    def analyze(self):
        prompt = self.task.get("1.0", "end").strip()
        if not prompt:
            self.reason_var.set("Masukkan task dulu.")
            return
        tier, score, reasons = score_route(prompt)
        agent_name = self.agent_var.get()
        if agent_name == "auto":
            agent_name = self._pick_agent()
        model = self._get_model(agent_name, tier)
        self.route_var.set(f"{tier.upper()} ({score:+d})")
        self.model_var.set(f"{agent_name}: {model}")
        self.reason_var.set("Alasan: " + ", ".join(reasons))

    def _pick_agent(self) -> str:
        # Generic "auto" preference. User can change the preference in config.json.
        preferred = self.config_data.get("general", {}).get("preferred_agent", "codex")
        if preferred in self.config_data.get("agents", {}):
            return preferred
        for candidate in ("codex", "claude", "antigravity", "custom"):
            if candidate in self.config_data.get("agents", {}):
                return candidate
        raise RuntimeError("Belum ada agent yang dikonfigurasi.")

    def _get_model(self, agent_name: str, tier: str) -> str:
        agent = self.config_data["agents"][agent_name]
        return str(agent.get("models", {}).get(tier, ""))

    def _refresh_model_preview(self):
        prompt = self.task.get("1.0", "end").strip()
        if not prompt:
            self.route_var.set("AUTO")
            self.model_var.set("-")
            self.reason_var.set("Masukkan task.")
            return

        tier, score, reasons = score_route(prompt)
        mode = self.mode_var.get()
        if mode != "auto":
            tier = mode
            reasons = [f"mode manual: {mode}"]

        agent_name = self.agent_var.get()
        if agent_name == "auto":
            agent_name = self._pick_agent()
        model = self._get_model(agent_name, tier)
        self.route_var.set(f"{tier.upper()} ({score:+d})")
        self.model_var.set(f"{agent_name}: {model}")
        self.reason_var.set("Alasan: " + ", ".join(reasons))

    def run_router(self):
        prompt = self.task.get("1.0", "end").strip()
        if not prompt:
            messagebox.showwarning("Task kosong", "Masukkan task terlebih dahulu.")
            return

        tier, score, reasons = score_route(prompt)
        mode = self.mode_var.get()
        if mode != "auto":
            tier = mode

        agent_name = self.agent_var.get()
        if agent_name == "auto":
            agent_name = self._pick_agent()

        agent = self.config_data["agents"].get(agent_name)
        if not agent:
            messagebox.showerror("Agent", f"Agent '{agent_name}' belum dikonfigurasi.")
            return

        model = self._get_model(agent_name, tier)
        self.route_var.set(f"{tier.upper()} ({score:+d})")
        self.model_var.set(f"{agent_name}: {model}")
        self.reason_var.set("Alasan: " + ", ".join(reasons))

        kind = agent.get("kind", "cli")
        cwd = self.cwd_var.get().strip() or self.config_data.get("general", {}).get("working_directory", "").strip()
        if cwd and not Path(cwd).is_dir():
            messagebox.showerror("Working directory", f"Folder tidak ditemukan:\n{cwd}")
            return

        try:
            if kind == "desktop_ui":
                detail = (
                    f"Agent: {agent.get('label', agent_name)}\n"
                    f"Mode: {tier}\n"
                    f"Model: {model}\n\n"
                    "Router akan membuka aplikasi dan menyalin task ke clipboard.\n"
                    "Pemilihan model tetap manual di UI aplikasi."
                )
                if self.confirm_var.get() and not messagebox.askyesno("Konfirmasi", detail):
                    return
                open_desktop_ui(agent.get("executable", ""), prompt)
                messagebox.showinfo("Siap", "Task sudah disalin ke clipboard. Paste di aplikasi agent.")
                return

            command = build_command(agent, model, prompt)
            preview = subprocess.list2cmdline(command)
            if self.confirm_var.get():
                if not messagebox.askyesno(
                    "Jalankan agent?",
                    f"Tier: {tier}\nModel: {model}\n\nCommand:\n{preview}\n\n"
                    "Router tidak memakai shell dan tidak menambahkan bypass permission."
                ):
                    return
            launch_cli(command, cwd)
        except Exception as exc:
            messagebox.showerror("Gagal menjalankan", str(exc))

    def open_settings(self):
        SettingsWindow(self)


class SettingsWindow(tk.Toplevel):
    def __init__(self, parent: RouterApp):
        super().__init__(parent)
        self.parent = parent
        self.title("Models & Agents")
        self.geometry("900x650")

        frame = ttk.Frame(self, padding=12)
        frame.pack(fill="both", expand=True)

        ttk.Label(
            frame,
            text="Edit config.json. Model names bebas diganti sesuai model yang kamu punya.",
            font=("Segoe UI", 10, "bold")
        ).pack(anchor="w", pady=(0, 8))

        self.text = tk.Text(frame, wrap="none", font=("Consolas", 10))
        self.text.pack(fill="both", expand=True)

        data = json.dumps(parent.config_data, indent=2, ensure_ascii=False)
        self.text.insert("1.0", data)

        buttons = ttk.Frame(frame)
        buttons.pack(fill="x", pady=(8, 0))
        ttk.Button(buttons, text="Validate", command=self.validate).pack(side="left")
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left", padx=8)
        ttk.Button(buttons, text="Open config folder", command=lambda: os.startfile(CONFIG_PATH.parent)).pack(side="left")
        ttk.Button(buttons, text="Close", command=self.destroy).pack(side="right")

    def validate(self):
        try:
            data = json.loads(self.text.get("1.0", "end"))
            if not isinstance(data, dict) or "agents" not in data:
                raise ValueError("Top-level harus memiliki 'agents'.")
            messagebox.showinfo("Valid", "JSON valid.")
        except Exception as exc:
            messagebox.showerror("Invalid", str(exc))

    def save(self):
        try:
            data = json.loads(self.text.get("1.0", "end"))
            save_config(data)
            self.parent.config_data = data
            self.parent._refresh_agents()
            messagebox.showinfo("Saved", "Settings tersimpan.")
        except Exception as exc:
            messagebox.showerror("Tidak tersimpan", str(exc))


if __name__ == "__main__":
    try:
        app = RouterApp()
        app.mainloop()
    except Exception as exc:
        messagebox.showerror("Zwart AI Router", str(exc))
        raise
