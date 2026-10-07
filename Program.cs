// ZwartFlow v2.1 - auto model routing untuk AI agent CLI di Windows.
// Framework: C# WinForms pada .NET Framework 4.8 (bawaan Windows, tanpa runtime tambahan).
// Build: csc.exe bawaan Windows - tanpa Python, tanpa PyInstaller.

using System;
using System.Collections.Generic;
using System.Diagnostics;
using System.Drawing;
using System.IO;
using System.Linq;
using System.Runtime.InteropServices;
using System.Text;
using System.Text.RegularExpressions;
using System.Threading.Tasks;
using System.Web.Script.Serialization;
using System.Windows.Forms;

namespace ZwartFlow
{
    static class Program
    {
        [STAThread]
        static void Main()
        {
            try { Marshal.ThrowExceptionForHR(UnsafeNative.SetProcessDpiAwareness(1)); } catch { }
            Application.EnableVisualStyles();
            Application.SetCompatibleTextRenderingDefault(false);
            Application.ThreadException += (s, e) =>
                MessageBox.Show("Terjadi error: " + e.Exception.Message, "ZwartFlow",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            try
            {
                Application.Run(new MainForm());
            }
            catch (Exception ex)
            {
                MessageBox.Show("Fatal: " + ex.Message, "ZwartFlow",
                    MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }
    }

    internal static class UnsafeNative
    {
        [DllImport("shcore.dll", EntryPoint = "SetProcessDpiAwareness")]
        public static extern int SetProcessDpiAwareness(int value);
    }

    public class ModelInfo
    {
        public string Id;
        public string Label;
        public string Tier;
        public string Source;
    }

    public class ProviderState
    {
        public string CliPath;
        public string DesktopPath;
        public string LaunchTarget;
        public string Note = "";
        public bool Done;
        public List<ModelInfo> Models = new List<ModelInfo>();
    }

    public class ProviderEntry
    {
        public string Key;
        public string Name;
        public string Vendor;
        public string Kind; // "cli" atau "desktop"
        public string CliKey; // utk entri desktop: key entri CLI padanannya
    }

    public class RoutingResult
    {
        public string Tier;
        public string Delegation;
        public List<string> Reasons = new List<string>();
        public int Score;
        public bool Risky;
    }

    public class MainForm : Form
    {
        // ------------------------------------------------------------ warna
        static readonly Color BG = Html("#0E1014");
        static readonly Color PANEL = Html("#161A21");
        static readonly Color PANEL2 = Html("#1D222B");
        static readonly Color BORDER = Html("#262C37");
        static readonly Color TEXT = Html("#E7EAF0");
        static readonly Color MUTED = Html("#8B95A5");
        static readonly Color ACCENT = Html("#4C8DFF");
        static readonly Color FAST = Html("#3ECF8E");
        static readonly Color BAL = Html("#5A9CFF");
        static readonly Color HEAVY = Html("#FF9F5A");
        static readonly Color CHIP_FAST_BG = Html("#12301F");
        static readonly Color CHIP_BAL_BG = Html("#15233D");
        static readonly Color CHIP_HEAVY_BG = Html("#33230F");

        static Color Html(string hex)
        {
            return Color.FromArgb(
                Convert.ToInt32(hex.Substring(1, 2), 16),
                Convert.ToInt32(hex.Substring(3, 2), 16),
                Convert.ToInt32(hex.Substring(5, 2), 16));
        }

        // ------------------------------------------------------------ state
        readonly JavaScriptSerializer _json = new JavaScriptSerializer { MaxJsonLength = int.MaxValue };
        Dictionary<string, object> _cfg = new Dictionary<string, object>();
        Dictionary<string, object> _defaultCfg;
        readonly Dictionary<string, ProviderEntry> _entries = new Dictionary<string, ProviderEntry>();
        readonly Dictionary<string, ProviderState> _states = new Dictionary<string, ProviderState>();
        readonly Dictionary<string, Image> _logos = new Dictionary<string, Image>();
        readonly Dictionary<string, Panel> _cardPanels = new Dictionary<string, Panel>();
        readonly Dictionary<string, Label> _cardStatus = new Dictionary<string, Label>();
        readonly Dictionary<string, Panel> _cardStrips = new Dictionary<string, Panel>();
        string _selectedKey = "auto";
        ModelInfo _selectedModel;
        string _selectedProviderKey;
        bool _settingsOpen;

        // ------------------------------------------------------------ UI
        TableLayoutPanel _cardsTlp;
        TextBox _taskBox;
        Label _resultTier;
        Label _resultMain;
        Label _resultSub;
        Button _runBtn;
        Panel _resultCard;
        Label _modelsHint;
        TableLayoutPanel _modelsTlp;
        Label _statusLabel;

        public MainForm()
        {
            _defaultCfg = DefaultConfig();

            Text = "ZwartFlow";
            StartPosition = FormStartPosition.CenterScreen;
            ClientSize = new Size(1120, 720);
            MinimumSize = new Size(900, 600);
            BackColor = BG;
            Font = new Font("Segoe UI", 9.5F);
            AutoScaleMode = AutoScaleMode.Font;
            DoubleBuffered = true;

            LoadConfig();
            LoadLogos();
            BuildEntries();
            BuildUi();
            RefreshCards();
            SelectEntry("auto");
            DiscoverAll();
        }

        // =========================================================== config

        public static Dictionary<string, object> DefaultConfig()
        {
            return JMap(
                "version", 6,
                "ui", JMap("preferred_provider", "codex-cli", "confirm_before_run", true),
                "router", JMap("simple_threshold", -1, "heavy_threshold", 4, "max_parallel_workers", 4),
                "providers", JMap(
                    "codex-cli", JMap(
                        "name", "Codex CLI", "vendor", "OpenAI", "kind", "cli",
                        "executable_candidates", JList(
                            "codex.exe", "codex.cmd", "codex",
                            "%LOCALAPPDATA%\\OpenAI\\Codex\\bin\\*\\codex.exe"),
                        "desktop_candidates", JList(),
                        "discover", JMap("type", "command_json", "command", JList("debug", "models"), "timeout", 45),
                        "run", JMap("command", JList("exec", "--model", "{model}", "{prompt}"))),
                    "codex-app", JMap(
                        "name", "Codex App", "vendor", "OpenAI", "kind", "desktop",
                        "store", "^OpenAI\\.Codex$",
                        "executable_candidates", JList(),
                        "desktop_candidates", JList(
                            "%LOCALAPPDATA%\\Microsoft\\WindowsApps\\codex.exe",
                            "%LOCALAPPDATA%\\Microsoft\\WindowsApps\\OpenAI.Codex_*\\codex.exe")),
                    "claude-cli", JMap(
                        "name", "Claude CLI", "vendor", "Anthropic", "kind", "cli",
                        "executable_candidates", JList(
                            "claude.exe", "claude.cmd", "claude",
                            "%APPDATA%\\Claude\\claude-code\\*\\*\\claude.exe",
                            "%APPDATA%\\Claude\\claude-code\\*\\claude.exe",
                            "%USERPROFILE%\\.local\\bin\\claude.exe",
                            "%USERPROFILE%\\.claude\\local\\claude.exe",
                            "%LOCALAPPDATA%\\AnthropicClaude\\claude.exe"),
                        "desktop_candidates", JList(),
                        "discover", JMap("type", "aliases",
                            "aliases", JList(
                                JMap("id", "haiku", "label", "Haiku", "tier", "fast"),
                                JMap("id", "sonnet", "label", "Sonnet", "tier", "balanced"),
                                JMap("id", "opus", "label", "Opus", "tier", "heavy")),
                            "note", "Claude CLI tidak punya command resmi untuk list model non-interaktif; ditampilkan sebagai alias."),
                        "run", JMap("command", JList("-p", "--model", "{model}", "{prompt}"))),
                    "claude-app", JMap(
                        "name", "Claude App", "vendor", "Anthropic", "kind", "desktop",
                        "store", "^Claude$",
                        "executable_candidates", JList(),
                        "desktop_candidates", JList(
                            "%LOCALAPPDATA%\\Microsoft\\WindowsApps\\claude-desktop.exe",
                            "%LOCALAPPDATA%\\Microsoft\\WindowsApps\\Claude_*\\claude-desktop.exe")),
                    "antigravity-cli", JMap(
                        "name", "Antigravity CLI", "vendor", "Google", "kind", "cli",
                        "executable_candidates", JList(
                            "agy.exe", "agy.cmd", "agy",
                            "%LOCALAPPDATA%\\agy\\bin\\agy.exe"),
                        "desktop_candidates", JList(),
                        "discover", JMap("type", "command_table", "command", JList("models"), "timeout", 25),
                        "run", JMap("command", JList("-p", "{prompt}", "--model", "{model}"))),
                    "antigravity-app", JMap(
                        "name", "Antigravity IDE", "vendor", "Google", "kind", "desktop",
                        "store", "^Antigravity( IDE)?$",
                        "executable_candidates", JList(),
                        "desktop_candidates", JList(
                            "%LOCALAPPDATA%\\Programs\\Antigravity IDE\\Antigravity IDE.exe",
                            "%LOCALAPPDATA%\\Programs\\Antigravity\\Antigravity.exe")),
                    "gemini", JMap(
                        "name", "Gemini CLI", "vendor", "Google", "kind", "cli",
                        "executable_candidates", JList("gemini.exe", "gemini.cmd", "gemini"),
                        "desktop_candidates", JList(),
                        "discover", JMap("type", "aliases",
                            "aliases", JList(
                                JMap("id", "gemini-2.5-flash", "label", "2.5 Flash", "tier", "fast"),
                                JMap("id", "gemini-2.5-pro", "label", "2.5 Pro", "tier", "heavy")),
                            "note", "Alias resmi Google."),
                        "run", JMap("command", JList("-m", "{model}", "{prompt}"))),
                    "opencode", JMap(
                        "name", "OpenCode CLI", "vendor", "Community", "kind", "cli",
                        "executable_candidates", JList(
                            "opencode.exe", "opencode.cmd", "opencode",
                            "%APPDATA%\\npm\\opencode.cmd"),
                        "desktop_candidates", JList(),
                        "discover", JMap("type", "command_table", "command", JList("models"), "timeout", 20),
                        "run", JMap("command", JList("run", "--model", "{model}", "{prompt}"))),
                    "commandcode", JMap(
                        "name", "Command Code CLI", "vendor", "Command Code", "kind", "cli",
                        "executable_candidates", JList(
                            "cmdc.exe", "cmdc.cmd", "cmdc",
                            "%APPDATA%\\npm\\cmdc.cmd"),
                        "desktop_candidates", JList(),
                        "discover", JMap("type", "command_table", "command", JList("--list-models"), "timeout", 30),
                        "run", JMap("command", JList("-p", "-m", "{model}", "{prompt}"))),
                    "custom", JMap(
                        "name", "Custom Agent", "vendor", "Lainnya", "kind", "cli",
                        "executable_candidates", JList(),
                        "desktop_candidates", JList(),
                        "discover", JMap("type", "aliases",
                            "aliases", JList(
                                JMap("id", "my-fast", "label", "Fast (edit config.json)", "tier", "fast"),
                                JMap("id", "my-heavy", "label", "Heavy (edit config.json)", "tier", "heavy")),
                            "note", "Isi path CLI + alias model di config.json."),
                        "run", JMap("command", JList("--model", "{model}", "{prompt}")))));
        }

        static Dictionary<string, object> JMap(params object[] kv)
        {
            var d = new Dictionary<string, object>();
            for (int i = 0; i + 1 < kv.Length; i += 2) d[kv[i].ToString()] = kv[i + 1];
            return d;
        }

        static List<object> JList(params object[] items)
        {
            var l = new List<object>();
            foreach (var x in items) l.Add(x);
            return l;
        }

        static Dictionary<string, object> AsMap(object o) { return o as Dictionary<string, object>; }

        // JavaScriptSerializer menghasilkan ArrayList utk array JSON, bukan List<object>
        static List<object> AsList(object o)
        {
            if (o is List<object>) return (List<object>)o;
            var al = o as System.Collections.ArrayList;
            if (al != null)
            {
                var l = new List<object>();
                foreach (var x in al) l.Add(x);
                return l;
            }
            var arr = o as object[];
            if (arr != null) return new List<object>(arr);
            return null;
        }

        static string Str(object o) { return o == null ? "" : o.ToString(); }

        string ConfigPath()
        {
            return Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "config.json");
        }

        void LoadConfig()
        {
            var path = ConfigPath();
            Dictionary<string, object> loaded = null;
            try
            {
                if (File.Exists(path))
                    loaded = _json.Deserialize<Dictionary<string, object>>(File.ReadAllText(path));
            }
            catch { loaded = null; }

            var cfg = loaded ?? new Dictionary<string, object>();

            // migrasi: config pra-v6 pakai candidate lama yang salah path - ganti
            // definisi provider bawaan, user hanya mempertahankan provider tambahan miliknya
            int cfgVersion = ToInt(cfg.ContainsKey("version") ? cfg["version"] : null, 0);
            if (cfgVersion < 6)
            {
                cfg["version"] = 6;
                var defProviders = AsMap(_defaultCfg["providers"]);
                var userProviders = AsMap(cfg.ContainsKey("providers") ? cfg["providers"] : null) ?? new Dictionary<string, object>();
                var migrated = new Dictionary<string, object>();
                foreach (var dk in defProviders.Keys) migrated[dk] = defProviders[dk];
                foreach (var uk in userProviders.Keys)
                    if (!migrated.ContainsKey(uk)) migrated[uk] = userProviders[uk]; // provider kustom user dipertahankan
                cfg["providers"] = migrated;
            }

            MergeDefault(cfg, _defaultCfg);
            _cfg = cfg;
            if (!File.Exists(path)) SafeSaveConfig(cfg);
        }

        void SafeSaveConfig(Dictionary<string, object> cfg)
        {
            try { SaveConfig(cfg); } catch { }
        }

        void MergeDefault(Dictionary<string, object> cfg, Dictionary<string, object> def)
        {
            foreach (var kv in def)
            {
                if (kv.Key == "providers")
                {
                    var defProviders = AsMap(kv.Value);
                    var userProviders = AsMap(cfg.ContainsKey(kv.Key) ? cfg[kv.Key] : null);
                    if (userProviders == null) userProviders = new Dictionary<string, object>();
                    var merged = new Dictionary<string, object>();
                    foreach (var uk in userProviders.Keys) merged[uk] = userProviders[uk];
                    foreach (var dk in defProviders.Keys)
                        if (!merged.ContainsKey(dk)) merged[dk] = defProviders[dk];
                    cfg[kv.Key] = merged;
                }
                else
                {
                    var defVal = AsMap(kv.Value);
                    if (defVal != null)
                    {
                        if (!cfg.ContainsKey(kv.Key) || AsMap(cfg[kv.Key]) == null)
                            cfg[kv.Key] = new Dictionary<string, object>();
                        var m = AsMap(cfg[kv.Key]);
                        foreach (var dk in defVal.Keys)
                            if (!m.ContainsKey(dk)) m[dk] = defVal[dk];
                    }
                    else if (!cfg.ContainsKey(kv.Key))
                    {
                        cfg[kv.Key] = kv.Value;
                    }
                }
            }
        }

        void SaveConfig(Dictionary<string, object> cfg)
        {
            var path = ConfigPath();
            var tmp = path + ".tmp";
            File.WriteAllText(tmp, _json.Serialize(cfg), new UTF8Encoding(false));
            if (File.Exists(path)) File.Delete(path);
            File.Move(tmp, path);
        }

        // =========================================================== routing

        static readonly Regex HeavyRe = new Regex(
            @"\b(architecture|arsitektur|redesign|root[ -]?cause|memory leak|race condition|concurrency|security|keamanan|audit|migration|migrasi|refactor[ -]?(besar|global|monorepo)|monorepo|from scratch|dari nol|full[ -]?stack|debug kompleks|performance|optimasi dalam|scalab|distribut|scheduler|parser|interpreter|implementasi besar|build sistem|buat sistem|app lengkap)\b",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);
        static readonly Regex SimpleRe = new Regex(
            @"\b(rename|typo|format|lint|grep|lookup|list|daftar|syntax|regex sederhana|git status|git diff|cek file|cari file|baca file|apa itu|translate|terjemah|ringkas|summar|tambah komentar|perbaiki typo|ganti nama var)\b",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);
        static readonly Regex QuestionRe = new Regex(
            @"\?|\b(apa|kenapa|bagaimana|gimana|cara|explain|jelaskan|apa itu|berapa)\b",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);
        static readonly Regex WriteRe = new Regex(
            @"\b(buat|bikin|build|implement|implementasi|add|tambah|create|write|fix|perbaiki|refactor)\b",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);
        static readonly Regex DestructiveRe = new Regex(
            @"\b(password|api[ _-]?key|secret|credential|token|delete|hapus|destroy|drop (table|database)|deploy|ssh|registry|system32|\.env|db migrate|force push)\b",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);
        static readonly Regex BulletRe = new Regex(@"^\s*(?:[-*\u2022]|\d+[.)])\s+\S",
            RegexOptions.Compiled | RegexOptions.Multiline);
        static readonly Regex ParallelRe = new Regex(
            @"\b(paralel|parallel|sekaligus|semua (file|modul|halaman|endpoint)|tiap file|batch|beberapa worker|banyak file)\b",
            RegexOptions.Compiled | RegexOptions.IgnoreCase);

        RoutingResult RouteTask(string prompt)
        {
            var rc = AsMap(_cfg.ContainsKey("router") ? _cfg["router"] : null) ?? AsMap(_defaultCfg["router"]);
            int simpleTh = ToInt(rc["simple_threshold"], -1);
            int heavyTh = ToInt(rc["heavy_threshold"], 4);
            int maxW = ToInt(rc["max_parallel_workers"], 4);

            int score = 0;
            var reasons = new List<string>();
            int n = prompt.Length;

            if (n > 1400) { score += 2; reasons.Add("context panjang"); }
            else if (n > 600) { score += 1; reasons.Add("context sedang"); }

            if (HeavyRe.IsMatch(prompt)) { score += 4; reasons.Add("keyword kompleks"); }
            if (SimpleRe.IsMatch(prompt)) { score -= 2; reasons.Add("task sederhana"); }
            bool writing = WriteRe.IsMatch(prompt);
            if (QuestionRe.IsMatch(prompt) && !writing) { score -= 1; reasons.Add("pertanyaan"); }
            if (writing) { score += 1; reasons.Add("tulis kode"); }
            if (n <= 120 && !writing && !HeavyRe.IsMatch(prompt)) { score -= 1; reasons.Add("task pendek"); }

            int steps = BulletRe.Matches(prompt).Count;
            int newlines = 0;
            foreach (char c in prompt) if (c == '\n') newlines++;
            if (steps >= 4 || newlines >= 8) { score += 2; reasons.Add("multi-step (" + Math.Max(steps, newlines / 2) + " langkah)"); }
            else if (steps >= 2 || newlines >= 3) { score += 1; }

            bool parallel = ParallelRe.IsMatch(prompt);
            if (parallel) reasons.Add("bisa diparalelkan");

            bool risky = DestructiveRe.IsMatch(prompt);
            if (risky) { score = Math.Max(score, heavyTh); reasons.Add("safety floor (destructive)"); }

            string tier;
            if (score <= simpleTh) tier = "fast";
            else if (score >= heavyTh) tier = "heavy";
            else tier = "balanced";

            string delegation;
            if (parallel && tier == "heavy") delegation = "planner \u2192 " + maxW + " worker paralel \u2192 reviewer";
            else if (parallel && tier == "balanced") delegation = Math.Max(2, maxW - 2) + " worker paralel";
            else if (risky) delegation = "langsung (1 model + review perubahan)";
            else if (tier == "heavy") delegation = "langkah berat - kerjakan bertahap";
            else delegation = "langsung (1 model)";

            return new RoutingResult { Tier = tier, Delegation = delegation, Reasons = reasons, Score = score, Risky = risky };
        }

        static int ToInt(object o, int def)
        {
            int v;
            return int.TryParse(Str(o), out v) ? v : def;
        }

        static bool ToBool(object o, bool def)
        {
            try { return Convert.ToBoolean(o); }
            catch { return def; }
        }

        ModelInfo ChooseModel(List<ModelInfo> models, string tier)
        {
            if (models == null || models.Count == 0) return null;
            var exact = models.FirstOrDefault(m => m.Tier == tier);
            if (exact != null) return exact;
            if (tier == "heavy")
                return models.FirstOrDefault(m => m.Tier == "balanced") ?? models[models.Count - 1];
            if (tier == "fast")
                return models.FirstOrDefault(m => m.Tier == "balanced") ?? models[0];
            return models[0];
        }

        string TierOf(string text)
        {
            var s = text.ToLowerInvariant();
            if (Regex.IsMatch(s, @"\b(mini|nano|small|lite|haiku|flash)\b")) return "fast";
            if (Regex.IsMatch(s, @"\b(opus|pro|ultra|max|heavy|xhigh|flagship)\b")) return "heavy";
            return "balanced";
        }

        // ======================================================== discovery

        string ExpandPath(string v)
        {
            return Environment.ExpandEnvironmentVariables(v);
        }

        // dukung wildcard di tengah path, mis. %APPDATA%\Claude\claude-code\*\*\claude.exe
        string ExpandWild(string pattern)
        {
            try
            {
                var parts = pattern.Split('\\');
                var dirs = new List<string>();
                var start = parts[0];
                if (start.EndsWith(":") || start.Length == 2) dirs.Add(start + "\\");
                else dirs.Add(start);

                for (int i = 1; i < parts.Length; i++)
                {
                    var seg = parts[i];
                    var next = new List<string>();
                    bool isLast = i == parts.Length - 1;
                    foreach (var d in dirs)
                    {
                        if (seg.IndexOfAny(new[] { '*', '?' }) >= 0)
                        {
                            if (isLast)
                            {
                                foreach (var f in Directory.GetFiles(d, seg))
                                    return f; // file pertama yang cocok
                            }
                            else
                            {
                                foreach (var sub in Directory.GetDirectories(d, seg))
                                    next.Add(sub);
                            }
                        }
                        else
                        {
                            var cand = isLast ? Path.Combine(d, seg) : Path.Combine(d, seg);
                            if (isLast)
                            {
                                if (File.Exists(cand)) return cand;
                            }
                            else if (Directory.Exists(cand)) next.Add(cand);
                        }
                    }
                    if (!isLast)
                    {
                        if (next.Count == 0) return null;
                        dirs = next;
                    }
                }
            }
            catch { }
            return null;
        }

        string ResolveCandidates(List<object> candidates)
        {
            if (candidates == null) return null;
            foreach (var rawObj in candidates)
            {
                var raw = Str(rawObj);
                if (string.IsNullOrWhiteSpace(raw)) continue;
                var v = ExpandPath(raw);

                if (v.IndexOfAny(new[] { '*', '?' }) >= 0)
                {
                    var hit = ExpandWild(v);
                    if (hit != null) return hit;
                    continue;
                }

                try
                {
                    var dir = Path.GetDirectoryName(v);
                    if (!string.IsNullOrEmpty(dir) && Directory.Exists(dir))
                    {
                        var full = Path.Combine(dir, Path.GetFileName(v));
                        if (File.Exists(full)) return full;
                    }
                    if (File.Exists(v)) return v;
                }
                catch { }
                var pathVar = Environment.GetEnvironmentVariable("PATH") ?? "";
                foreach (var p in pathVar.Split(';'))
                {
                    if (string.IsNullOrWhiteSpace(p)) continue;
                    try
                    {
                        var cand = Path.Combine(p.Trim(), Path.GetFileName(v));
                        if (File.Exists(cand)) return cand;
                    }
                    catch { }
                }
            }
            return null;
        }

        string ResolveDesktop(List<object> candidates)
        {
            if (candidates == null) return null;
            foreach (var rawObj in candidates)
            {
                var raw = Str(rawObj);
                if (string.IsNullOrWhiteSpace(raw)) continue;
                var v = ExpandPath(raw);
                if (v.IndexOfAny(new[] { '*', '?' }) >= 0)
                {
                    var hit = ExpandWild(v);
                    if (hit != null) return hit;
                    continue;
                }
                if (File.Exists(v)) return v;
            }
            return null;
        }

        // ------------------------------------------------------------ store app

        List<string[]> _storeApps; // [name, family, appId, exe, version]

        void EnsureStoreInventory()
        {
            if (_storeApps != null) return;
            _storeApps = new List<string[]>();
            try
            {
                var ps = Path.Combine(
                    Environment.GetFolderPath(Environment.SpecialFolder.System), "WindowsPowerShell", "v1.0", "powershell.exe");
                if (!File.Exists(ps)) return;
                var script =
                    "$ErrorActionPreference='SilentlyContinue'\n" +
                    "$targets=@('OpenAI.Codex','Claude','Antigravity','OpenCode','Gemini')\n" +
                    "$apps = Get-AppxPackage | Where-Object { $targets -contains $_.Name } | ForEach-Object {\n" +
                    "  $p=$_; $m=Get-AppxPackageManifest -Package $p.PackageFullName\n" +
                    "  if ($m -and $m.Package.Applications) { foreach($a in $m.Package.Applications.Application){\n" +
                    "    [pscustomobject]@{name=$p.Name; family=$p.PackageFamilyName; appId=[string]$a.Id; exe=[string]$a.Executable; version=[string]$p.Version} } }\n" +
                    "}\n" +
                    "$apps | ConvertTo-Json -Depth 3 -Compress";
                var r = CaptureCli(ps, "-NoProfile -NonInteractive -Command " + QuoteArg(script), 20000);
                if (r.ExitCode == 0 && !string.IsNullOrWhiteSpace(r.StdOut))
                {
                    var data = _json.DeserializeObject(r.StdOut.Trim());
                    if (data is Dictionary<string, object>)
                        AddStoreApp(AsMap(data));
                    else if (data is System.Collections.IEnumerable && !(data is string))
                        foreach (var item in (System.Collections.IEnumerable)data)
                            AddStoreApp(AsMap(item));
                }
            }
            catch { }
        }

        void AddStoreApp(Dictionary<string, object> m)
        {
            if (m == null || !m.ContainsKey("family")) return;
            _storeApps.Add(new[]
            {
                Str(m.ContainsKey("name") ? m["name"] : ""),
                Str(m["family"]),
                Str(m.ContainsKey("appId") ? m["appId"] : "App"),
                Str(m.ContainsKey("exe") ? m["exe"] : ""),
                Str(m.ContainsKey("version") ? m["version"] : "")
            });
        }

        string FindStoreApp(string nameRegex)
        {
            if (_storeApps == null || string.IsNullOrEmpty(nameRegex)) return null;
            var re = new Regex(nameRegex, RegexOptions.IgnoreCase);
            foreach (var a in _storeApps)
                if (re.IsMatch(a[0])) return a[1] + "!" + a[2];
            return null;
        }

        void LaunchApp(string target)
        {
            if (string.IsNullOrEmpty(target)) return;
            if (target.StartsWith("aumid:", StringComparison.OrdinalIgnoreCase))
            {
                Process.Start("explorer.exe", "shell:appsFolder\\" + target.Substring(6));
            }
            else
            {
                Process.Start(new ProcessStartInfo(target) { UseShellExecute = true });
            }
        }

        List<ModelInfo> ParseJsonModels(string raw)
        {
            try
            {
                var data = _json.DeserializeObject(raw);
                var acc = new List<ModelInfo>();
                var seen = new HashSet<string>();
                WalkModels(data, acc, seen);
                return acc;
            }
            catch
            {
                return new List<ModelInfo>();
            }
        }

        void WalkModels(object node, List<ModelInfo> acc, HashSet<string> seen)
        {
            if (node == null) return;
            var map = node as Dictionary<string, object>;
            if (map != null)
            {
                string mid = null, label = "";
                foreach (var k in new[] { "slug", "id", "model", "model_id" })
                {
                    if (map.ContainsKey(k) && !string.IsNullOrWhiteSpace(Str(map[k]))) { mid = Str(map[k]).Trim(); break; }
                }
                foreach (var k in new[] { "display_name", "name", "label", "title" })
                {
                    if (map.ContainsKey(k) && !string.IsNullOrWhiteSpace(Str(map[k]))) { label = Str(map[k]).Trim(); break; }
                }
                if (!string.IsNullOrEmpty(mid) && Regex.IsMatch(mid, @"^[A-Za-z0-9][A-Za-z0-9._:/+\-]*$") && !seen.Contains(mid))
                {
                    seen.Add(mid);
                    acc.Add(new ModelInfo
                    {
                        Id = mid,
                        Label = string.IsNullOrEmpty(label) ? mid : label,
                        Tier = TierOf(mid + " " + label),
                        Source = "live"
                    });
                }
                foreach (var v in map.Values) WalkModels(v, acc, seen);
            }
            else
            {
                var list = node as System.Collections.IEnumerable;
                if (list != null && !(node is string))
                {
                    foreach (var v in list) WalkModels(v, acc, seen);
                }
            }
        }

        List<ModelInfo> ParseTableModels(string raw)
        {
            var acc = new List<ModelInfo>();
            var seen = new HashSet<string>();
            if (raw == null) return acc;
            foreach (var line0 in raw.Split('\n'))
            {
                var line = line0.Trim();
                if (line.Length == 0) continue;
                var parts = Regex.Split(line, @"\s{2,}|\t+");
                var mid = parts[0].Trim();
                var label = parts.Length > 1 ? parts[1].Trim() : mid;
                if (Regex.IsMatch(mid, @"^[A-Za-z0-9][A-Za-z0-9._:/+\-]*$") && !seen.Contains(mid))
                {
                    seen.Add(mid);
                    acc.Add(new ModelInfo { Id = mid, Label = label, Tier = TierOf(mid + " " + label), Source = "live" });
                }
            }
            return acc;
        }

        List<ModelInfo> AliasModels(List<object> aliases)
        {
            var acc = new List<ModelInfo>();
            if (aliases == null) return acc;
            foreach (var aObj in aliases)
            {
                var a = AsMap(aObj);
                if (a == null) continue;
                var id = Str(a.ContainsKey("id") ? a["id"] : "");
                if (string.IsNullOrEmpty(id)) continue;
                string t = Str(a.ContainsKey("tier") ? a["tier"] : "");
                if (t != "fast" && t != "balanced" && t != "heavy")
                    t = TierOf(id + " " + Str(a.ContainsKey("label") ? a["label"] : ""));
                acc.Add(new ModelInfo
                {
                    Id = id,
                    Label = Str(a.ContainsKey("label") ? a["label"] : id),
                    Tier = t,
                    Source = "alias"
                });
            }
            return acc;
        }

        class CaptureResult
        {
            public int ExitCode = -1;
            public string StdOut = "";
            public string StdErr = "";
            public bool TimedOut;
        }

        CaptureResult CaptureCli(string exe, string argsList, int timeoutMs)
        {
            var res = new CaptureResult();
            try
            {
                var psi = new ProcessStartInfo
                {
                    UseShellExecute = false,
                    CreateNoWindow = true,
                    RedirectStandardOutput = true,
                    RedirectStandardError = true
                };
                // .cmd/.bat hanya bisa dieksekusi lewat cmd.exe
                if (exe.EndsWith(".cmd", StringComparison.OrdinalIgnoreCase)
                    || exe.EndsWith(".bat", StringComparison.OrdinalIgnoreCase))
                {
                    psi.FileName = "cmd.exe";
                    psi.Arguments = "/c " + QuoteArg(exe) + (argsList.Length > 0 ? " " + argsList : "");
                }
                else
                {
                    psi.FileName = exe;
                    psi.Arguments = argsList;
                }
                using (var p = Process.Start(psi))
                {
                    var so = p.StandardOutput.ReadToEndAsync();
                    var se = p.StandardError.ReadToEndAsync();
                    if (!p.WaitForExit(timeoutMs))
                    {
                        try { p.Kill(); } catch { }
                        res.TimedOut = true;
                    }
                    try { res.StdOut = so.Result ?? ""; } catch { }
                    try { res.StdErr = se.Result ?? ""; } catch { }
                    if (!res.TimedOut)
                    {
                        try { res.ExitCode = p.ExitCode; } catch { }
                        p.WaitForExit(2000);
                    }
                }
            }
            catch (Exception ex)
            {
                res.StdErr = ex.Message;
                res.ExitCode = -1;
            }
            return res;
        }

        Dictionary<string, object> ProviderConf(string key)
        {
            var provs = AsMap(_cfg["providers"]);
            return provs.ContainsKey(key) ? AsMap(provs[key]) : null;
        }

        void DiscoverAll()
        {
            Task.Factory.StartNew(delegate
            {
                EnsureStoreInventory();
                var remaining = _entries.Count;
                foreach (var e in _entries.Values)
                {
                    var key = e.Key;
                    ProviderState st;
                    try { st = DiscoverEntry(e); }
                    catch (Exception ex)
                    {
                        st = new ProviderState { Done = true, Note = ex.Message };
                    }
                    SafeInvoke(delegate
                    {
                        _states[key] = st;
                        UpdateCard(key);
                        remaining--;
                        if (remaining <= 0) { UpdateStatusSummary(); DumpDebugStates(); }
                        if (_selectedKey == key) ShowMain();
                        if (remaining <= 0 && _selectedKey == "auto") ShowMain();
                    });
                }
            });
        }

        void SafeInvoke(MethodInvoker action)
        {
            try
            {
                if (IsHandleCreated && !IsDisposed) BeginInvoke(action);
            }
            catch { }
        }

        void DumpDebugStates()
        {
            try
            {
                var sb = new StringBuilder();
                sb.Append("{\n");
                bool first = true;
                foreach (var kv in _states)
                {
                    if (!first) sb.Append(",\n");
                    first = false;
                    var e = _entries.ContainsKey(kv.Key) ? _entries[kv.Key] : null;
                    sb.Append("  \"").Append(kv.Key).Append("\": {\"kind\": \"").Append(e != null ? e.Kind : "?")
                        .Append("\", \"cli\": \"").Append(kv.Value.CliPath ?? "")
                        .Append("\", \"desktop\": \"").Append(kv.Value.DesktopPath ?? "")
                        .Append("\", \"models\": ").Append(kv.Value.Models.Count)
                        .Append(", \"note\": \"").Append(kv.Value.Note.Replace("\\", "\\\\").Replace("\"", "'"))
                        .Append("\"}");
                }
                sb.Append("\n}");
                File.WriteAllText(Path.Combine(AppDomain.CurrentDomain.BaseDirectory, "zwartflow-state.log"), sb.ToString());
            }
            catch { }
        }

        ProviderState DiscoverEntry(ProviderEntry e)
        {
            var conf = ProviderConf(e.Key);
            var st = new ProviderState();
            if (conf == null) { st.Note = "config tidak ditemukan"; st.Done = true; return st; }

            st.CliPath = ResolveCandidates(AsList(conf.ContainsKey("executable_candidates") ? conf["executable_candidates"] : null));
            st.DesktopPath = ResolveDesktop(AsList(conf.ContainsKey("desktop_candidates") ? conf["desktop_candidates"] : null));

            if (e.Kind == "desktop")
            {
                if (st.DesktopPath != null)
                {
                    st.LaunchTarget = st.DesktopPath;
                    st.Note = "app ditemukan";
                }
                else
                {
                    var aumid = FindStoreApp(Str(conf.ContainsKey("store") ? conf["store"] : ""));
                    if (aumid != null)
                    {
                        st.DesktopPath = "aumid:" + aumid;
                        st.LaunchTarget = st.DesktopPath;
                        st.Note = "app ditemukan (Microsoft Store)";
                    }
                    else st.Note = "app tidak ditemukan";
                }
                st.Done = true;
                return st;
            }

            if (string.IsNullOrEmpty(st.CliPath))
            {
                st.Note = "CLI tidak terdeteksi";
                var dc = AsMap(conf.ContainsKey("discover") ? conf["discover"] : null);
                if (dc != null && Str(dc.ContainsKey("type") ? dc["type"] : "") == "aliases")
                    st.Models = AliasModels(AsList(dc.ContainsKey("aliases") ? dc["aliases"] : null));
                st.Done = true;
                return st;
            }

            var disc = AsMap(conf.ContainsKey("discover") ? conf["discover"] : null);
            var type = disc != null ? Str(disc.ContainsKey("type") ? disc["type"] : "") : "";
            try
            {
                if (type == "command_json")
                {
                    int timeout = ToInt(disc.ContainsKey("timeout") ? disc["timeout"] : null, 30);
                    var r = CaptureCli(st.CliPath, ArgsList(disc["command"]), timeout * 1000);
                    if (r.TimedOut) st.Note = "timeout setelah " + timeout + "s";
                    else if (r.ExitCode == 0)
                    {
                        st.Models = ParseJsonModels(r.StdOut);
                        st.Note = st.Models.Count > 0 ? "katalog live" : "katalog kosong";
                    }
                    else st.Note = string.IsNullOrWhiteSpace(r.StdErr) ? "exit " + r.ExitCode : r.StdErr.Trim();
                }
                else if (type == "command_table")
                {
                    int timeout = ToInt(disc.ContainsKey("timeout") ? disc["timeout"] : null, 20);
                    var r2 = CaptureCli(st.CliPath, ArgsList(disc["command"]), timeout * 1000);
                    if (r2.TimedOut) st.Note = "timeout setelah " + timeout + "s";
                    else if (r2.ExitCode == 0)
                    {
                        st.Models = ParseTableModels(r2.StdOut);
                        st.Note = st.Models.Count > 0 ? "katalog live (teks)" : "katalog kosong";
                    }
                    else st.Note = string.IsNullOrWhiteSpace(r2.StdErr) ? "exit " + r2.ExitCode : r2.StdErr.Trim();
                }
                else if (type == "aliases")
                {
                    st.Models = AliasModels(AsList(disc.ContainsKey("aliases") ? disc["aliases"] : null));
                    st.Note = Str(disc.ContainsKey("note") ? disc["note"] : "alias");
                }
                else
                {
                    st.Note = "discovery tidak didukung: " + type;
                }
            }
            catch (Exception ex)
            {
                st.Note = ex.Message;
            }
            st.Done = true;
            return st;
        }

        string ArgsList(object cmdObj)
        {
            var args = new StringBuilder();
            foreach (var a in AsList(cmdObj))
            {
                if (args.Length > 0) args.Append(' ');
                args.Append(QuoteArg(Str(a)));
            }
            return args.ToString();
        }

        void BuildEntries()
        {
            _entries.Clear();
            var provs = AsMap(_cfg["providers"]);
            foreach (var kv in provs)
            {
                var conf = AsMap(kv.Value);
                if (conf == null) continue;
                var kind = Str(conf.ContainsKey("kind") ? conf["kind"] : "cli").ToLowerInvariant();
                var desktopCandidates = AsList(conf.ContainsKey("desktop_candidates") ? conf["desktop_candidates"] : null);
                var hasDesktopPath = desktopCandidates != null && desktopCandidates.Count > 0
                                     && ResolveDesktop(desktopCandidates) != null && kind != "desktop";

                var name = Str(conf.ContainsKey("name") ? conf["name"] : kv.Key);
                var vendor = Str(conf.ContainsKey("vendor") ? conf["vendor"] : "");

                if (hasDesktopPath && kind == "cli")
                {
                    _entries[kv.Key] = new ProviderEntry { Key = kv.Key, Name = name + " CLI", Vendor = vendor, Kind = "cli" };
                    _entries[kv.Key + ".app"] = new ProviderEntry { Key = kv.Key + ".app", Name = name + " App", Vendor = vendor, Kind = "desktop", CliKey = kv.Key };
                }
                else
                {
                    _entries[kv.Key] = new ProviderEntry
                    {
                        Key = kv.Key,
                        Name = name,
                        Vendor = vendor,
                        Kind = kind == "desktop" ? "desktop" : "cli",
                        CliKey = kind == "desktop" ? kv.Key.Replace(".app", "") : null
                    };
                }
            }
        }

        // ================================================================ UI

        void BuildUi()
        {
            // topbar: judul + tombol
            var topbar = new Panel { Dock = DockStyle.Top, Height = 56, BackColor = PANEL };
            var title = new Label { Text = "ZwartFlow", AutoSize = true, ForeColor = TEXT, Font = Semibold(14), Location = new Point(16, 13) };
            var topBtns = new FlowLayoutPanel { Dock = DockStyle.Right, FlowDirection = FlowDirection.LeftToRight, BackColor = PANEL, WrapContents = false, Padding = new Padding(0, 12, 14, 0) };
            var refreshBtn = Flat("Refresh", delegate { DiscoverAll(); });
            var settingsBtn = Flat("Settings", delegate { OpenSettings(); });
            refreshBtn.Margin = new Padding(0, 0, 8, 0);
            topBtns.Controls.Add(refreshBtn);
            topBtns.Controls.Add(settingsBtn);
            topbar.Controls.Add(title);
            topbar.Controls.Add(topBtns);

            // root: sidebar kiri + area utama
            var root = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = BG, ColumnCount = 2, RowCount = 1 };
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Absolute, 248f));
            root.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
            root.RowStyles.Add(new RowStyle(SizeType.Percent, 100f));

