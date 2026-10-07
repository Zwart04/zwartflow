from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import sys
import threading
from pathlib import Path

import tkinter as tk
from tkinter import Tk, Toplevel, StringVar, Text, END, messagebox, ttk


# ---------------------------------------------------------------- paths ----

def app_dir() -> Path:
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


CONFIG_PATH = app_dir() / "config.json"


DEFAULT_CONFIG = {
    "version": 4,
    "ui": {"preferred_provider": "codex", "confirm_before_run": True},
    "router": {
        "simple_threshold": -1,
        "heavy_threshold": 4,
        "max_parallel_workers": 4,
    },
    "providers": {
        "codex": {
            "name": "Codex",
            "vendor": "OpenAI",
            "executable_candidates": ["codex.exe", "codex.cmd", "codex"],
            "desktop_candidates": [
                "%LOCALAPPDATA%\\Microsoft\\WindowsApps\\Codex.exe",
                "%LOCALAPPDATA%\\Programs\\Codex\\Codex.exe",
            ],
            "discover": {"type": "command_json", "command": ["debug", "models"], "timeout": 45},
            "run": {"command": ["exec", "--model", "{model}", "{prompt}"]},
        },
        "claude": {
            "name": "Claude Code",
            "vendor": "Anthropic",
            "executable_candidates": ["claude.exe", "claude.cmd", "claude"],
            "desktop_candidates": [
                "%LOCALAPPDATA%\\Programs\\Claude\\Claude.exe",
                "%LOCALAPPDATA%\\AnthropicClaude\\Claude.exe",
            ],
            "discover": {
                "type": "aliases",
                "aliases": [
                    {"id": "haiku", "label": "Haiku", "tier": "fast"},
                    {"id": "sonnet", "label": "Sonnet", "tier": "balanced"},
                    {"id": "opus", "label": "Opus", "tier": "heavy"},
                ],
                "note": "Claude Code tidak punya command resmi untuk list model non-interaktif; ditampilkan sebagai alias.",
            },
            "run": {"command": ["-p", "--model", "{model}", "{prompt}"]},
        },
        "antigravity": {
            "name": "Antigravity",
            "vendor": "Google",
            "executable_candidates": ["agy.exe", "agy.cmd", "agy", "%LOCALAPPDATA%\\agy\\bin\\agy.exe"],
            "desktop_candidates": [
                "%LOCALAPPDATA%\\Programs\\Antigravity\\Antigravity.exe",
            ],
            "discover": {"type": "command_table", "command": ["models"], "timeout": 25},
            "run": {"command": ["-p", "{prompt}", "--model", "{model}"]},
        },
        "gemini": {
            "name": "Gemini CLI",
            "vendor": "Google",
            "executable_candidates": ["gemini.exe", "gemini.cmd", "gemini"],
            "desktop_candidates": [],
            "discover": {
                "type": "aliases",
                "aliases": [
                    {"id": "gemini-2.5-flash", "label": "2.5 Flash", "tier": "fast"},
                    {"id": "gemini-2.5-pro", "label": "2.5 Pro", "tier": "heavy"},
                ],
                "note": "Alias resmi Google; cek `gemini --help` untuk varian terbaru.",
            },
            "run": {"command": ["-m", "{model}", "{prompt}"]},
        },
        "opencode": {
            "name": "OpenCode",
            "vendor": "Community",
            "executable_candidates": ["opencode.exe", "opencode.cmd", "opencode"],
            "desktop_candidates": [],
            "discover": {"type": "command_table", "command": ["models"], "timeout": 20},
            "run": {"command": ["run", "--model", "{model}", "{prompt}"]},
        },
        "custom": {
            "name": "Custom Agent",
            "vendor": "Lainnya",
            "executable_candidates": [],
            "desktop_candidates": [],
            "discover": {
                "type": "aliases",
                "aliases": [
                    {"id": "my-fast", "label": "Fast (edit config.json)", "tier": "fast"},
                    {"id": "my-heavy", "label": "Heavy (edit config.json)", "tier": "heavy"},
                ],
                "note": "Isi path CLI + alias model di config.json.",
            },
            "run": {"command": ["--model", "{model}", "{prompt}"]},
        },
    },
}


def load_config() -> dict:
    try:
        return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
    except Exception:
        return json.loads(json.dumps(DEFAULT_CONFIG))


def save_config(data: dict) -> None:
    tmp = CONFIG_PATH.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG_PATH)


def merge_defaults(cfg: dict) -> dict:
    base = json.loads(json.dumps(DEFAULT_CONFIG))
    base["providers"].update(cfg.get("providers", {}))
    for k in ("ui", "router"):
        base[k].update(cfg.get(k, {}))
    return base


