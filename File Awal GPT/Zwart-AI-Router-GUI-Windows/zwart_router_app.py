
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import threading
from pathlib import Path
from tkinter import Tk, Toplevel, StringVar, BooleanVar, Text, END, messagebox
from tkinter import ttk


APP_DIR = Path(__file__).resolve().parent
CONFIG = APP_DIR / "config.json"

BG = "#F5F5F7"
PANEL = "#FFFFFF"
TEXT = "#171717"
MUTED = "#777777"
BORDER = "#E5E5EA"
ACCENT = "#111111"
SUCCESS = "#2E7D32"
WARN = "#996000"
ERROR = "#B3261E"


def load_config():
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def save_config(data):
    tmp = CONFIG.with_suffix(".tmp")
    tmp.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    tmp.replace(CONFIG)


def expand(v):
    return os.path.expandvars(os.path.expanduser(v))


def resolve(candidates):
    for raw in candidates:
        if not raw:
            continue
        v = expand(raw)
        found = shutil.which(v)
        if found:
            return found
        p = Path(v)
        if p.exists() and p.is_file():
            return str(p)
    return None


def resolve_desktop(candidates):
    for raw in candidates:
        if not raw:
            continue
        p = Path(expand(raw))
        if p.exists() and p.is_file():
            return str(p)
    return None


def capture(exe, args, timeout=40):
    p = subprocess.run(
        [exe, *args],
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=timeout,
        shell=False,
    )
    return p.returncode, p.stdout, p.stderr


def tier_for(model_id, label=""):
    s = f"{model_id} {label}".lower()
    if re.search(r"\b(mini|nano|haiku|flash[- _]?low)\b", s):
        return "fast"
    if re.search(r"\b(opus|pro|ultra|flagship|xhigh)\b", s):
        return "heavy"
    if re.search(r"\b(sonnet|flash[- _]?(medium|high)|medium|balanced)\b", s):
        return "balanced"
    return "balanced"


def dedupe(items):
    seen = set()
    out = []
    for x in items:
        if x.get("id") and x["id"] not in seen:
            seen.add(x["id"])
            out.append(x)
    return out


def parse_agy(raw):
    out = []
    for line in raw.splitlines():
        line = line.strip()
        if not line:
            continue
        parts = re.split(r"\s{2,}|\t+", line)
        mid = parts[0].strip()
        label = parts[1].strip() if len(parts) > 1 else mid
        if re.match(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]*$", mid):
            out.append({"id": mid, "label": label, "tier": tier_for(mid, label), "source": "live"})
    return dedupe(out)


def walk_models(v, out):
    if isinstance(v, dict):
        mid = next((v[k] for k in ("slug", "id", "model", "model_id")
                    if isinstance(v.get(k), str) and v[k].strip()), None)
        label = next((v[k] for k in ("display_name", "name", "label", "title")
                      if isinstance(v.get(k), str) and v[k].strip()), "")
        if mid and re.match(r"^[A-Za-z0-9][A-Za-z0-9._:/+-]*$", mid):
            out.append({"id": mid.strip(), "label": label.strip() or mid.strip(),
                        "tier": tier_for(mid, label), "source": "live"})
        for child in v.values():
            walk_models(child, out)
    elif isinstance(v, list):
        for child in v:
            walk_models(child, out)


def parse_codex(raw):
    try:
        data = json.loads(raw)
    except Exception:
        return []
    out = []
    walk_models(data, out)
    return dedupe(out)


def claude_aliases():
    return [
        {"id": "haiku", "label": "Haiku · alias", "tier": "fast", "source": "alias"},
        {"id": "sonnet", "label": "Sonnet · alias", "tier": "balanced", "source": "alias"},
        {"id": "opus", "label": "Opus · alias", "tier": "heavy", "source": "alias"},
    ]