            // ---------- sidebar ----------
            var sidebar = new Panel { Dock = DockStyle.Fill, BackColor = PANEL };
            var sideHeader = new Label
            {
                Text = "  AGENT & APP",
                Dock = DockStyle.Top,
                Height = 34,
                ForeColor = MUTED,
                BackColor = PANEL,
                Font = Semibold(8f),
                TextAlign = ContentAlignment.MiddleLeft
            };
            _cardsTlp = new TableLayoutPanel
            {
                Dock = DockStyle.Fill,
                ColumnCount = 1,
                AutoScroll = true,
                BackColor = PANEL,
                Padding = new Padding(8, 4, 8, 8)
            };
            _cardsTlp.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
            sidebar.Controls.Add(_cardsTlp);
            sidebar.Controls.Add(sideHeader);

            // ---------- main ----------
            var main = new TableLayoutPanel { Dock = DockStyle.Fill, BackColor = BG, ColumnCount = 1, Padding = new Padding(12, 10, 12, 8) };
            main.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 26f));   // step 1 label
            main.RowStyles.Add(new RowStyle(SizeType.Percent, 30f));    // task box
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 52f));   // buttons
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 92f));   // result card
            main.RowStyles.Add(new RowStyle(SizeType.Absolute, 30f));   // models header
            main.RowStyles.Add(new RowStyle(SizeType.Percent, 70f));    // model list

            var step1 = new Label
            {
                Text = "1  Tulis task kamu",
                AutoSize = true,
                ForeColor = TEXT,
                BackColor = BG,
                Font = Semibold(10f),
                Margin = new Padding(2, 4, 0, 0)
            };
            _taskBox = new TextBox
            {
                Multiline = true,
                BackColor = PANEL2,
                ForeColor = TEXT,
                BorderStyle = BorderStyle.FixedSingle,
                Font = new Font("Segoe UI", 10.5f),
                Dock = DockStyle.Fill,
                Margin = new Padding(2, 4, 2, 4)
            };

            var buttonsRow = new Panel { Dock = DockStyle.Fill, BackColor = BG, Margin = new Padding(0) };
            var analyzeBtn = FlatAccent("2 \u00b7 Analyze & Route", delegate { Analyze(); });
            var clearBtn = Flat("Clear", delegate { _taskBox.Clear(); });
            analyzeBtn.Font = Semibold(10f);
            clearBtn.Font = new Font("Segoe UI", 9.5f);
            analyzeBtn.Location = new Point(2, 10);
            clearBtn.Location = new Point(analyzeBtn.Right + 10, 13);
            buttonsRow.Controls.Add(analyzeBtn);
            buttonsRow.Controls.Add(clearBtn);

            // kartu hasil
            _resultCard = new Panel { Dock = DockStyle.Fill, BackColor = PANEL2, Margin = new Padding(2, 6, 2, 6), Padding = new Padding(14, 10, 14, 10) };
            _resultTier = new Label
            {
                Text = "\u2014",
                ForeColor = MUTED,
                BackColor = PANEL,
                Font = Semibold(13f),
                AutoSize = true,
                Padding = new Padding(10, 8, 10, 8),
                Location = new Point(14, 20)
            };
            _resultMain = new Label
            {
                Text = "Hasil routing muncul di sini",
                AutoSize = true,
                ForeColor = TEXT,
                BackColor = PANEL2,
                Font = Semibold(11f),
                Location = new Point(150, 16)
            };
            _resultSub = new Label
            {
                Text = "Tulis task di atas lalu tekan Analyze & Route \u2014 router menilai kompleksitas 100% lokal.",
                AutoSize = true,
                ForeColor = MUTED,
                BackColor = PANEL2,
                Font = new Font("Segoe UI", 8.5f),
                Location = new Point(150, 44),
                MaximumSize = new Size(470, 0),
                UseMnemonic = false
            };
            _runBtn = FlatAccent("Run Selected", delegate { RunSelected(); });
            _runBtn.Font = Semibold(10f);
            _runBtn.Enabled = false;
            var runFlp = new FlowLayoutPanel
            {
                Dock = DockStyle.Right,
                FlowDirection = FlowDirection.TopDown,
                BackColor = PANEL2,
                WrapContents = false,
                AutoSize = true,
                AutoSizeMode = AutoSizeMode.GrowAndShrink
            };
            _runBtn.Margin = new Padding(0, 27, 0, 0);
            runFlp.Controls.Add(_runBtn);
            _resultCard.Controls.Add(_resultTier);
            _resultCard.Controls.Add(_resultMain);
            _resultCard.Controls.Add(_resultSub);
            _resultCard.Controls.Add(runFlp);

            var step3 = new Label
            {
                Text = "3  Model tersedia \u2014 klik Use untuk pilih manual",
                AutoSize = true,
                ForeColor = TEXT,
                BackColor = BG,
                Font = Semibold(10f),
                Margin = new Padding(2, 8, 0, 0)
            };
            _modelsHint = new Label { Text = "", AutoSize = true, ForeColor = MUTED, BackColor = BG, Font = new Font("Segoe UI", 8f), Margin = new Padding(2, 0, 0, 0) };

            var modelsScroll = new Panel { Dock = DockStyle.Fill, BackColor = BG, AutoScroll = true, Margin = new Padding(2, 2, 6, 2) };
            _modelsTlp = new TableLayoutPanel
            {
                ColumnCount = 1,
                AutoSize = true,
                BackColor = BG,
                Dock = DockStyle.Top,
                Padding = new Padding(0, 2, 6, 8)
            };
            _modelsTlp.ColumnStyles.Add(new ColumnStyle(SizeType.Percent, 100f));
            modelsScroll.Controls.Add(_modelsTlp);

            main.Controls.Add(step1, 0, 0);
            main.Controls.Add(_taskBox, 0, 1);
            main.Controls.Add(buttonsRow, 0, 2);
            main.Controls.Add(_resultCard, 0, 3);
            main.Controls.Add(step3, 0, 4);
            main.Controls.Add(modelsScroll, 0, 5);

            var statusStrip = new Panel { Dock = DockStyle.Bottom, Height = 24, BackColor = BG };
            _statusLabel = new Label { Text = "", AutoSize = true, ForeColor = MUTED, Font = new Font("Segoe UI", 7.5f), Location = new Point(18, 5) };
            statusStrip.Controls.Add(_statusLabel);

            root.Controls.Add(sidebar, 0, 0);
            root.Controls.Add(main, 1, 0);

            // urutan dock: fill dulu, lalu bottom & top diproses lebih akhir
            Controls.Add(root);
            Controls.Add(statusStrip);
            Controls.Add(topbar);
        }

        void RefreshCards()
        {
            _cardsTlp.Controls.Clear();
            _cardsTlp.RowStyles.Clear();
            _cardsTlp.RowCount = 0;
            _cardPanels.Clear();
            _cardStatus.Clear();
            foreach (var e in _entries.Values)
            {
                var cardKey = e.Key;
                var root = new Panel { BackColor = PANEL, Margin = new Padding(0, 3, 0, 3), Padding = new Padding(10, 8, 8, 8) };
                var strip = new Panel { BackColor = ACCENT, Width = 4, Dock = DockStyle.Left, Visible = false };
                var inner = new Panel { Dock = DockStyle.Fill, BackColor = PANEL };
                var titleLb = new Label { Text = e.Name, AutoSize = true, ForeColor = e.Kind == "desktop" ? MUTED : TEXT, Font = Semibold(9.5f), Location = new Point(46, 4) };
                var statusLb = new Label { Text = "memeriksa\u2026", AutoSize = true, ForeColor = MUTED, Font = new Font("Segoe UI", 7.5f), Location = new Point(46, 28) };

                EventHandler click = delegate { SelectEntry(cardKey); };
                root.Click += click;
                inner.Click += click;
                titleLb.Click += click;
                statusLb.Click += click;

                root.MouseEnter += delegate { if (_selectedKey != cardKey) root.BackColor = PANEL2; };
                root.MouseLeave += delegate { if (_selectedKey != cardKey) root.BackColor = PANEL; };

                root.Controls.Add(strip);
                root.Controls.Add(inner);
                inner.Controls.Add(titleLb);
                inner.Controls.Add(statusLb);

                var icon = new Panel { Size = new Size(32, 32), BackColor = PANEL, Location = new Point(8, 9) };
                icon.Click += click;
                icon.MouseEnter += delegate { if (_selectedKey != cardKey) root.BackColor = PANEL2; };
                icon.MouseLeave += delegate { if (_selectedKey != cardKey) root.BackColor = PANEL; };
                icon.Paint += (s, ev) => DrawGlyph(ev.Graphics, icon.ClientRectangle, cardKey, e.Kind == "desktop", TEXT, MUTED);
                inner.Controls.Add(icon);
                icon.BringToFront();

                _cardPanels[cardKey] = root;
                _cardStatus[cardKey] = statusLb;
                _cardStrips[cardKey] = strip;
                _cardsTlp.RowCount++;
                _cardsTlp.RowStyles.Add(new RowStyle(SizeType.Absolute, 64));
                _cardsTlp.Controls.Add(root, 0, _cardsTlp.RowCount - 1);
                root.Dock = DockStyle.Fill;
            }
        }

        // ============================================================ logos

        string BrandKey(string entryKey)
        {
            var k = entryKey.ToLowerInvariant();
            if (k.StartsWith("codex")) return "codex";
            if (k.StartsWith("claude")) return "claude";
            if (k.StartsWith("antigravity")) return "antigravity";
            if (k.StartsWith("gemini")) return "gemini";
            if (k.StartsWith("opencode")) return "opencode";
            if (k.StartsWith("commandcode")) return "commandcode";
            return null;
        }

        void LoadLogos()
        {
            foreach (var name in new[] { "codex", "claude", "antigravity", "gemini", "opencode", "commandcode" })
            {
                try
                {
                    using (var s = typeof(MainForm).Assembly.GetManifestResourceStream("ZwartFlow.logos." + name + ".png"))
                    {
                        if (s == null) continue;
                        using (var mem = new MemoryStream())
                        {
                            s.CopyTo(mem);
                            _logos[name] = Image.FromStream(mem);
                        }
                    }
                }
                catch { }
            }
        }

        void DrawGlyph(Graphics g, Rectangle r, string key, bool desktop, Color fg, Color muted)
        {
            g.SmoothingMode = System.Drawing.Drawing2D.SmoothingMode.AntiAlias;
            g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
            g.InterpolationMode = System.Drawing.Drawing2D.InterpolationMode.HighQualityBicubic;

            var brand = BrandKey(key);
            Image logo;
            if (brand != null && _logos.TryGetValue(brand, out logo))
            {
                float box = r.Width - 4f;
                float scale = Math.Min(box / logo.Width, box / logo.Height);
                float w = logo.Width * scale, h = logo.Height * scale;
                var dest = new RectangleF(r.X + (r.Width - w) / 2f, r.Y + (r.Height - h) / 2f, w, h);
                g.DrawImage(logo, dest);
                if (desktop)
                {
                    var cx = r.X + r.Width / 2f;
                    var cy = r.Y + r.Height / 2f;
                    var radius = r.Width / 2f;
                    using (var ring = new Pen(Color.FromArgb(139, 149, 165), 1.4f))
                        g.DrawEllipse(ring, cx - radius, cy - radius, radius * 2f - 1f, radius * 2f - 1f);
                }
                return;
            }

            // fallback: monogram brand
            string mono;
            Color color;
            if (key.StartsWith("codex")) { mono = "CX"; color = Color.FromArgb(16, 163, 127); }
            else if (key.StartsWith("claude")) { mono = "CL"; color = Color.FromArgb(217, 119, 87); }
            else if (key.StartsWith("antigravity")) { mono = "AG"; color = Color.FromArgb(76, 141, 255); }
            else if (key == "gemini") { mono = "GM"; color = Color.FromArgb(139, 92, 246); }
            else if (key.StartsWith("opencode")) { mono = "OC"; color = Color.FromArgb(245, 158, 11); }
            else if (key.StartsWith("commandcode")) { mono = "CC"; color = Color.FromArgb(56, 189, 248); }
            else { mono = "+"; color = Color.FromArgb(120, 130, 145); }

            var cx2 = r.X + r.Width / 2f;
            var cy2 = r.Y + r.Height / 2f;
            var radius2 = r.Width / 2f - 1f;

            using (var brush = new SolidBrush(color))
                g.FillEllipse(brush, cx2 - radius2, cy2 - radius2, radius2 * 2f, radius2 * 2f);

            if (desktop)
            {
                using (var ring = new Pen(Color.FromArgb(230, 234, 240), 1.6f))
                    g.DrawEllipse(ring, cx2 - radius2 - 2f, cy2 - radius2 - 2f, radius2 * 2f + 4f, radius2 * 2f + 4f);
            }

            var font = new Font("Segoe UI", 7.5f, FontStyle.Bold);
            var sz = g.MeasureString(mono, font);
            using (var brush = new SolidBrush(Color.White))
                g.DrawString(mono, font, brush, cx2 - sz.Width / 2f, cy2 - sz.Height / 2f);
        }

        void UpdateStatusSummary()
        {
            int cli = 0, app = 0;
            foreach (var kv in _states)
            {
                if (!string.IsNullOrEmpty(kv.Value.CliPath)) cli++;
                if (!string.IsNullOrEmpty(kv.Value.DesktopPath)) app++;
            }
            _statusLabel.Text = cli + " CLI terdeteksi \u00b7 " + app + " app desktop ditemukan \u00b7 routing 100% lokal \u00b7 tanpa shell=True";
        }

        void UpdateCard(string key)
        {
            if (!_cardStatus.ContainsKey(key)) return;
            var st = GetState(key);
            if (st == null) { _cardStatus[key].Text = "memeriksa\u2026"; return; }
            var e = _entries[key];
            string status;
            if (e.Kind == "desktop")
            {
                status = st.DesktopPath != null ? "App \u2713" : "App \u2014";
            }
            else
            {
                status = (st.CliPath != null ? "CLI \u2713" : "CLI \u2014") +
                         (st.DesktopPath != null ? "   App \u2713" : "");
            }
            _cardStatus[key].Text = status;
            if (_cardPanels.ContainsKey(key)) _cardPanels[key].Invalidate();
        }

        ProviderState GetState(string key)
        {
            ProviderState s;
            return _states.TryGetValue(key, out s) ? s : null;
        }

        void SelectEntry(string key)
        {
            _selectedKey = key;
            foreach (var kv in _cardPanels)
            {
                bool sel = kv.Key == key;
                kv.Value.BackColor = sel ? PANEL2 : PANEL;
                Panel strip;
                if (_cardStrips.TryGetValue(kv.Key, out strip)) strip.Visible = sel;
            }
            ShowMain();
        }

        void ShowMain()
        {
            if (_modelsTlp.InvokeRequired)
            {
                SafeInvoke(delegate { ShowMain(); });
                return;
            }
            RefreshModelArea();
        }

        void RefreshModelArea()
        {
            _modelsTlp.Controls.Clear();
            _modelsTlp.RowStyles.Clear();
            _modelsTlp.RowCount = 0;

            string key = _selectedKey;
            if (key == "auto")
            {
                var pref = PrefProvider();
                if (pref == null)
                {
                    _modelsHint.Text = "auto \u2014 menunggu pemindaian CLI selesai\u2026";
                    AddRowNote("Pemindaian CLI & desktop app masih berjalan. Hasil akan muncul di sini setelah selesai (Refresh untuk pindai ulang).");
                    return;
                }
                key = pref;
            }

            var e = _entries[key];
            var st = GetState(key);
            if (st == null)
            {
                _modelsHint.Text = e.Name + " \u2014 memeriksa\u2026";
                AddRowNote("Memeriksa provider\u2026");
                return;
            }

            var conf = ProviderConf(e.Kind == "desktop" && e.CliKey != null ? e.CliKey : key);
            var vendor = conf != null && conf.ContainsKey("vendor") ? Str(conf["vendor"]) : "";
            var cliMark = string.IsNullOrEmpty(st.CliPath) ? "CLI \u2014" : "CLI \u2713";
            var appMark = st.DesktopPath != null ? "App \u2713" : "App \u2014";
            var hintText = (key != "auto" && _selectedKey == "auto" ? "auto \u2192 " : "")
                + e.Name + "  \u00b7  " + vendor + "  \u00b7  " + cliMark + "  \u00b7  " + appMark
                + (st.Note.Length > 0 ? ("  \u00b7  " + st.Note) : "");
            _modelsHint.Text = hintText;

            if (e.Kind == "desktop")
            {
                AddRowNote("Provider ini adalah app desktop. Pemilihan model otomatis hanya berlaku untuk CLI.");
                if (st.LaunchTarget != null) AddRowOpenApp("Buka " + e.Name, st.LaunchTarget);
                else AddRowNote("Desktop app tidak ditemukan - periksa path di Settings.");
                return;
            }

            if (st.Models == null || st.Models.Count == 0)
            {
                AddRowNote("Belum ada daftar model: " + st.Note);
                if (st.LaunchTarget != null) AddRowOpenApp("Buka Desktop App", st.LaunchTarget);
                return;
            }

            foreach (var m in st.Models)
                AddRowModel(e, m);
        }

        void AddRowNote(string text)
        {
            var lb = new Label
            {
                Text = text,
                ForeColor = MUTED,
                BackColor = PANEL,
                Font = new Font("Segoe UI", 9f),
                AutoSize = true,
                MaximumSize = new Size(Math.Max(320, _modelsTlp.ClientSize.Width - 44), 0),
                Margin = new Padding(6, 8, 6, 8)
            };
            AddModelRow(lb, 0);
        }

        void AddRowOpenApp(string label, string target)
        {
            var row = new Panel { BackColor = PANEL2, Margin = new Padding(0, 3, 0, 3), Padding = new Padding(10, 8, 10, 8) };
            var btn = FlatAccent(label, delegate
            {
                try { LaunchApp(target); }
                catch (Exception ex) { MessageBox.Show("Gagal membuka: " + ex.Message, "ZwartFlow", MessageBoxButtons.OK, MessageBoxIcon.Error); }
            });
            btn.Location = new Point(10, 8);
            row.Controls.Add(btn);
            var lb = new Label { Text = target.StartsWith("aumid:", StringComparison.OrdinalIgnoreCase) ? "Microsoft Store app" : target, ForeColor = MUTED, AutoSize = true, BackColor = PANEL2, Font = new Font("Segoe UI", 8f) };
            lb.Location = new Point(btn.Right + 14, 16);
            row.Controls.Add(lb);
            AddModelRow(row, 44);
        }

        void AddRowModel(ProviderEntry e, ModelInfo m)
        {
            var row = new Panel { BackColor = PANEL2, Margin = new Padding(0, 3, 0, 3), Padding = new Padding(12, 8, 12, 8) };

            var icon = new Panel { Size = new Size(30, 30), BackColor = PANEL2, Location = new Point(14, 9) };
            icon.Paint += (s, ev) => DrawGlyph(ev.Graphics, icon.ClientRectangle, e.Key, false, TEXT, MUTED);
            row.Controls.Add(icon);

            var nameLabel = new Label { Text = m.Label, AutoSize = true, ForeColor = TEXT, BackColor = PANEL2, Font = Semibold(9.5f), Location = new Point(54, 4) };
            var idLabel = new Label { Text = m.Id, AutoSize = true, ForeColor = MUTED, BackColor = PANEL2, Font = new Font("Segoe UI", 7.5f), Location = new Point(54, 26) };
            row.Controls.Add(nameLabel);
            row.Controls.Add(idLabel);

            var tierChip = new Label
            {
                Text = m.Tier.ToUpperInvariant(),
                AutoSize = true,
                Font = new Font("Segoe UI", 7.5f, FontStyle.Bold),
                Padding = new Padding(9, 5, 9, 5),
                ForeColor = m.Tier == "fast" ? FAST : (m.Tier == "heavy" ? HEAVY : BAL),
                BackColor = m.Tier == "fast" ? CHIP_FAST_BG : (m.Tier == "heavy" ? CHIP_HEAVY_BG : CHIP_BAL_BG)
            };
            var chipX = 54 + Math.Max(nameLabel.PreferredWidth + 14, idLabel.PreferredWidth + 14);
            tierChip.Location = new Point(chipX, 10);
            row.Controls.Add(tierChip);

            if (m.Source == "alias")
            {
                var alias = new Label { Text = "alias", AutoSize = true, ForeColor = MUTED, BackColor = PANEL2, Font = new Font("Segoe UI", 7.5f) };
                alias.Location = new Point(tierChip.Right + 10, 15);
                row.Controls.Add(alias);
            }

            var useBtn = Flat("Use", delegate { UseModel(e, m); });
            var useFlp = new FlowLayoutPanel
            {
                Dock = DockStyle.Right,
                FlowDirection = FlowDirection.TopDown,
                BackColor = PANEL2,
                WrapContents = false,
                AutoSize = true,
                AutoSizeMode = AutoSizeMode.GrowAndShrink
            };
            useBtn.Margin = new Padding(0, 10, 0, 0);
            useFlp.Controls.Add(useBtn);
            row.Controls.Add(useFlp);

            AddModelRow(row, 52);
        }

        void AddModelRow(Control c, int absoluteHeight)
        {
            _modelsTlp.RowCount++;
            if (absoluteHeight > 0)
            {
                _modelsTlp.RowStyles.Add(new RowStyle(SizeType.Absolute, absoluteHeight));
            }
            else
            {
                _modelsTlp.RowStyles.Add(new RowStyle(SizeType.AutoSize));
            }
            _modelsTlp.Controls.Add(c, 0, _modelsTlp.RowCount - 1);
            c.Dock = DockStyle.Fill;
            c.Margin = new Padding(0);
            c.Padding = new Padding(0);
        }

        void UseModel(ProviderEntry e, ModelInfo m)
        {
            if (e.Kind == "desktop") return;
            _selectedModel = m;
            _selectedProviderKey = e.Key;
            var conf = ProviderConf(e.Key);
            var name = conf != null && conf.ContainsKey("name") ? Str(conf["name"]) : e.Key;
            _resultTier.Text = m.Tier.ToUpperInvariant();
            _resultTier.ForeColor = m.Tier == "fast" ? FAST : (m.Tier == "heavy" ? HEAVY : BAL);
            _resultTier.BackColor = m.Tier == "fast" ? CHIP_FAST_BG : (m.Tier == "heavy" ? CHIP_HEAVY_BG : CHIP_BAL_BG);
            _resultMain.Text = name + "  \u00b7  " + m.Label;
            _resultSub.Text = "Model dipilih manual (" + m.Id + "). Klik Run Selected untuk menjalankan.";
            _runBtn.Enabled = true;
        }

        string PrefProvider()
        {
            var ui = AsMap(_cfg.ContainsKey("ui") ? _cfg["ui"] : null);
            var pref = ui != null && ui.ContainsKey("preferred_provider") ? Str(ui["preferred_provider"]) : "";
            if (!string.IsNullOrEmpty(pref) && _states.ContainsKey(pref) && _states[pref].Done && !string.IsNullOrEmpty(_states[pref].CliPath))
                return pref;
            foreach (var k in new[] { "codex-cli", "commandcode", "claude-cli", "antigravity-cli", "gemini", "opencode", "custom" })
            {
                ProviderState s;
                if (_states.TryGetValue(k, out s) && s.Done && s.CliPath != null) return k;
            }
            var done = _states.FirstOrDefault(x => x.Value.Done && !string.IsNullOrEmpty(x.Value.CliPath));
            return done.Key;
        }

        // ========================================================== actions

        void Analyze()
        {
            var prompt = _taskBox.Text.Trim();
            if (prompt.Length == 0)
            {
                MessageBox.Show("Tulis task dulu.", "Task", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var r = RouteTask(prompt);

            string key;
            if (_selectedKey != "auto" && _entries.ContainsKey(_selectedKey))
            {
                var e = _entries[_selectedKey];
                if (e.Kind == "desktop" && e.CliKey != null) key = e.CliKey;
                else key = _selectedKey;
            }
            else key = PrefProvider();

            if (string.IsNullOrEmpty(key) || !_states.ContainsKey(key))
            {
                MessageBox.Show("Provider belum selesai dipindai - coba lagi.", "Provider", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }
            var st = _states[key];
            if (string.IsNullOrEmpty(st.CliPath))
            {
                MessageBox.Show("CLI " + _entries[key].Name + " tidak terdeteksi.", "Provider", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var model = ChooseModel(st.Models, r.Tier);
            if (model == null)
            {
                MessageBox.Show("Tidak ada model tersedia di " + _entries[key].Name + ".", "Model", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            _selectedModel = model;
            _selectedProviderKey = key;
            var chipColor = r.Tier == "fast" ? FAST : (r.Tier == "heavy" ? HEAVY : BAL);
            var chipBg = r.Tier == "fast" ? CHIP_FAST_BG : (r.Tier == "heavy" ? CHIP_HEAVY_BG : CHIP_BAL_BG);
            var conf = ProviderConf(key);
            var provName = conf != null && conf.ContainsKey("name") ? Str(conf["name"]) : key;
            _resultTier.Text = r.Tier.ToUpperInvariant();
            _resultTier.ForeColor = chipColor;
            _resultTier.BackColor = chipBg;
            _resultMain.Text = provName + "  \u00b7  " + model.Label;
            var why = string.Join(" \u00b7 ", r.Reasons.ToArray());
            _resultSub.Text = "Delegasi: " + r.Delegation + "   \u00b7   Score " + (r.Score >= 0 ? "+" : "") + r.Score
                + " (" + why + ")   \u00b7   " + model.Id;
            _runBtn.Enabled = true;
        }

        void RunSelected()
        {
            var prompt = _taskBox.Text.Trim();
            if (prompt.Length == 0) { MessageBox.Show("Tulis task dulu.", "Task", MessageBoxButtons.OK, MessageBoxIcon.Warning); return; }
            if (_selectedModel == null || string.IsNullOrEmpty(_selectedProviderKey))
            {
                Analyze();
                if (_selectedModel == null || string.IsNullOrEmpty(_selectedProviderKey)) return;
            }

            var key = _selectedProviderKey;
            var conf = ProviderConf(key);
            var modelId = _selectedModel.Id;
            var cliPath = _states[key].CliPath;
            if (string.IsNullOrEmpty(cliPath) || conf == null || !conf.ContainsKey("run"))
            {
                MessageBox.Show("Konfigurasi run tidak tersedia untuk provider ini.", "Run", MessageBoxButtons.OK, MessageBoxIcon.Warning);
                return;
            }

            var runConf = AsMap(conf["run"]);
            var args = new StringBuilder();
            foreach (var aObj in AsList(runConf["command"]))
            {
                var a = Str(aObj).Replace("{model}", modelId).Replace("{prompt}", Collapse(prompt));
                if (args.Length > 0) args.Append(' ');
                args.Append(QuoteArg(a));
            }

            var ui = AsMap(_cfg.ContainsKey("ui") ? _cfg["ui"] : null);
            bool confirm = ui == null || !ui.ContainsKey("confirm_before_run") || ToBool(ui["confirm_before_run"], true);
            if (confirm)
            {
                var detail = "Provider: " + _entries[key].Name +
                             "\nModel: " + _selectedModel.Label + " (" + modelId + ")" +
                             "\n\n" + cliPath + " " + args +
                             "\n\nJalankan di console baru?";
                if (MessageBox.Show(detail, "Run agent", MessageBoxButtons.OKCancel, MessageBoxIcon.Question) != DialogResult.OK)
                    return;
            }

            try
            {
                var psi = new ProcessStartInfo
                {
                    FileName = cliPath,
                    Arguments = args.ToString(),
                    UseShellExecute = true
                };
                Process.Start(psi);
            }
            catch (Exception ex)
            {
                MessageBox.Show("Run gagal: " + ex.Message, "Run", MessageBoxButtons.OK, MessageBoxIcon.Error);
            }
        }

        static string Collapse(string s)
        {
            return Regex.Replace(s, @"\s+", " ").Trim();
        }

        static string QuoteArg(string s)
        {
            if (string.IsNullOrEmpty(s)) return "\"\"";
            bool need = s.IndexOfAny(new[] { ' ', '\t', '"' }) >= 0;
            if (!need) return s;
            var sb = new StringBuilder();
            sb.Append('"');
            int backslashes = 0;
            foreach (var ch in s)
            {
                if (ch == '\\') { backslashes++; continue; }
                if (ch == '"')
                {
                    sb.Append('\\', backslashes * 2 + 1);
                    sb.Append('"');
                }
                else
                {
                    sb.Append('\\', backslashes);
                    sb.Append(ch);
                }
                backslashes = 0;
            }
            if (backslashes > 0) sb.Append('\\', backslashes * 2);
            sb.Append('"');
            return sb.ToString();
        }

        // ========================================================== settings

        void OpenSettings()
        {
            if (_settingsOpen) return;
            _settingsOpen = true;
            try
            {
                using (var dlg = new SettingsDialog(ConfigPath(), _json))
                {
                    dlg.ShowDialog(this);
                    if (dlg.Saved)
                    {
                        LoadConfig();
                        _states.Clear();
                        BuildEntries();
                        RefreshCards();
                        SelectEntry("auto");
                        DiscoverAll();
                    }
                }
            }
            finally { _settingsOpen = false; }
        }

        class SettingsDialog : Form
        {
            public bool Saved;
            readonly TextBox _editor = new TextBox();
            readonly JavaScriptSerializer _json;
            readonly string _configPath;
            readonly string _defaultJson;

            public SettingsDialog(string configPath, JavaScriptSerializer json)
            {
                _configPath = configPath;
                _json = json;
                _defaultJson = _json.Serialize(MainForm.DefaultConfig());

                Text = "ZwartFlow \u00b7 Settings";
                Size = new Size(860, 680);
                StartPosition = FormStartPosition.CenterParent;
                BackColor = BG_S();
                MinimumSize = new Size(700, 520);

                var header = new Panel { Dock = DockStyle.Top, Height = 64, BackColor = BG_S(), Padding = new Padding(18, 10, 18, 6) };
                var title = new Label { Text = "Provider & Model Discovery", AutoSize = true, ForeColor = FG_S(), Font = new Font("Segoe UI Semibold", 13, FontStyle.Bold), Location = new Point(18, 8) };
                var sub = new Label { Text = "Path CLI, discovery command, alias model, dan argumen run semua provider.", AutoSize = true, ForeColor = MUTED_S(), Location = new Point(18, 36) };
                header.Controls.Add(title);
                header.Controls.Add(sub);

                _editor.Multiline = true;
                _editor.ScrollBars = ScrollBars.Both;
                _editor.WordWrap = false;
                _editor.Font = new Font("Consolas", 9.5f);
                _editor.BackColor = PANEL_S();
                _editor.ForeColor = FG_S();
                _editor.BorderStyle = BorderStyle.FixedSingle;
                _editor.Dock = DockStyle.Fill;
                try { _editor.Text = File.Exists(_configPath) ? File.ReadAllText(_configPath) : _defaultJson; }
                catch { _editor.Text = ""; }

                var bottom = new Panel { Dock = DockStyle.Bottom, Height = 54, BackColor = BG_S(), Padding = new Padding(18, 10, 18, 10) };
                var validateBtn = FlatB("Validate", delegate { ValidateJson(); });
                var saveBtn = FlatAccentB("Save & Refresh", delegate { Save(); });
                var resetBtn = FlatB("Reset default", delegate { _editor.Text = _defaultJson; });
                var closeBtn = FlatB("Close", delegate { Close(); });
                closeBtn.Dock = DockStyle.Right;
                validateBtn.Dock = DockStyle.Left;
                saveBtn.Dock = DockStyle.Left;
                resetBtn.Dock = DockStyle.Left;
                bottom.Controls.Add(validateBtn);
                bottom.Controls.Add(saveBtn);
                bottom.Controls.Add(resetBtn);
                bottom.Controls.Add(closeBtn);
                saveBtn.Left = validateBtn.Right + 10;
                resetBtn.Left = saveBtn.Right + 10;

                Controls.Add(_editor);
                Controls.Add(header);
                Controls.Add(bottom);
            }

            static Color BG_S() { return Color.FromArgb(14, 16, 20); }
            static Color PANEL_S() { return Color.FromArgb(29, 34, 43); }
            static Color FG_S() { return Color.FromArgb(231, 234, 240); }
            static Color MUTED_S() { return Color.FromArgb(139, 149, 165); }

            void ValidateJson()
            {
                try
                {
                    _json.Deserialize<Dictionary<string, object>>(_editor.Text);
                    MessageBox.Show("JSON valid.", "Validate", MessageBoxButtons.OK, MessageBoxIcon.Information);
                }
                catch (Exception ex)
                {
                    MessageBox.Show("JSON invalid: " + ex.Message, "Validate", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }

            void Save()
            {
                try
                {
                    var data = _json.Deserialize<Dictionary<string, object>>(_editor.Text);
                    if (data == null)
                    {
                        MessageBox.Show("JSON invalid: kosong", "Save", MessageBoxButtons.OK, MessageBoxIcon.Error);
                        return;
                    }
                    File.WriteAllText(_configPath, _json.Serialize(data), new UTF8Encoding(false));
                    Saved = true;
                    Close();
                }
                catch (Exception ex)
                {
                    MessageBox.Show("Save gagal: " + ex.Message, "Save", MessageBoxButtons.OK, MessageBoxIcon.Error);
                }
            }
        }

        // ============================================================ helper UI

        static Font Semibold(float size)
        {
            return new Font("Segoe UI Semibold", size, FontStyle.Bold);
        }

        static Button Flat(string text, EventHandler onClick)
        {
            var b = new Button
            {
                Text = text,
                FlatStyle = FlatStyle.Flat,
                BackColor = PANEL2,
                ForeColor = TEXT,
                Font = new Font("Segoe UI", 8.75f),
                AutoSize = true,
                AutoSizeMode = AutoSizeMode.GrowAndShrink,
                Padding = new Padding(4),
                Cursor = Cursors.Hand,
                UseMnemonic = false
            };
            b.FlatAppearance.MouseOverBackColor = BORDER;
            b.FlatAppearance.BorderSize = 0;
            b.Click += onClick;
            return b;
        }

        static Button FlatAccent(string text, EventHandler onClick)
        {
            var b = Flat(text, onClick);
            b.BackColor = ACCENT;
            b.ForeColor = Color.White;
            b.Font = new Font("Segoe UI Semibold", 9, FontStyle.Bold);
            b.FlatAppearance.MouseOverBackColor = Color.FromArgb(61, 121, 231);
            return b;
        }

        static Button FlatB(string text, EventHandler onClick)
        {
            return Flat(text, onClick);
        }

        static Button FlatAccentB(string text, EventHandler onClick)
        {
            return FlatAccent(text, onClick);
        }

        static Label Chip(string text, Color fg, Color bg)
        {
            return new Label
            {
                Text = text,
                AutoSize = true,
                ForeColor = fg,
                BackColor = bg,
                Font = new Font("Segoe UI", 8.5f),
                Padding = new Padding(10, 5, 10, 5),
                Margin = new Padding(0)
            };
        }
    }
}