# ------------------------------------------------------------ discovery ----

def expand(v: str) -> str:
    return os.path.expandvars(os.path.expanduser(v))


def resolve(cli_candidates) -> str | None:
    for raw in cli_candidates or []:
        if not raw:
            continue
        v = expand(raw)
        found = shutil.which(v)
        if found:
            return found
        p = Path(v)
        if p.is_file():
            return str(p)
    return None


def resolve_desktop(desktop_candidates) -> str | None:
    for raw in desktop_candidates or []:
        if not raw:
            continue
        p = Path(expand(raw))
        if p.is_file():
            return str(p)
    return None


def capture(exe: str, args: list[str], timeout: float):
    p = subprocess.run(
        [exe, *args], capture_output=True, text=True, encoding="utf-8",
        errors="replace", timeout=timeout, shell=False,
    )
    return p.returncode, p.stdout, p.stderr


def tier_for(text: str) -> str:
    s = text.lower()
    if re.search(r"\b(mini|nano|small|lite|haiku|flash)\b", s):
        return "fast"
    if re.search(r"\b(opus|pro|ultra|max|heavy|xhigh|flagship)\b", s):
        return "heavy"
    return "balanced"


MODEL_ID_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:/+\-]*$")


def walk_json_models(v, out):
    if isinstance(v, dict):
        mid = next((v[k] for k in ("slug", "id", "model", "model_id")
                    if isinstance(v.get(k), str) and v[k].strip()), None)
        label = next((v[k] for k in ("display_name", "name", "label", "title")
                      if isinstance(v.get(k), str) and v[k].strip()), "")
        if mid and MODEL_ID_RE.match(mid):
            out.append({"id": mid.strip(), "label": label.strip() or mid.strip(),
                        "tier": tier_for(mid + " " + label), "source": "live"})
        for c in v.values():
            walk_json_models(c, out)
    elif isinstance(v, (list, tuple)):
        for c in v:
            walk_json_models(c, out)


def parse_json_models(raw: str):
    try:
        data = json.loads(raw)
    except Exception:
        return []
    out = []
    walk_json_models(data, out)
    seen, uniq = set(), []
    for m in out:
        if m["id"] not in seen:
            seen.add(m["id"])
            uniq.append(m)
    return uniq


def parse_table_models(raw: str):
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s{2,}|\t+", line)
        mid = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else mid
        if MODEL_ID_RE.match(mid):
            out.append({"id": mid, "label": label, "tier": tier_for(mid + " " + label),
                        "source": "live"})
    seen, uniq = set(), []
    for m in out:
        if m["id"] not in seen:
            seen.add(m["id"])
            uniq.append(m)
    return uniq


def alias_models(aliases):
    out = []
    for a in aliases:
        t = a.get("tier", "")
        out.append({"id": a["id"], "label": a["label"],
                    "tier": t if t in ("fast", "balanced", "heavy") else tier_for(a["id"] + " " + a.get("label", "")),
                    "source": "alias"})
    return out


def discover(provider: dict) -> dict:
    cli = resolve(provider.get("executable_candidates", []))
    desktop = resolve_desktop(provider.get("desktop_candidates", []))
    disc = provider.get("discover", {}) or {}
    dtype = disc.get("type")

    if not cli:
        models = alias_models(disc.get("aliases", [])) if dtype == "aliases" else []
        return {"cli": None, "desktop": desktop, "models": models, "note": "CLI tidak terdeteksi"}

    try:
        if dtype == "command_json":
            code, out, err = capture(cli, disc["command"], disc.get("timeout", 30))
            models = parse_json_models(out) if code == 0 else []
            note = "Katalog live" if code == 0 and models else (err.strip() or f"exit {code}" if code else "Katalog kosong")
            return {"cli": cli, "desktop": desktop, "models": models, "note": note}

        if dtype == "command_table":
            code, out, err = capture(cli, disc["command"], disc.get("timeout", 20))
            models = parse_table_models(out) if code == 0 else []
            note = "Katalog live (teks)" if code == 0 and models else (err.strip() or f"exit {code}")
            return {"cli": cli, "desktop": desktop, "models": models, "note": note}

        if dtype == "aliases":
            return {"cli": cli, "desktop": desktop,
                    "models": alias_models(disc.get("aliases", [])),
                    "note": disc.get("note", "Alias")}
    except Exception as exc:
        return {"cli": cli, "desktop": desktop, "models": [], "note": str(exc)}

    return {"cli": cli, "desktop": desktop, "models": [], "note": "Discovery tidak didukung"}