def discover(key, provider):
    cli = resolve(provider.get("executable_candidates", []))
    desktop = resolve_desktop(provider.get("desktop_candidates", []))
    dtype = provider.get("discover", {}).get("type")

    if not cli:
        if dtype == "claude_aliases":
            return {"cli": None, "desktop": desktop, "models": claude_aliases(),
                    "note": "Claude aliases • CLI not detected"}
        return {"cli": None, "desktop": desktop, "models": [], "note": "CLI not detected"}

    try:
        if dtype == "agy_models":
            code, out, err = capture(cli, provider["discover"]["command"], 25)
            return {"cli": cli, "desktop": desktop,
                    "models": parse_agy(out) if code == 0 else [],
                    "note": "Live discovery: agy models" if code == 0 else (err.strip() or f"Exit {code}")}

        if dtype == "codex_debug_models":
            code, out, err = capture(cli, provider["discover"]["command"], 45)
            return {"cli": cli, "desktop": desktop,
                    "models": parse_codex(out) if code == 0 else [],
                    "note": "Live catalog: codex debug models" if code == 0 else (err.strip() or f"Exit {code}")}

        if dtype == "claude_aliases":
            return {"cli": cli, "desktop": desktop, "models": claude_aliases(),
                    "note": "CLI aliases • no official non-interactive model-list command"}

        if dtype == "custom_command":
            code, out, err = capture(cli, provider["discover"]["command"], 20)
            models = parse_codex(out) if code == 0 else []
            if not models and code == 0:
                for line in out.splitlines():
                    value = line.strip()
                    if value:
                        models.append({"id": value.split()[0], "label": value,
                                       "tier": tier_for(value), "source": "custom"})
            return {"cli": cli, "desktop": desktop, "models": dedupe(models),
                    "note": "Custom discovery" if code == 0 else (err.strip() or f"Exit {code}")}

    except Exception as exc:
        return {"cli": cli, "desktop": desktop, "models": [], "note": str(exc)}

    return {"cli": cli, "desktop": desktop, "models": [], "note": "Unsupported discovery"}


def task_tier(prompt):
    s = prompt.lower()
    score = 0
    why = []

    if len(prompt) > 1400:
        score += 2; why.append("context panjang")
    elif len(prompt) > 600:
        score += 1; why.append("context sedang")

    if re.search(r"\b(architecture|arsitektur|redesign|root cause|memory leak|concurrency|security|production|migration|refactor|monorepo|from scratch|dari nol|full stack|repo-wide)\b", s):
        score += 4; why.append("task kompleks")

    if re.search(r"\b(rename|typo|format|grep|lookup|list|syntax|regex|git status|git diff|cek file|cari file|apa itu|jelaskan)\b", s):
        score -= 2; why.append("task sederhana")

    if prompt.count("\n") >= 8:
        score += 1; why.append("multi-step")

    if re.search(r"\b(password|api[_ -]?key|secret|credential|token|delete|hapus|destroy|format disk|deploy|ssh|registry|system32|\.env)\b", s):
        score = max(score, 4); why.append("safety floor")

    if score <= -1:
        return "fast", why
    if score >= 4:
        return "heavy", why
    return "balanced", why


def choose_model(models, tier):
    exact = [m for m in models if m["tier"] == tier]
    if exact:
        return exact[0]
    if tier == "heavy":
        return next((m for m in models if m["tier"] == "balanced"), models[0] if models else None)
    if tier == "fast":
        return next((m for m in models if m["tier"] == "balanced"), models[0] if models else None)
    return models[0] if models else None


def command_for(provider, model, prompt):
    exe = resolve(provider.get("executable_candidates", []))
    if not exe:
        raise RuntimeError("CLI tidak ditemukan.")
    args = [x.replace("{model}", model).replace("{prompt}", prompt)
            for x in provider.get("run", {}).get("command", [])]
    return [exe, *args]


