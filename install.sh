#!/data/data/com.termux/files/usr/bin/bash

# Menyimpan lokasi file installer ini agar bisa otomatis dihapus setelah instalasi selesai
INSTALLER_FILE="$(realpath "$0" 2>/dev/null || echo "$0")"
BASE_DIR="$HOME/vortex-ai"
BIN_PATH="$PREFIX/bin/vortex"

# Jika belum bisa dipanggil dengan "vortex", daftarkan dulu lalu langsung jalankan
if [ "$1" != "--run-installer" ] && [ "$(basename "$0")" != "vortex" ]; then
    cp "$INSTALLER_FILE" "$BIN_PATH"
    chmod +x "$BIN_PATH"
fi

# Fungsi mengisi seluruh layar dengan background hijau dan teks tepat di tengah layar
draw_green_screen() {
    local msg="$1"
    # Aktifkan background hijau (\033[42m) dan teks putih tebal (\033[1;37m), lalu bersihkan layar
    printf "\033[42;1;37m\033[2J\033[H"
    # Sembunyikan kursor
    printf "\033[?25l"
    local rows=$(tput lines 2>/dev/null || echo 24)
    local cols=$(tput cols 2>/dev/null || echo 80)
    local r=$((rows / 2))
    local c=$(( (cols - ${#msg}) / 2 ))
    [ $c -lt 1 ] && c=1
    printf "\033[%d;%dH%s" "$r" "$c" "$msg"
}

# Jalankan instalasi paket & library di background sambil memutar / dan \ per detik
run_background_install() {
    mkdir -p "$BASE_DIR/workspace"
    pkg install python curl tmux figlet -y >/dev/null 2>&1
    pip install requests rich prompt_toolkit >/dev/null 2>&1

    # Merakit file utama main.py
    cat << 'VORTEX_MAIN_EOF' > "$BASE_DIR/main.py"
#!/data/data/com.termux/files/usr/bin/python
import os, sys, time, json, re, ast, math, uuid, base64, hashlib, shutil, socket, sqlite3, platform, subprocess, threading, urllib.parse, secrets, string, py_compile
from pathlib import Path
import requests
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich.markdown import Markdown

console = Console()
BASE_DIR = Path.home() / "vortex-ai"
WORKSPACE = BASE_DIR / "workspace"
DB_PATH = BASE_DIR / "vortex.db"
BASE_DIR.mkdir(parents=True, exist_ok=True)
WORKSPACE.mkdir(parents=True, exist_ok=True)

# ==================== 1. DATABASE & CUMULATIVE TIMER ====================
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, time TEXT, user TEXT, reply TEXT, model TEXT, step_time REAL, total_cumulative REAL)")
        conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, val TEXT)")
init_db()

def get_cfg(key, default):
    with sqlite3.connect(DB_PATH) as conn:
        row = conn.execute("SELECT val FROM config WHERE key=?", (key,)).fetchone()
        return json.loads(row[0]) if row else default

def set_cfg(key, val):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT OR REPLACE INTO config (key, val) VALUES (?,?)", (key, json.dumps(val)))

if get_cfg("active_model", "") in ("", "qwen-coder"):
    set_cfg("active_model", "chatgpt")

def add_cumulative_time(seconds_added):
    total = float(get_cfg("all_time_thinking_sec", 0.0)) + float(seconds_added)
    count = int(get_cfg("all_time_thinking_count", 0)) + 1
    set_cfg("all_time_thinking_sec", total)
    set_cfg("all_time_thinking_count", count)
    return total, count

def format_duration(sec):
    sec = float(sec)
    if sec < 60:
        return f"{sec:.1f} detik"
    mins = int(sec // 60)
    rem_sec = sec % 60
    if mins < 60:
        return f"{mins} menit {rem_sec:.1f} detik"
    hrs = int(mins // 60)
    rem_mins = mins % 60
    return f"{hrs} jam {rem_mins} menit {rem_sec:.1f} detik"

def save_chat(user, reply, model, step_t, cum_t):
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute("INSERT INTO history (time, user, reply, model, step_time, total_cumulative) VALUES (?,?,?,?,?,?)",
                     (time.strftime("%Y-%m-%d %H:%M:%S"), user, reply, model, round(step_t, 2), round(cum_t, 2)))

def get_chats(limit=6):
    with sqlite3.connect(DB_PATH) as conn:
        rows = conn.execute("SELECT time, user, reply, model, step_time, total_cumulative FROM history ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
    return list(reversed(rows))

# ==================== 2. REAL-TIME STEP & ACTION TIMER ====================
def run_step_with_timer(label, func, *args):
    stop_evt = threading.Event()
    elapsed = [0.0]

    def ticker():
        t0 = time.perf_counter()
        while not stop_evt.is_set():
            elapsed[0] = time.perf_counter() - t0
            sys.stdout.write(f"\r\033[1;33m[⏳] {label}... ({format_duration(elapsed[0])})\033[K\033[0m")
            sys.stdout.flush()
            time.sleep(0.1)

    t = threading.Thread(target=ticker, daemon=True)
    t.start()
    try:
        res = func(*args)
    finally:
        stop_evt.set()
        t.join()

    dur_str = format_duration(elapsed[0])
    log_line = f"{label} -> Selesai dalam {dur_str}"
    sys.stdout.write(f"\r\033[1;32m[✓] {log_line}\033[K\033[0m\n")
    sys.stdout.flush()
    return res, elapsed[0], log_line

# ==================== 3. COMPLETE FUNCTIONAL TOOLS ====================
def resolve_path(p):
    raw = str(p).strip()
    return Path(os.path.expanduser(raw)).resolve() if raw else WORKSPACE

def t_python_runner(arg="main.py"):
    p = resolve_path(arg)
    if not p.exists(): return f"File tidak ditemukan: {p}"
    r = subprocess.run([sys.executable, str(p)], capture_output=True, text=True, timeout=30)
    return (r.stdout + r.stderr).strip() or "[Selesai tanpa output]"

def t_code_writer(arg=""):
    parts = arg.split("|", 1)
    if len(parts) < 2: return "Format: (code_writer nama_file.py | isi_kode)"
    p = resolve_path(parts[0].strip())
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(parts[1].strip(), encoding="utf-8")
    return f"Kode disimpan ke {p} ({len(parts[1])} bytes)"

def t_code_reader(arg=""):
    p = resolve_path(arg)
    if not p.exists(): return f"File tidak ditemukan: {p}"
    lines = p.read_text(encoding="utf-8", errors="replace").splitlines()
    return "\n".join(f"{i+1:4d} | {l}" for i, l in enumerate(lines))

def t_code_debugger(arg=""):
    p = resolve_path(arg)
    if not p.exists(): return f"File tidak ditemukan: {p}"
    try:
        ast.parse(p.read_text(encoding="utf-8"), filename=p.name)
        return f"[OK] AST & Sintaks Python pada {p.name} 100% valid."
    except SyntaxError as e:
        return f"[BUG DITEMUKAN] Baris {e.lineno}: {e.msg}\nKode: {e.text}"

def t_syntax_checker(arg=""):
    p = resolve_path(arg)
    if not p.exists(): return f"File tidak ditemukan: {p}"
    try:
        py_compile.compile(str(p), doraise=True)
        return f"[VALID] {p.name} berhasil dikompilasi."
    except Exception as e:
        return f"[INVALID] {e}"

def t_code_analyzer(arg=""):
    p = resolve_path(arg)
    if not p.exists(): return f"File tidak ditemukan: {p}"
    txt = p.read_text(encoding="utf-8", errors="replace")
    lines = txt.splitlines()
    funcs = len(re.findall(r"^\s*def\s+\w+", txt, re.M))
    classes = len(re.findall(r"^\s*class\s+\w+", txt, re.M))
    return f"File: {p.name} | Total Baris: {len(lines)} | Fungsi: {funcs} | Class: {classes}"

def t_html_builder(arg="index.html"):
    p = resolve_path(arg or "index.html")
    p.write_text("<!DOCTYPE html><html><head><meta charset='utf-8'><title>Vortex App</title><link rel='stylesheet' href='style.css'></head><body><div class='box'><h1>VORTEX AI</h1><p>Created by vzxTeam</p></div><script src='app.js'></script></body></html>", encoding="utf-8")
    return f"HTML dibuat di: {p}"

def t_css_builder(arg="style.css"):
    p = resolve_path(arg or "style.css")
    p.write_text("body{background:#06080e;color:#00ffcc;font-family:monospace;display:flex;justify-content:center;align-items:center;height:100vh;margin:0}.box{border:2px solid #00ffcc;padding:30px;border-radius:10px;box-shadow:0 0 20px #00ffcc44;text-align:center}", encoding="utf-8")
    return f"CSS dibuat di: {p}"

def t_js_builder(arg="app.js"):
    p = resolve_path(arg or "app.js")
    p.write_text("console.log('Vortex Web App Ready!');", encoding="utf-8")
    return f"JS dibuat di: {p}"

def t_json_formatter(arg=""):
    p = resolve_path(arg)
    if p.exists():
        data = json.loads(p.read_text(encoding="utf-8"))
        out = json.dumps(data, indent=2)
        p.write_text(out, encoding="utf-8")
        return out
    return json.dumps(json.loads(arg), indent=2)

def t_project_creator(arg="my_project"):
    d = resolve_path(WORKSPACE / (arg.strip() or "my_project"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "main.py").write_text(f"print('Project {d.name} Running!')\n", encoding="utf-8")
    (d / "requirements.txt").write_text("requests\nrich\n", encoding="utf-8")
    (d / "README.md").write_text(f"# {d.name}\nGenerated by VORTEX AI.\n", encoding="utf-8")
    return f"Proyek lengkap dibuat di: {d}"

def t_app_builder(arg="my_cli"):
    name = arg.strip() or "my_cli"
    d = Path.home() / name
    d.mkdir(parents=True, exist_ok=True)
    app_py = d / "main.py"
    app_py.write_text(f"#!/data/data/com.termux/files/usr/bin/python\nimport sys\nprint('=== APLIKASI {name.upper()} AKTIF ===')\n", encoding="utf-8")
    os.chmod(app_py, 0o755)
    bin_p = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "bin" / name
    bin_p.write_text(f"#!/data/data/com.termux/files/usr/bin/bash\npython {app_py} \"$@\"\n", encoding="utf-8")
    os.chmod(bin_p, 0o755)
    return f"Aplikasi '{name}' berhasil dipasang ke sistem Termux! Ketik '{name}' di terminal."

def t_git_helper(arg="status"):
    r = subprocess.run(f"git {arg}", shell=True, capture_output=True, text=True)
    return (r.stdout + r.stderr).strip() or "Git selesai."

def t_dep_installer(arg=""):
    if not arg: return "Contoh: (dependency_installer pyfiglet)"
    r = subprocess.run([sys.executable, "-m", "pip", "install", arg.strip()], capture_output=True, text=True)
    return (r.stdout + r.stderr).strip()[-500:]

def t_terminal(arg=""):
    if not arg: return "Contoh: (terminal pkg list-installed)"
    r = subprocess.run(arg, shell=True, capture_output=True, text=True, timeout=45)
    return (r.stdout + r.stderr).strip() or "[Selesai]"

def t_root_shell(arg="id && whoami"):
    cmd = arg.strip() or "id && whoami"
    if shutil.which("tsu"):
        r = subprocess.run(f"tsu -c '{cmd}'", shell=True, capture_output=True, text=True, timeout=30)
        return (r.stdout + r.stderr).strip()
    if not shutil.which("proot"):
        subprocess.run("pkg install proot -y", shell=True)
    r = subprocess.run(f"proot -0 {cmd}", shell=True, capture_output=True, text=True, timeout=30)
    return "[PROOT ROOT ENVIRONMENT]\n" + ((r.stdout + r.stderr).strip() or "Selesai.")

def t_system_info(arg=""):
    model = subprocess.run("getprop ro.product.model", shell=True, capture_output=True, text=True).stdout.strip()
    ver = subprocess.run("getprop ro.build.version.release", shell=True, capture_output=True, text=True).stdout.strip()
    root_st = "Hardware Root (su)" if shutil.which("su") else "Virtual Root (proot -0)"
    return f"Device : {model} (Android {ver})\nKernel : {platform.system()} {platform.release()} ({platform.machine()})\nPython : {platform.python_version()}\nRoot   : {root_st}"

def t_storage_info(arg=""):
    u = shutil.disk_usage(Path.home())
    gb = 1024**3
    return f"Total: {u.total/gb:.2f} GB | Terpakai: {u.used/gb:.2f} GB ({u.used/u.total*100:.1f}%) | Sisa: {u.free/gb:.2f} GB"

def t_memory_info(arg=""):
    p = Path("/proc/meminfo")
    return "\n".join(p.read_text().splitlines()[:8]) if p.exists() else "Tidak dapat membaca /proc/meminfo"

def t_cpu_info(arg=""):
    return f"CPU Cores: {os.cpu_count()} | Arch: {platform.machine()}"

def t_process_monitor(arg=""):
    r = subprocess.run(["ps", "aux"], capture_output=True, text=True)
    return "\n".join((r.stdout or "").splitlines()[:20])

def t_network_status(arg=""):
    try:
        t0 = time.perf_counter()
        ip = socket.gethostbyname("one.one.one.one")
        return f"ONLINE | DNS: 1.1.1.1 ({ip}) | Latency: {(time.perf_counter()-t0)*1000:.1f} ms"
    except Exception as e:
        return f"OFFLINE: {e}"

def t_package_checker(arg=""):
    cmd = f"dpkg -s {arg}" if arg else "pkg list-installed"
    r = subprocess.run(cmd, shell=True, capture_output=True, text=True)
    return "\n".join((r.stdout + r.stderr).splitlines()[:25])

def t_file_manager(arg="."):
    p = resolve_path(arg)
    if not p.exists(): return f"Path tidak ditemukan: {p}"
    items = [f"{'[DIR] ' if x.is_dir() else '[FILE]'} {x.name:30s} ({x.stat().st_size if x.is_file() else '-'} B)" for x in sorted(p.iterdir())]
    return f"Direktori {p}:\n" + ("\n".join(items[:50]) if items else "(Kosong)")

def t_file_search(arg=""):
    if not arg: return "Contoh: (file_search .py)"
    found = [str(p.relative_to(Path.home())) for p in Path.home().rglob(f"*{arg}*") if ".git" not in str(p)][:30]
    return "\n".join(found) if found else "Tidak ditemukan."

def t_file_delete(arg=""):
    p = resolve_path(arg)
    if not p.exists(): return "Target tidak ditemukan."
    if p.is_dir(): shutil.rmtree(p)
    else: p.unlink()
    return f"Berhasil dihapus: {p}"

def t_archive_creator(arg=""):
    p = resolve_path(arg or WORKSPACE)
    out = shutil.make_archive(str(WORKSPACE / f"{p.name}_archive"), "zip", str(p))
    return f"Arsip ZIP berhasil dibuat: {out}"

def t_backup_creator(arg=""):
    p = resolve_path(arg)
    if not p.exists(): return "File tidak ditemukan."
    dst = p.with_suffix(p.suffix + f".{int(time.time())}.bak")
    shutil.copy2(p, dst)
    return f"Backup tersimpan di: {dst}"

def t_calculator(arg="25 * 4"):
    try:
        return f"{arg} = {eval(arg, {'__builtins__': None}, math.__dict__)}"
    except Exception as e:
        return f"Error: {e}"

def t_password_gen(arg="16"):
    n = max(8, min(64, int(arg or 16)))
    chars = string.ascii_letters + string.digits + "!@#$%^&*"
    return "".join(secrets.choice(chars) for _ in range(n))

def t_hash_gen(arg="vortex"):
    return f"SHA256: {hashlib.sha256(arg.encode()).hexdigest()}\nMD5   : {hashlib.md5(arg.encode()).hexdigest()}"

def t_base64_enc(arg="vortex"):
    return base64.b64encode(arg.encode()).decode()

def t_base64_dec(arg=""):
    return base64.b64decode(arg.encode()).decode("utf-8", errors="replace")

def t_uuid_gen(arg=""):
    return str(uuid.uuid4())

def t_url_checker(arg="https://github.com"):
    u = arg if arg.startswith("http") else "https://" + arg
    t0 = time.perf_counter()
    r = requests.head(u, timeout=10)
    return f"URL: {u} | HTTP {r.status_code} | Waktu: {(time.perf_counter()-t0)*1000:.1f} ms"

TOOLS = {
    "python_runner": ("CODING", "Jalankan file Python & tangkap outputnya", t_python_runner),
    "code_writer": ("CODING", "Tulis kode ke file (nama.py | kode)", t_code_writer),
    "code_reader": ("CODING", "Baca source code dengan nomor baris", t_code_reader),
    "code_debugger": ("CODING", "Cek AST bug & syntax error pada file Python", t_code_debugger),
    "syntax_checker": ("CODING", "Uji kompilasi file Python", t_syntax_checker),
    "code_analyzer": ("CODING", "Hitung jumlah baris, fungsi, dan class", t_code_analyzer),
    "html_builder": ("CODING", "Buat template halaman HTML5 Cyberpunk", t_html_builder),
    "css_builder": ("CODING", "Buat stylesheet CSS modern", t_css_builder),
    "javascript_builder": ("CODING", "Buat script JavaScript interaktif", t_js_builder),
    "json_formatter": ("CODING", "Rapikan struktur JSON", t_json_formatter),
    "project_creator": ("CODING", "Buat folder proyek lengkap di workspace", t_project_creator),
    "app_builder": ("CODING", "Buat aplikasi CLI & pasang ke bin Termux", t_app_builder),
    "git_helper": ("CODING", "Jalankan perintah Git (status/log/branch)", t_git_helper),
    "dependency_installer": ("CODING", "Instal library pip Python", t_dep_installer),
    "terminal": ("SYSTEM", "Jalankan perintah bash & tools luar bebas", t_terminal),
    "root_shell": ("SYSTEM", "Jalankan perintah mode Root (tsu / proot -0)", t_root_shell),
    "system_info": ("SYSTEM", "Info lengkap perangkat Android, Kernel & Root", t_system_info),
    "storage_info": ("SYSTEM", "Info kapasitas memori internal HP", t_storage_info),
    "memory_info": ("SYSTEM", "Info penggunaan RAM aktual (/proc/meminfo)", t_memory_info),
    "cpu_info": ("SYSTEM", "Info jumlah core & arsitektur prosesor", t_cpu_info),
    "process_monitor": ("SYSTEM", "Lihat daftar proses sistem yang berjalan", t_process_monitor),
    "network_status": ("SYSTEM", "Cek koneksi internet & ping DNS", t_network_status),
    "package_checker": ("SYSTEM", "Lihat daftar paket Termux terinstal", t_package_checker),
    "file_manager": ("FILES", "Lihat daftar file & ukuran di direktori", t_file_manager),
    "file_search": ("FILES", "Cari file di seluruh penyimpanan Termux", t_file_search),
    "file_delete": ("FILES", "Hapus file atau folder", t_file_delete),
    "archive_creator": ("FILES", "Kompres folder menjadi arsip ZIP", t_archive_creator),
    "backup_creator": ("FILES", "Buat file cadangan (.bak)", t_backup_creator),
    "calculator": ("UTILS", "Kalkulator matematika ilmiah", t_calculator),
    "password_generator": ("UTILS", "Generator password kriptografis aman", t_password_gen),
    "hash_generator": ("UTILS", "Buat hash SHA256 & MD5", t_hash_gen),
    "base64_encoder": ("UTILS", "Encode teks ke Base64", t_base64_enc),
    "base64_decoder": ("UTILS", "Decode Base64 ke teks asli", t_base64_dec),
    "uuid_generator": ("UTILS", "Generator kode unik UUID v4", t_uuid_gen),
    "url_checker": ("UTILS", "Cek status HTTP & kecepatan website", t_url_checker),
}

# ==================== 4. AI ENGINE & TIMED EXECUTION ====================
MODELS_CATALOG = {
    "1": ("chatgpt", "ChatGPT (OpenAI GPT-4o-mini) - Default Tanpa API Key"),
    "2": ("gemini", "Google Gemini Flash/Pro"),
    "3": ("llama", "Meta Llama 3.3 70B"),
}

SYSTEM_PROMPT = """Anda adalah VORTEX AI, Autonomous Full-Control Agent di Termux Android.
Anda memiliki akses penuh untuk membuat file, membuat aplikasi, menginstal tools luar, dan menjalankan mode root (proot -0 / tsu).

ATURAN EKSEKUSI:
1. Jika user hanya mengobrol atau bertanya, jawab langsung tanpa tag <file> atau <shell>.
2. Jika user meminta membuat aplikasi, kode, atau mengubah konfigurasi Termux, wajib gunakan tag:
<file path="~/nama_file">
isi kode lengkap
</file>
3. Jika user meminta instalasi tools, menjalankan script, atau kontrol Termux/Root, wajib gunakan tag:
<shell>
perintah bash satu baris
</shell>"""

def request_ai_backend(prompt_text):
    choice = get_cfg("active_model", "chatgpt")
    api_keys = get_cfg("api_keys", {})
    personal_key = api_keys.get(choice, "").strip()

    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    for _, u, rep, _, _, _ in get_chats(4):
        messages.append({"role": "user", "content": u})
        messages.append({"role": "assistant", "content": rep[:700]})
    messages.append({"role": "user", "content": prompt_text})

    if personal_key:
        try:
            if choice == "chatgpt":
                r = requests.post("https://api.openai.com/v1/chat/completions",
                    headers={"Authorization": f"Bearer {personal_key}"},
                    json={"model": "gpt-4o-mini", "messages": messages}, timeout=45)
                if r.status_code == 200:
                    return True, r.json()["choices"][0]["message"]["content"], "ChatGPT (Personal API)"
            elif choice == "gemini":
                url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={personal_key}"
                merged = "\n".join(f"{m['role']}: {m['content']}" for m in messages)
                r = requests.post(url, json={"contents": [{"parts": [{"text": merged}]}]}, timeout=45)
                if r.status_code == 200:
                    return True, r.json()["candidates"][0]["content"]["parts"][0]["text"], "Gemini (Personal API)"
            elif choice == "llama":
                r = requests.post("https://api.groq.com/openai/v1/chat/compl