# ------------------------------------------------------------- routing ----

HEAVY_RE = re.compile(
    r"\b(architecture|arsitektur|redesign|root[ -]?cause|memory leak|race condition|concurrency|security|keamanan|"
    r"audit|migration|migrasi|refactor[ -]?(besar|global|monorepo)|monorepo|from scratch|dari nol|"
    r"full[ -]?stack|debug kompleks|performance|optimasi dalam|scalab|distribut|scheduler|parser|intepreter|"
    r"implementasi besar|build sistem|buat sistem|app lengkap)\b", re.I)
SIMPLE_RE = re.compile(
    r"\b(rename|typo|format|lint|grep|lookup|list|daftar|syntax|regex sederhana|git status|git diff|"
    r"cek file|cari file|baca file|apa itu|jelaskan (apa|artinya)|translate|terjemah|ringkas|summar|"
    r"tambah komentar|perbaiki typo|ganti nama var|helo|halo|test ci)\b", re.I)
QUESTION_RE = re.compile(r"\?|\b(apa|kenapa|bagaimana|gimana|cara|explain|jelaskan|apa itu|berapa)\b", re.I)
WRITE_RE = re.compile(r"\b(buat|bikin|build|implement|implementasi|add|tambah|create|write|fix|perbaiki|refactor|ganti \w+ (cara|utuh))\b", re.I)
DESTRUCTIVE_RE = re.compile(
    r"\b(password|api[ _-]?key|secret|credential|token|delete|hapus|destroy|drop (table|database)|"
    r"deploy|ssh|registry|system32|\.env|db migrate|force push)\b", re.I)
BULLET_RE = re.compile(r"^\s*(?:[-*•]|\d+[.)])\s+\S", re.M)


def route_task(prompt: str, router_cfg: dict | None = None) -> dict:
    cfg = router_cfg or {}
    simple_th = int(cfg.get("simple_threshold", -1))
    heavy_th = int(cfg.get("heavy_threshold", 4))
    max_w = int(cfg.get("max_parallel_workers", 4))

    score, reasons = 0, []
    n = len(prompt)
    if n > 1400:
        score += 2; reasons.append("context panjang")
    elif n > 600:
        score += 1; reasons.append("context sedang")

    if HEAVY_RE.search(prompt):
        score += 4; reasons.append("keyword kompleks")
    if SIMPLE_RE.search(prompt):
        score -= 2; reasons.append("task sederhana")
    if QUESTION_RE.search(prompt) and not WRITE_RE.search(prompt):
        score -= 1; reasons.append("pertanyaan")
    writing = bool(WRITE_RE.search(prompt))
    if writing:
        score += 1; reasons.append("tulis kode")
    if n <= 120 and not writing and not HEAVY_RE.search(prompt):
        score -= 1; reasons.append("task pendek")

    steps = len(BULLET_RE.findall(prompt))
    newlines = prompt.count("\n")
    if steps >= 4 or newlines >= 8:
        score += 2; reasons.append(f"multi-step ({max(steps, newlines // 2)} langkah)")
    elif steps >= 2 or newlines >= 3:
        score += 1

    parallel = bool(re.search(
        r"\b(paralel|parallel|sekaligus|semua (file|modul|halaman|endpoint)|tiap file|batch|"
        r"beberapa worker|banyak file)\b", prompt, re.I))
    if parallel:
        reasons.append("bisa diparalelkan")

    risky = bool(DESTRUCTIVE_RE.search(prompt))
    if risky:
        score = max(score, heavy_th); reasons.append("safety floor (destructive)")

    if score <= simple_th:
        tier = "fast"
    elif score >= heavy_th:
        tier = "heavy"
    else:
        tier = "balanced"

    if parallel and tier == "heavy":
        delegation = f"planner → {max_w} worker paralel → reviewer"
    elif parallel and tier == "balanced":
        delegation = f"{max(2, max_w - 2)} worker paralel"
    elif risky:
        delegation = "langsung (1 model + review perubahan)"
    elif tier == "heavy":
        delegation = "langkah berat - kerjakan bertahap"
    else:
        delegation = "langsung (1 model)"

    return {"tier": tier, "delegation": delegation, "reasons": reasons or ["default"], "score": score, "risky": risky}


def choose_model(models: list[dict], tier: str) -> dict | None:
    if not models:
        return None
    exact = [m for m in models if m["tier"] == tier]
    if exact:
        return exact[0]
    if tier == "heavy":
        return next((m for m in models if m["tier"] == "balanced"), models[-1])
    if tier == "fast":
        return next((m for m in models if m["tier"] == "balanced"), models[0])
    return models[0]