def draw_mark(canvas, key):
    canvas.delete("all")
    canvas.configure(bg=PANEL, highlightthickness=0)
    if key == "codex":
        # abstract OpenAI/Codex-inspired interlock
        for i in range(6):
            a = i * 60
            canvas.create_arc(5, 5, 27, 27, start=a, extent=45, style="arc", width=2, outline=TEXT)
    elif key == "claude":
        canvas.create_line(16, 3, 16, 29, fill=TEXT, width=2)
        canvas.create_line(3, 16, 29, 16, fill=TEXT, width=2)
        canvas.create_line(7, 7, 25, 25, fill=TEXT, width=2)
        canvas.create_line(25, 7, 7, 25, fill=TEXT, width=2)
    elif key == "antigravity":
        canvas.create_line(6, 25, 16, 5, 26, 25, fill=TEXT, width=2, smooth=True)
        canvas.create_line(10, 18, 22, 18, fill=TEXT, width=2)
        canvas.create_oval(3, 12, 7, 16, outline=MUTED, width=1)
        canvas.create_arc(2, 2, 30, 30, start=205, extent=130, style="arc", outline=MUTED)
    else:
        canvas.create_oval(6, 6, 26, 26, outline=TEXT, width=2)
        canvas.create_text(16, 16, text="+", fill=TEXT, font=("Segoe UI", 13, "bold"))