def build_command(provider: dict, model_id: str, prompt: str) -> list[str]:
    exe = resolve(provider.get("executable_candidates", []))
    if not exe:
        raise RuntimeError("CLI tidak ditemukan")
    args = [a.replace("{model}", model_id).replace("{prompt}", prompt)
            for a in (provider.get("run", {}).get("command", []) or [])]
    return [exe, *args]


# ---------------------------------------------------------------- icon ----

def draw_mark(canvas: tk.Canvas, key: str, bg: str, fg: str, muted: str):
    canvas.delete("all")
    canvas.configure(bg=bg, highlightthickness=0)
    w = 2
    if key == "codex":
        for i in range(6):
            canvas.create_arc(4, 4, 28, 28, start=i * 60, extent=42, style="arc", width=w, outline=fg)
        canvas.create_oval(13, 13, 19, 19, outline=muted, width=1)
    elif key == "claude":
        canvas.create_line(16, 3, 16, 29, fill=fg, width=w)
        canvas.create_line(3, 16, 29, 16, fill=fg, width=w)
        canvas.create_line(7, 7, 25, 25, fill=fg, width=w)
        canvas.create_line(25, 7, 7, 25, fill=fg, width=w)
    elif key == "antigravity":
        canvas.create_line(5, 26, 16, 6, 27, 26, fill=fg, width=w, smooth=True)
        canvas.create_line(10, 19, 22, 19, fill=fg, width=w)
        canvas.create_arc(1, 1, 31, 31, start=200, extent=140, style="arc", outline=muted)
    elif key == "gemini":
        canvas.create_polygon(16, 3, 19, 13, 29, 16, 19, 19, 16, 29, 13, 19, 3, 16, 13, 13,
                              fill=fg, outline="")
    elif key == "opencode":
        canvas.create_text(16, 16, text="</>", fill=fg, font=("Consolas", 10, "bold"))
    else:
        canvas.create_oval(5, 5, 27, 27, outline=fg, width=w)
        canvas.create_text(16, 15, text="+", fill=fg, font=("Segoe UI", 12, "bold"))


# ----------------------------------------------------------------- ui ----

_BG = "#0E1014"
_PANEL = "#161A21"
_PANEL2 = "#1D222B"
_BORDER = "#262C37"
_TEXT = "#E7EAF0"
_MUTED = "#8B95A5"
_ACCENT = "#4C8DFF"
_FAST = "#3ECF8E"
_BAL = "#5A9CFF"
_HEAVY = "#FF9F5A"
_ERR = "#FF6B6B"
_CHIPBG = {"fast": "#12301F", "balanced": "#15233D", "heavy": "#33230F"}