class App(Tk):
    def __init__(self):
        super().__init__()
        self.title("Zwart AI Router")
        self.geometry("1180x760")
        self.minsize(1000, 650)
        self.configure(bg=BG)

        self.cfg = load_config()
        self.current = "auto"
        self.data = {}
        self.selected = None

        self.setup_style()
        self.build()
        self.after(150, self.refresh)

    def setup_style(self):
        st = ttk.Style(self)
        try:
            st.theme_use("clam")
        except Exception:
            pass
        st.configure("TFrame", background=BG)
        st.configure("Panel.TFrame", background=PANEL)
        st.configure("TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 10))
        st.configure("Panel.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 10))
        st.configure("Muted.TLabel", background=BG, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("PanelMuted.TLabel", background=PANEL, foreground=MUTED, font=("Segoe UI", 9))
        st.configure("Title.TLabel", background=BG, foreground=TEXT, font=("Segoe UI", 18, "bold"))
        st.configure("PanelTitle.TLabel", background=PANEL, foreground=TEXT, font=("Segoe UI", 11, "bold"))
        st.configure("TButton", font=("Segoe UI", 9), padding=(12, 7))
        st.configure("Primary.TButton", background=ACCENT, foreground="#FFFFFF",
                     font=("Segoe UI", 9, "bold"), padding=(14, 8))
        st.map("Primary.TButton", background=[("active", "#2A2A2A")])

    def build(self):
        top = ttk.Frame(self, padding=(22, 17, 22, 10))
        top.pack(fill="x")
        ttk.Label(top, text="Zwart AI Router", style="Title.TLabel").pack(side="left")
        ttk.Label(top, text="Clean Windows control center for AI agents",
                  style="Muted.TLabel").pack(side="left", padx=14)
        ttk.Button(top, text="Settings", command=self.settings).pack(side="right")
        ttk.Button(top, text="Refresh", command=self.refresh).pack(side="right", padx=7)

        body = ttk.Frame(self, padding=(18, 4, 18, 18))
        body.pack(fill="both", expand=True)

        sidebar = ttk.Frame(body, style="Panel.TFrame", padding=12)
        sidebar.pack(side="left", fill="y", padx=(0, 12))
        ttk.Label(sidebar, text="PROVIDERS", style="Panel.TLabel",
                  font=("Segoe UI", 8, "bold")).pack(anchor="w", pady=(3, 10))

        self.cards = {}
        for key in self.cfg["providers"]:
            self.provider_card(sidebar, key)

        ttk.Separator(sidebar).pack(fill="x", pady=12)
        ttk.Button(sidebar, text="Auto select", command=lambda: self.select("auto")).pack(fill="x")
        self.sidebar_status = StringVar(value="Detecting…")
        ttk.Label(sidebar, textvariable=self.sidebar_status, style="PanelMuted.TLabel",
                  wraplength=185).pack(anchor="w", pady=(12, 3))

        main = ttk.Frame(body)
        main.pack(side="left", fill="both", expand=True)

        head = ttk.Frame(main, style="Panel.TFrame", padding=14)
        head.pack(fill="x", pady=(0, 12))
        self.provider_title = StringVar(value="Auto provider")
        ttk.Label(head, textvariable=self.provider_title, style="PanelTitle.TLabel").pack(anchor="w")
        self.provider_meta = StringVar(value="Looking for installed agents…")
        ttk.Label(head, textvariable=self.provider_meta, style="PanelMuted.TLabel").pack(anchor="w", pady=(2, 0))

        router = ttk.Frame(main, style="Panel.TFrame", padding=14)
        router.pack(fill="x", pady=(0, 12))
        ttk.Label(router, text="AUTO ROUTER", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(router, text="Analyzes the task locally and maps it to a model tier.",
                  style="PanelMuted.TLabel").pack(anchor="w", pady=(2, 9))

        route_row = ttk.Frame(router, style="Panel.TFrame")
        route_row.pack(fill="x")
        self.route_provider = StringVar(value="AUTO")
        self.route_tier = StringVar(value="AUTO")
        self.route_model = StringVar(value="—")
        for label, var in (("PROVIDER", self.route_provider), ("TIER", self.route_tier), ("MODEL", self.route_model)):
            box = ttk.Frame(route_row, style="Panel.TFrame")
            box.pack(side="left", fill="x", expand=True, padx=(0, 15))
            ttk.Label(box, text=label, style="PanelMuted.TLabel").pack(anchor="w")
            ttk.Label(box, textvariable=var, background=PANEL, foreground=TEXT,
                      font=("Segoe UI", 11, "bold")).pack(anchor="w", pady=(2, 0))
        ttk.Button(router, text="Analyze", style="Primary.TButton",
                   command=self.analyze).pack(anchor="e", pady=(11, 0))

        work = ttk.Frame(main)
        work.pack(fill="both", expand=True)

        models_panel = ttk.Frame(work, style="Panel.TFrame", padding=14)
        models_panel.pack(side="left", fill="both", expand=True, padx=(0, 12))
        ttk.Label(models_panel, text="AVAILABLE MODELS", style="PanelTitle.TLabel").pack(anchor="w")
        self.models_hint = StringVar(value="")
        ttk.Label(models_panel, textvariable=self.models_hint, style="PanelMuted.TLabel").pack(anchor="w", pady=(2, 10))
        self.models_box = ttk.Frame(models_panel, style="Panel.TFrame")
        self.models_box.pack(fill="both", expand=True)

        task_panel = ttk.Frame(work, style="Panel.TFrame", padding=14)
        task_panel.pack(side="right", fill="both", expand=True)
        ttk.Label(task_panel, text="TASK", style="PanelTitle.TLabel").pack(anchor="w")
        ttk.Label(task_panel, text="Write one task. The router will recommend a model.",
                  style="PanelMuted.TLabel").pack(anchor="w", pady=(2, 8))
        self.task = Text(task_panel, bg="#FFFFFF", fg=TEXT, bd=0, highlightthickness=1,
                         highlightbackground=BORDER, highlightcolor=TEXT,
                         font=("Segoe UI", 11), padx=13, pady=11, wrap="word")
        self.task.pack(fill="both", expand=True)
        btnrow = ttk.Frame(task_panel, style="Panel.TFrame")
        btnrow.pack(fill="x", pady=(10, 0))
        ttk.Button(btnrow, text="Clear", command=lambda: self.task.delete("1.0", END)).pack(side="left")
        ttk.Button(btnrow, text="Run selected", style="Primary.TButton",
                   command=self.run_selected).pack(side="right")

        footer = ttk.Frame(main, padding=(0, 9, 0, 0))
        footer.pack(fill="x")
        ttk.Label(footer, text="No shell=True • no permission bypass • no credential storage",
                  style="Muted.TLabel").pack(side="left")

    def provider_card(self, parent, key):
        f = ttk.Frame(parent, style="Panel.TFrame", padding=8)
        f.pack(fill="x", pady=3)
        icon = tk_canvas = __import__("tkinter").Canvas(f, width=32, height=32, bg=PANEL, bd=0, highlightthickness=0)
        icon.pack(side="left")
        draw_mark(icon, key)

        info = ttk.Frame(f, style="Panel.TFrame")
        info.pack(side="left", fill="x", expand=True, padx=8)
        name = ttk.Label(info, text=self.cfg["providers"][key]["name"], style="Panel.TLabel")
        name.pack(anchor="w")
        status = ttk.Label(info, text="Detecting…", style="PanelMuted.TLabel")
        status.pack(anchor="w")
        self.cards[key] = {"frame": f, "status": status}

        def choose(_=None):
            self.select(key)
        for w in (f, icon, info, name, status):
            w.bind("<Button-1>", choose)

    def select(self, key):
        self.current = key
        for k, c in self.cards.items():
            bg = "#F0F0F3" if k == key else PANEL
            c["frame"].configure(style="Panel.TFrame")
            for child in c["frame"].winfo_children():
                if isinstance(child, __import__("tkinter").Canvas):
                    child.configure(bg=bg)
        self.show_models()

    def refresh(self):
        self.sidebar_status.set("Refreshing live catalogs…")
        def worker():
            data = {}
            for key, p in self.cfg["providers"].items():
                data[key] = discover(key, p)
            self.data = data
            self.after(0, self.refresh_done)
        threading.Thread(target=worker, daemon=True).start()

    def refresh_done(self):
        cli_count = sum(1 for v in self.data.values() if v.get("cli"))
        desktop_count = sum(1 for v in self.data.values() if v.get("desktop"))
        self.sidebar_status.set(f"{cli_count} CLI detected\n{desktop_count} desktop app path detected")
        for key, card in self.cards.items():
            d = self.data.get(key, {})
            cli = "CLI ✓" if d.get("cli") else "CLI —"
            desk = "App ✓" if d.get("desktop") else "App —"
            card["status"].configure(text=f"{cli}   {desk}")
        self.show_models()

    def show_models(self):
        for w in self.models_box.winfo_children():
            w.destroy()

        key = self.current
        if key == "auto":
            key = self.preferred_provider()
            self.provider_title.set("Auto provider")
        else:
            self.provider_title.set(self.cfg["providers"][key]["name"])

        if not key:
            self.provider_meta.set("No provider detected.")
            self.models_hint.set("")
            return

        d = self.data.get(key, {})
        p = self.cfg["providers"][key]
        models = d.get("models", [])
        cli = d.get("cli")
        desktop = d.get("desktop")

        parts = []
        if cli: parts.append("CLI ✓")
        if desktop: parts.append("Desktop ✓")
        self.provider_meta.set(f"{p['provider']}   •   " + ("   ".join(parts) if parts else "Not installed"))
        self.models_hint.set(f"{len(models)} model(s)   •   {d.get('note', '')}")

        if not models:
            ttk.Label(self.models_box, text="No live model list available.", style="PanelMuted.TLabel").pack(anchor="w", pady=8)
            if key == "claude":
                ttk.Label(
                    self.models_box,
                    text="Claude Code has --model and interactive /model, but Anthropic does not currently expose an official non-interactive model-list command. This app intentionally shows aliases instead of inventing an account-specific list.",
                    style="PanelMuted.TLabel", wraplength=520
                ).pack(anchor="w", pady=4)
            if desktop:
                ttk.Button(self.models_box, text="Open Desktop App",
                           command=lambda x=desktop: os.startfile(x)).pack(anchor="w", pady=10)
            return

        for m in models:
            card = ttk.Frame(self.models_box, style="Panel.TFrame", padding=(10, 8))
            card.pack(fill="x", pady=4)
            left = ttk.Frame(card, style="Panel.TFrame")
            left.pack(side="left", fill="x", expand=True)
            ttk.Label(left, text=m["label"], style="Panel.TLabel",
                      font=("Segoe UI", 10, "bold")).pack(anchor="w")
            ttk.Label(left, text=m["id"], style="PanelMuted.TLabel").pack(anchor="w", pady=(1, 0))
            tag = ttk.Label(card, text=m["tier"].upper(), background="#EFEFF2",
                            foreground=TEXT, font=("Segoe UI", 8, "bold"), padding=(8, 4))
            tag.pack(side="left", padx=7)
            ttk.Button(card, text="Use", command=lambda kk=key, mm=m: self.choose_model(kk, mm)).pack(side="right")

    def choose_model(self, key, model):
        self.selected = (key, model)
        self.current = key
        self.route_provider.set(self.cfg["providers"][key]["name"])
        self.route_tier.set(model["tier"].upper())
        self.route_model.set(model["id"])
        self.show_models()

    def preferred_provider(self):
        pref = self.cfg.get("ui", {}).get("preferred_provider", "")
        if pref in self.data and self.data[pref].get("cli"):
            return pref
        for key in ("codex", "antigravity", "claude", "custom"):
            if self.data.get(key, {}).get("cli"):
                return key
        return None

    def analyze(self):
        prompt = self.task.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("Task", "Masukkan task dulu.")
            return

        tier, why = task_tier(prompt)
        key = self.current if self.current != "auto" else self.preferred_provider()
        if not key:
            messagebox.showerror("Provider", "Tidak ada CLI provider yang terdeteksi.")
            return

        model = choose_model(self.data.get(key, {}).get("models", []), tier)
        if not model:
            messagebox.showerror("Model", f"Tidak ada model yang terdeteksi di {self.cfg['providers'][key]['name']}.")
            return

        self.selected = (key, model)
        self.route_provider.set(self.cfg["providers"][key]["name"])
        self.route_tier.set(f"{tier.upper()}  ·  " + (", ".join(why) if why else "default"))
        self.route_model.set(model["id"])

    def run_selected(self):
        prompt = self.task.get("1.0", END).strip()
        if not prompt:
            messagebox.showwarning("Task", "Masukkan task dulu.")
            return
        if not self.selected:
            self.analyze()
        if not self.selected:
            return

        key, model = self.selected
        p = self.cfg["providers"][key]
        try:
            cmd = command_for(p, model["id"], prompt)
        except Exception as exc:
            messagebox.showerror("Run", str(exc))
            return

        if self.cfg["ui"].get("confirm_before_run", True):
            ok = messagebox.askyesno(
                "Run agent",
                f"Provider: {p['name']}\nModel: {model['id']}\nTier: {model['tier']}\n\n"
                + subprocess.list2cmdline(cmd)
                + "\n\nOpen in a new console?"
            )
            if not ok:
                return

        try:
            flags = subprocess.CREATE_NEW_CONSOLE if os.name == "nt" else 0
            subprocess.Popen(cmd, shell=False, creationflags=flags)
        except Exception as exc:
            messagebox.showerror("Run failed", str(exc))

    def settings(self):
        Settings(self)

class Settings(Toplevel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.title("Zwart AI Router · Settings")
        self.geometry("820x650")
        self.configure(bg=BG)
        ttk.Label(self, text="Provider & model discovery", style="Title.TLabel").pack(anchor="w", padx=18, pady=(18, 6))
        ttk.Label(self, text="Edit provider commands, paths and custom adapters here.",
                  style="Muted.TLabel").pack(anchor="w", padx=18)
        self.editor = Text(self, font=("Consolas", 10), bg="#FFFFFF", fg=TEXT, bd=0,
                           highlightthickness=1, highlightbackground=BORDER, padx=10, pady=10)
        self.editor.pack(fill="both", expand=True, padx=18, pady=12)
        self.editor.insert("1.0", json.dumps(parent.cfg, indent=2, ensure_ascii=False))
        row = ttk.Frame(self, padding=(18, 0, 18, 18))
        row.pack(fill="x")
        ttk.Button(row, text="Validate", command=self.validate).pack(side="left")
        ttk.Button(row, text="Save", style="Primary.TButton", command=self.save).pack(side="left", padx=7)
        ttk.Button(row, text="Close", command=self.destroy).pack(side="right")

    def validate(self):
        try:
            json.loads(self.editor.get("1.0", END))
            messagebox.showinfo("Valid", "JSON valid.")
        except Exception as exc:
            messagebox.showerror("Invalid", str(exc))

    def save(self):
        try:
            data = json.loads(self.editor.get("1.0", END))
            save_config(data)
            self.parent.cfg = data
            self.parent.refresh()
            self.destroy()
        except Exception as exc:
            messagebox.showerror("Save", str(exc))


if __name__ == "__main__":
    App().mainloop()