class App(Tk):
    def __init__(self):
        super().__init__()
        self.title("ZwartFlow")
        self.geometry("1160x740")
        self.minsize(960, 620)
        self.configure(bg=_BG)

        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        self.cfg = merge_defaults(load_config())
        self.data: dict[str, dict] = {}
        self.current = "auto"
        self.selection: tuple[str, dict] | None = None

        self.setup_style()
        self.build()

        self.after(200, self.refresh)

    def setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TFrame", background=_BG)
        st.configure("Panel.TFrame", background=_PANEL)
        st.configure("Card.TFrame", background=_PANEL2)
        st.configure("TLabel", background=_BG, foreground=_TEXT, font=("Segoe UI", 10))
        st.configure("Panel.TLabel", background=_PANEL, foreground=_TEXT)
        st.configure("Card.TLabel", background=_PANEL2, foreground=_TEXT)
        st.configure("Muted.TLabel", background=_BG, foreground=_MUTED, font=("Segoe UI", 9))
        st.configure("PanelMuted.TLabel", background=_PANEL, foreground=_MUTED, font=("Segoe UI", 9))
        st.configure("CardMuted.TLabel", background=_PANEL2, foreground=_MUTED, font=("Segoe UI", 9))
        st.configure("Title.TLabel", background=_BG, foreground=_TEXT, font=("Segoe UI Semibold", 17))
        st.configure("PanelTitle.TLabel", background=_PANEL, foreground=_TEXT,
                     font=("Segoe UI Semibold", 11))
        st.configure("Big.TLabel", font=("Segoe UI Semibold", 13))
        st.configure("TButton", padding=(11, 6), background=_PANEL2, foreground=_TEXT, borderwidth=0)
        st.map("TButton", background=[("active", _BORDER)], foreground=[("active", _TEXT)])
        st.configure("Accent.TButton", padding=(13, 7), background=_ACCENT, foreground="#FFFFFF",
                     font=("Segoe UI Semibold", 10), borderwidth=0)
        st.map("Accent.TButton", background=[("active", "#3D79E7")])
        st.configure("TScrollbar", background=_PANEL, bordercolor=_BG, troughcolor=_BG)

    # ---------- build ----------

    def build(self):
        head = tk.Frame(self, bg=_PANEL)
        head.pack(fill="x")
        inner = tk.Frame(head, bg=_PANEL)
        inner.pack(fill="x", padx=18, pady=12)

        tk.Label(inner, text="ZwartFlow", bg=_PANEL, fg=_TEXT,
                 font=("Segoe UI Semibold", 16)).pack(side="left")
        v = tk.Label(inner, text="v2.0", bg=_PANEL2, fg=_MUTED, font=("Segoe UI", 8, "bold"),
                     padx=7, pady=2)
        v.pack(side="left", padx=10)
        tk.Label(inner, text="Auto model routing untuk Claude Code · Codex · Antigravity · Gemini · OpenCode",
                 bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9)).pack(side="left", padx=4)
        ttk.Button(inner, text="Settings", command=self.open_settings).pack(side="right")
        ttk.Button(inner, text="Refresh", command=self.refresh).pack(side="right", padx=7)

        body = tk.Frame(self, bg=_BG)
        body.pack(fill="both", expand=True, padx=14, pady=(10, 12))

        self.build_sidebar(body)
        self.build_main(body)

        footer = tk.Label(self, text="No shell=True  ·  no permission bypass  ·  no credential storage  ·  routing 100% lokal",
                          bg=_BG, fg=_MUTED, font=("Segoe UI", 8))
        footer.pack(side="bottom", anchor="w", padx=16, pady=(0, 6))

    def build_sidebar(self, parent):
        side = tk.Frame(parent, bg=_PANEL)
        side.pack(side="left", fill="y", padx=(0, 12))

        tk.Label(side, text="PROVIDERS", bg=_PANEL, fg=_MUTED,
                 font=("Segoe UI Semibold", 8)).pack(anchor="w", padx=12, pady=(12, 8))

        self.cards: dict[str, dict] = {}
        for key, p in self.cfg["providers"].items():
            card = tk.Frame(side, bg=_PANEL, padx=10, pady=8)
            card.pack(fill="x")

            icon = tk.Canvas(card, width=32, height=32, bg=_PANEL, bd=0, highlightthickness=0)
            icon.pack(side="left")
            draw_mark(icon, key, _PANEL, _MUTED if key == "custom" else _TEXT, _MUTED)

            info = tk.Frame(card, bg=_PANEL)
            info.pack(side="left", fill="x", expand=True, padx=9)
            tk.Label(info, text=p["name"], bg=_PANEL, fg=_TEXT,
                     font=("Segoe UI Semibold", 10)).pack(anchor="w")
            status = tk.Label(info, text="memeriksa…", bg=_PANEL, fg=_MUTED,
                              font=("Segoe UI", 8))
            status.pack(anchor="w")

            self.cards[key] = {"frame": card, "icon": icon, "status": status}

            def on_click(_e, k=key):
                self.select(k)
            for w in (card, icon, info):
                w.bind("<Button-1>", on_click)

        ttk.Separator(side).pack(fill="x", padx=10, pady=10)
        tk.Button(side, text="AUTO ROUTING", bg=_PANEL2, fg=_TEXT, bd=0, cursor="hand2",
                  activebackground=_BORDER, activeforeground=_TEXT,
                  font=("Segoe UI Semibold", 10), pady=6, command=lambda: self.select("auto")
                  ).pack(fill="x", padx=10)
        self.sidebar_status = tk.Label(side, text="", bg=_PANEL, fg=_MUTED,
                                       font=("Segoe UI", 8), justify="left", wraplength=200)
        self.sidebar_status.pack(anchor="w", padx=12, pady=10)

    def build_main(self, parent):
        main = tk.Frame(parent, bg=_BG)
        main.pack(side="left", fill="both", expand=True)

        # --- task router card ---
        top = tk.Frame(main, bg=_PANEL)
        top.pack(fill="x", pady=(0, 10))
        topc = tk.Frame(top, bg=_PANEL)
        topc.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(topc, text="TASK & AUTO ROUTER", bg=_PANEL, fg=_TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        tk.Label(topc, text="Router menilai kompleksitas, langkah, paralelisasi, dan risiko — 100% lokal.",
                 bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9)).pack(side="left", padx=10)

        self.task = Text(top, bg=_PANEL2, fg=_TEXT, bd=0, insertbackground=_TEXT,
                         highlightthickness=1, highlightbackground=_BORDER, highlightcolor=_ACCENT,
                         font=("Segoe UI", 11), padx=12, pady=10, height=5, wrap="word")
        self.task.pack(fill="x", padx=14, pady=(6, 8))
        self.task.tag_configure("risk", foreground=_ERR)

        row = tk.Frame(top, bg=_PANEL)
        row.pack(fill="x", padx=14, pady=(0, 12))
        self.chip_provider = tk.Label(row, text="PROVIDER —", bg=_PANEL2, fg=_MUTED,
                                      font=("Segoe UI", 9), padx=10, pady=5)
        self.chip_tier = tk.Label(row, text="TIER —", bg=_PANEL2, fg=_MUTED,
                                  font=("Segoe UI", 9), padx=10, pady=5)
        self.chip_deleg = tk.Label(row, text="DELEGASI —", bg=_PANEL2, fg=_MUTED,
                                   font=("Segoe UI", 9), padx=10, pady=5)
        for c in (self.chip_provider, self.chip_tier, self.chip_deleg):
            c.pack(side="left", padx=(0, 8))
        ttk.Button(row, text="Analyze & Route", style="Accent.TButton",
                   command=self.analyze).pack(side="right")
        ttk.Button(row, text="Run Selected", style="Accent.TButton",
                   command=self.run_selected).pack(side="right", padx=(0, 8))
        ttk.Button(row, text="Clear", command=lambda: self.task.delete("1.0", END)).pack(side="right", padx=(0, 8))

        self.reason_label = tk.Label(top, text="", bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9),
                                     justify="left", anchor="w", wraplength=760)
        self.reason_label.pack(anchor="w", padx=14, pady=(0, 10))

        # --- models card ---
        box = tk.Frame(main, bg=_PANEL)
        box.pack(fill="both", expand=True)
        head2 = tk.Frame(box, bg=_PANEL)
        head2.pack(fill="x", padx=14, pady=(12, 4))
        tk.Label(head2, text="AVAILABLE MODELS", bg=_PANEL, fg=_TEXT,
                 font=("Segoe UI Semibold", 11)).pack(side="left")
        self.models_hint = tk.Label(head2, text="", bg=_PANEL, fg=_MUTED, font=("Segoe UI", 9))
        self.models_hint.pack(side="left", padx=10)

        canvas = tk.Canvas(box, bg=_PANEL, bd=0, highlightthickness=0)
        scroll = ttk.Scrollbar(box, orient="vertical", command=canvas.yview)
        self.models_inner = tk.Frame(canvas, bg=_PANEL)
        self.models_inner.bind("<Configure>",
                               lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self.models_win = canvas.create_window((0, 0), window=self.models_inner, anchor="nw")
        canvas.bind("<Configure>", lambda e: canvas.itemconfigure(self.models_win, width=e.width))
        canvas.configure(yscrollcommand=scroll.set)
        canvas.pack(side="left", fill="both", expand=True, padx=(14, 0), pady=(0, 14))
        scroll.pack(side="right", fill="y", pady=(0, 14), padx=(0, 8))
        canvas.bind_all("<MouseWheel>", lambda e: canvas.yview_scroll(-1 * (e.delta // 120), "units"))

    # ---------- data ----------

    def refresh(self):
        for card in self.cards.values():
            card["status"].config(text="memeriksa…")
        self.sidebar_status.config(text="memindai CLI & desktop app…")

        def worker():
            data = {k: discover(p) for k, p in self.cfg["providers"].items()}
            self.data = data
            self.after(0, self.refresh_done)

        threading.Thread(target=worker, daemon=True).start()

    def refresh_done(self):
        cli_n = sum(1 for v in self.data.values() if v.get("cli"))
        app_n = sum(1 for v in self.data.values() if v.get("desktop"))
        self.sidebar_status.config(text=f"{cli_n} CLI terdeteksi\n{app_n} app desktop ditemukan")
        for key, card in self.cards.items():
            d = self.data.get(key, {})
            mark = "✓" if d.get("cli") else "—"
            card["status"].config(text=f"CLI {mark}   App {'✓' if d.get('desktop') else '—'}")
            draw_mark(card["icon"], key, _PANEL, _TEXT if d.get("cli") else _MUTED, _MUTED)
        self.show_models()

    def select(self, key):
        self.current = key
        for k, card in self.cards.items():
            bg = _PANEL2 if k == key else _PANEL
            card["frame"].config(bg=bg)
            for w in card["frame"].winfo_children():
                try:
                    w.config(bg=bg)
                except tk.TclError:
                    pass
            for child in card["frame"].winfo_children():
                for sub in child.winfo_children():
                    sub.config(bg=bg)
        self.show_models()

    def preferred_provider(self) -> str | None:
        pref = self.cfg.get("ui", {}).get("preferred_provider", "")
        if pref in self.data and self.data[pref].get("cli"):
            return pref
        for key in ("codex", "antigravity", "claude", "gemini", "opencode"):
            if self.data.get(key, {}).get("cli"):
                return key
        return next((k for k, v in self.data.items() if v.get("cli")), None)

    def show_models(self):
        for w in self.models_inner.winfo_children():
            w.destroy()

        key = self.current if self.current != "auto" else self.preferred_provider()
        if not key:
            self.models_hint.config(text="— tidak ada CLI yang terdeteksi")
            tk.Label(self.models_inner, text="Tidak ada CLI provider terdeteksi. Instal CLI (codex / claude / agy) atau isi path di Settings.",
                     bg=_PANEL, fg=_MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=10)
            return

        p = self.cfg["providers"][key]
        d = self.data.get(key, {})
        models = d.get("models", [])
        if self.current == "auto":
            key_title = f"Auto → {p['name']}"
        else:
            key_title = p["name"]

        parts = [p["vendor"], "CLI ✓" if d.get("cli") else "CLI —", "Desktop ✓" if d.get("desktop") else "Desktop —"]
        self.models_hint.config(text=f"{key_title}  •  {'  '.join(parts)}  •  {d.get('note', '')}")

        if not models:
            tk.Label(self.models_inner, text="Tidak ada daftar model yang tersedia untuk provider ini.",
                     bg=_PANEL, fg=_MUTED, font=("Segoe UI", 10)).pack(anchor="w", pady=8)
            if d.get("desktop"):
                ttk.Button(self.models_inner, text="Buka Desktop App",
                           command=lambda x=d["desktop"]: os.startfile(x)).pack(anchor="w", pady=6)
            return

        for m in models:
            self.model_row(self.models_inner, key, m)

    def model_row(self, parent, key: str, m: dict):
        tier = m["tier"]
        chip = {"fast": _FAST, "balanced": _BAL, "heavy": _HEAVY}.get(tier, _MUTED)
        card = tk.Frame(parent, bg=_PANEL2)
        card.pack(fill="x", pady=4, ipadx=2, ipady=2)

        left = tk.Frame(card, bg=_PANEL2)
        left.pack(side="left", fill="x", expand=True, padx=12, pady=9)
        tk.Label(left, text=m["label"], bg=_PANEL2, fg=_TEXT,
                 font=("Segoe UI Semibold", 10)).pack(anchor="w")
        tk.Label(left, text=m["id"], bg=_PANEL2, fg=_MUTED,
                 font=("Segoe UI", 8)).pack(anchor="w")

        tk.Label(card, text=tier.upper(), bg=_CHIPBG.get(tier, _PANEL), fg=chip,
                 font=("Segoe UI", 8, "bold"), padx=10, pady=4).pack(side="left", padx=6)
        if m.get("source") == "alias":
            tk.Label(card, text="alias", bg=_PANEL2, fg=_MUTED, font=("Segoe UI", 8)).pack(side="left")

        ttk.Button(card, text="Use", command=lambda: self.use_model(key, m)).pack(side="right", padx=10)

    def use_model(self, key: str, m: dict):
        self.selection = (key, m)
        self.current = key
        self.chip_provider.config(text=f"PROVIDER  {self.cfg['providers'][key]['name']}", **self._chip_colors())
        self.chip_tier.config(text=f"TIER  {m['tier'].upper()}", **self._chip_colors())
        self.chip_deleg.config(text=f"MODEL  {m['id']}", **self._chip_colors())
        self.reason_label.config(text=f"Model dipilih manual: {m['label']} ({m['id']}). Tekan Run Selected untuk menjalankan.")
        self.show_models()

    @staticmethod
    def _chip_colors():
        return {"bg": _PANEL2, "fg": _TEXT}

    # ---------- actions ----------

    def analyze(self):
        prompt = self.task.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("Task", "Tulis task dulu.")
            return

        r = route_task(prompt, self.cfg.get("router"))
        key = self.current if self.current != "auto" else self.preferred_provider()
        if not key:
            messagebox.showerror("Provider", "Tidak ada CLI provider yang terdeteksi.")
            return
        model = choose_model(self.data.get(key, {}).get("models", []), r["tier"])
        if not model:
            messagebox.showerror("Model", f"Tidak ada model tersedia di {self.cfg['providers'][key]['name']}.")
            return

        self.selection = (key, model)
        chip_fg = {"fast": _FAST, "balanced": _BAL, "heavy": _HEAVY}[r["tier"]]
        self.chip_provider.config(text=f"PROVIDER  {self.cfg['providers'][key]['name']}", **self._chip_colors())
        self.chip_tier.config(text=f"TIER  {r['tier'].upper()}", bg=_CHIPBG[r["tier"]], fg=chip_fg)
        self.chip_deleg.config(text=f"DELEGASI  {r['delegation']}", **self._chip_colors())
        why = " · ".join(r["reasons"])
        self.reason_label.config(
            text=f"Score {r['score']:+d} → {r['tier'].upper()}  ·  {why}  ·  Model: {model['label']} ({model['id']})")

    def run_selected(self):
        prompt = self.task.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("Task", "Tulis task dulu.")
            return
        if not self.selection:
            self.analyze()
            if not self.selection:
                return
        key, model = self.selection
        p = self.cfg["providers"][key]
        try:
            cmd = build_command(p, model["id"], prompt)
        except Exception as exc:
            messagebox.showerror("Run", str(exc))
            return

        if self.cfg.get("ui", {}).get("confirm_before_run", True):
            detail = f"Provider: {p['name']}\nModel: {model['label']} ({model['id']})\n\n" \
                     + subprocess.list2cmdline(cmd) + "\n\nJalankan di console baru?"
            if not messagebox.askyesno("Run agent", detail):
                return

        try:
            flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
            subprocess.Popen(cmd, shell=False, creationflags=flags)
        except Exception as exc:
            messagebox.showerror("Run gagal", str(exc))

    def open_settings(self):
        Settings(self)


class Settings(Toplevel):
    def __init__(self, parent: App):
        super().__init__(parent)
        self.parent = parent
        self.title("ZwartFlow · Settings")
        self.geometry("840x660")
        self.configure(bg=_BG)
        self.minsize(700, 500)
        try:
            import ctypes
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except Exception:
            pass

        tk.Label(self, text="Provider & Model Discovery", bg=_BG, fg=_TEXT,
                 font=("Segoe UI Semibold", 14)).pack(anchor="w", padx=18, pady=(16, 4))
        tk.Label(self, text="Path CLI, discovery command, alias model, dan argumen run semua provider ada di sini.",
                 bg=_BG, fg=_MUTED, font=("Segoe UI", 9)).pack(anchor="w", padx=18)

        self.editor = Text(self, font=("Consolas", 10), bg=_PANEL2, fg=_TEXT,
                           insertbackground=_TEXT, bd=0, highlightthickness=1,
                           highlightbackground=_BORDER, highlightcolor=_ACCENT,
                           padx=12, pady=12)
        self.editor.pack(fill="both", expand=True, padx=18, pady=12)
        self.editor.insert("1.0", json.dumps(parent.cfg, indent=2, ensure_ascii=False))

        row = tk.Frame(self, bg=_BG)
        row.pack(fill="x", padx=18, pady=(0, 16))
        ttk.Button(row, text="Validate", command=self.validate).pack(side="left")
        ttk.Button(row, text="Save & Refresh", style="Accent.TButton", command=self.save).pack(side="left", padx=8)
        ttk.Button(row, text="Reset default", command=self.reset).pack(side="left")
        ttk.Button(row, text="Close", command=self.destroy).pack(side="right")

    def validate(self):
        try:
            merge_defaults(json.loads(self.editor.get("1.0", END)))
            messagebox.showinfo("Valid", "JSON valid.")
        except Exception as exc:
            messagebox.showerror("Invalid", str(exc))

    def save(self):
        try:
            data = merge_defaults(json.loads(self.editor.get("1.0", END)))
            save_config(data)
            self.parent.cfg = data
            self.parent.data = {}
            self.parent.selection = None
            self.parent.current = "auto"
            self.parent.refresh()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Save", str(exc))

    def reset(self):
        self.editor.delete("1.0", END)
        self.editor.insert("1.0", json.dumps(json.loads(json.dumps(DEFAULT_CONFIG)), indent=2, ensure_ascii=False))


def main():
    # self-healing: jika exe dijalankan tanpa config.json, tulis default
    if not CONFIG_PATH.exists():
        save_config(json.loads(json.dumps(DEFAULT_CONFIG)))
    App().mainloop()


if __name__ == "__main__":
    main()
