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
    p.write_text("<!DOCTYPE html><html><head><meta charset='utf-8'><title>Vortex App</title></head><body><h1>VORTEX AI</h1><p>Created by vzxTeam</p></body></html>", encoding="utf-8")
    return f"HTML dibuat di: {p}"

def t_project_creator(arg="my_project"):
    d = resolve_path(WORKSPACE / (arg.strip() or "my_project"))
    d.mkdir(parents=True, exist_ok=True)
    (d / "main.py").write_text(f"print('Project {d.name} Running!')\n", encoding="utf-8")
    (d / "README.md").write_text(f"# {d.name}\nGenerated by VORTEX AI.\n", encoding="utf-8")
    return f"Proyek lengkap dibuat di: {d}"

def t_app_builder(arg="my_cli"):
    name = arg.strip() or "my_cli"
    d = Path.home() / name
    d.mkdir(parents=True, exist_ok=True)
    app_py = d / "main.py"
    app_py.write_text(f"#!/data/data/com.termux/files/usr/bin/python\nprint('=== APLIKASI {name.upper()} AKTIF ===')\n", encoding="utf-8")
    os.chmod(app_py, 0o755)
    bin_p = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "bin" / name
    bin_p.write_text(f"#!/data/data/com.termux/files/usr/bin/bash\npython {app_py} \"$@\"\n", encoding="utf-8")
    os.chmod(bin_p, 0o755)
    return f"Aplikasi '{name}' berhasil dipasang! Ketik '{name}' di terminal."

def t_terminal(arg=""):
    if not arg: return "Contoh: (terminal pkg list-installed)"
    r = subprocess.run(arg, shell=True, capture_output=True, text=True, timeout=45)
    return (r.stdout + r.stderr).strip() or "[Selesai]"

def t_system_info(arg=""):
    model = subprocess.run("getprop ro.product.model", shell=True, capture_output=True, text=True).stdout.strip()
    ver = subprocess.run("getprop ro.build.version.release", shell=True, capture_output=True, text=True).stdout.strip()
    return f"Device : {model} (Android {ver})\nKernel : {platform.system()} {platform.release()} ({platform.machine()})\nPython : {platform.python_version()}"

def t_storage_info(arg=""):
    u = shutil.disk_usage(Path.home())
    gb = 1024**3
    return f"Total: {u.total/gb:.2f} GB | Terpakai: {u.used/gb:.2f} GB | Sisa: {u.free/gb:.2f} GB"

def t_memory_info(arg=""):
    p = Path("/proc/meminfo")
    return "\n".join(p.read_text().splitlines()[:8]) if p.exists() else "Info RAM tidak tersedia."

def t_network_status(arg=""):
    try:
        t0 = time.perf_counter()
        ip = socket.gethostbyname("one.one.one.one")
        return f"ONLINE | DNS: 1.1.1.1 ({ip}) | Latency: {(time.perf_counter()-t0)*1000:.1f} ms"
    except Exception as e:
        return f"OFFLINE: {e}"

def t_file_manager(arg="."):
    p = resolve_path(arg)
    if not p.exists(): return f"Path tidak ditemukan: {p}"
    items = [f"{'[DIR] ' if x.is_dir() else '[FILE]'} {x.name}" for x in sorted(p.iterdir())]
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

def t_calculator(arg="25 * 4"):
    try: return f"{arg} = {eval(arg, {'__builtins__': None}, math.__dict__)}"
    except Exception as e: return f"Error: {e}"

def t_password_gen(arg="16"):
    n = max(8, min(64, int(arg or 16)))
    return "".join(secrets.choice(string.ascii_letters + string.digits + "!@#$%^&*") for _ in range(n))

def t_hash_gen(arg="vortex"):
    return f"SHA256: {hashlib.sha256(arg.encode()).hexdigest()}\nMD5   : {hashlib.md5(arg.encode()).hexdigest()}"

TOOLS = {
    "python_runner": ("CODING", "Jalankan file Python & tangkap outputnya", t_python_runner),
    "code_writer": ("CODING", "Tulis kode ke file (nama.py | kode)", t_code_writer),
    "code_reader": ("CODING", "Baca source code dengan nomor baris", t_code_reader),
    "code_debugger": ("CODING", "Cek AST bug & syntax error pada file Python", t_code_debugger),
    "syntax_checker": ("CODING", "Uji kompilasi file Python", t_syntax_checker),
    "code_analyzer": ("CODING", "Hitung jumlah baris, fungsi, dan class", t_code_analyzer),
    "html_builder": ("CODING", "Buat template halaman HTML5", t_html_builder),
    "project_creator": ("CODING", "Buat folder proyek lengkap di workspace", t_project_creator),
    "app_builder": ("CODING", "Buat aplikasi CLI & pasang ke bin Termux", t_app_builder),
    "terminal": ("SYSTEM", "Jalankan perintah bash & tools luar bebas", t_terminal),
    "system_info": ("SYSTEM", "Info lengkap perangkat Android & Termux", t_system_info),
    "storage_info": ("SYSTEM", "Info kapasitas memori internal HP", t_storage_info),
    "memory_info": ("SYSTEM", "Info penggunaan RAM aktual", t_memory_info),
    "network_status": ("SYSTEM", "Cek koneksi internet & ping DNS", t_network_status),
    "file_manager": ("FILES", "Lihat daftar file di direktori", t_file_manager),
    "file_search": ("FILES", "Cari file di penyimpanan Termux", t_file_search),
    "file_delete": ("FILES", "Hapus file atau folder", t_file_delete),
    "calculator": ("UTILS", "Kalkulator matematika ilmiah", t_calculator),
    "password_generator": ("UTILS", "Generator password aman", t_password_gen),
    "hash_generator": ("UTILS", "Buat hash SHA256 & MD5", t_hash_gen),
}

MODELS_CATALOG = {
    "1": ("chatgpt", "ChatGPT (OpenAI GPT-4o-mini) - Default Tanpa API Key"),
    "2": ("gemini", "Google Gemini Flash/Pro"),
    "3": ("llama", "Meta Llama 3.3 70B"),
}

SYSTEM_PROMPT = """Anda adalah VORTEX AI, Autonomous Agent di Termux Android.
ATURAN EKSEKUSI:
1. Jika user hanya mengobrol atau bertanya, jawab langsung tanpa tag <file> atau <shell>.
2. Jika user meminta membuat aplikasi, kode, atau file, wajib gunakan tag:
<file path="~/nama_file">
isi kode lengkap
</file>
3. Jika user meminta instalasi tools atau menjalankan script, wajib gunakan tag:
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
                r = requests.post("https://api.groq.com/openai/v1/chat/completions",
                    headers={"Authorization": f"Bearer {personal_key}"},
                    json={"model": "llama-3.3-70b-versatile", "messages": messages}, timeout=45)
                if r.status_code == 200:
                    return True, r.json()["choices"][0]["message"]["content"], "Llama (Personal API)"
        except Exception as e:
            return False, f"API Key Pribadi Error: {e}", choice.upper()

    for mod in ["openai", "openai-fast"]:
        try:
            r = requests.post("https://text.pollinations.ai/", json={"messages": messages, "model": mod}, timeout=45)
            if r.status_code == 200 and r.text.strip() and '"status":40' not in r.text:
                return True, r.text.strip(), f"{choice.upper()}"
        except Exception:
            pass

    try:
        q = urllib.parse.quote(f"{SYSTEM_PROMPT}\nUser: {prompt_text}"[:1500])
        r2 = requests.get(f"https://text.pollinations.ai/{q}", timeout=45)
        if r2.status_code == 200 and r2.text.strip():
            return True, r2.text.strip(), f"{choice.upper()}"
    except Exception as e:
        return False, f"Gagal terhubung ke AI: {e}", choice.upper()
    return False, "Server sedang sibuk. Silakan coba lagi.", choice.upper()

def write_file_helper(fname, code):
    target = resolve_path(fname)
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(code, encoding="utf-8")
    if str(target).endswith((".py", ".sh")) or "/bin/" in str(target):
        os.chmod(target, 0o755)
    return str(target)

def run_shell_helper(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=45)
    return (p.stdout + p.stderr).strip() or "[Selesai dijalankan]"

def process_chat_with_timers(user_prompt):
    step_logs = []
    turn_total_sec = 0.0
    active_name = get_cfg("active_model", "chatgpt").upper()

    (ok, raw_reply, used_model), think_sec, think_log = run_step_with_timer(
        f"AI ({active_name}) sedang berpikir", request_ai_backend, user_prompt
    )
    step_logs.append(think_log)
    turn_total_sec += think_sec

    if not ok:
        add_cumulative_time(turn_total_sec)
        console.print(Panel(f"[bold red]{raw_reply}[/bold red]", title="ERROR", border_style="red"))
        return

    exec_outputs = []
    for m in re.finditer(r'<file\s+path=["\']([^"\']+)["\']\s*>(.*?)</file>', raw_reply, re.DOTALL | re.IGNORECASE):
        fname = m.group(1).strip()
        code = re.sub(r'^```\w*\n|\n```$', '', m.group(2).strip())
        try:
            saved_path, f_sec, f_log = run_step_with_timer(
                f"Aksi membuat/mengubah file '{fname}'", write_file_helper, fname, code
            )
            step_logs.append(f_log)
            turn_total_sec += f_sec
            exec_outputs.append(f"[✓] File disimpan: {saved_path}")
        except Exception as e:
            exec_outputs.append(f"[✗] Gagal membuat file {fname}: {e}")

    for m in re.finditer(r'<shell>(.*?)</shell>', raw_reply, re.DOTALL | re.IGNORECASE):
        cmds = re.sub(r'^```\w*\n|\n```$', '', m.group(1).strip()).splitlines()
        for cmd in cmds:
            cmd = cmd.strip()
            if not cmd or cmd.startswith("#"): continue
            try:
                cmd_out, s_sec, s_log = run_step_with_timer(
                    f"Aksi mengeksekusi '{cmd}'", run_shell_helper, cmd
                )
                step_logs.append(s_log)
                turn_total_sec += s_sec
                exec_outputs.append(f"$ {cmd}\n{cmd_out[:700]}")
            except Exception as e:
                exec_outputs.append(f"$ {cmd} -> ({e})")

    cum_sec, cum_cnt = add_cumulative_time(turn_total_sec)
    clean_reply = re.sub(r'<file\s+path=.*?>.*?</file>', '', raw_reply, flags=re.DOTALL | re.IGNORECASE)
    clean_reply = re.sub(r'<shell>.*?</shell>', '', clean_reply, flags=re.DOTALL | re.IGNORECASE)
    clean_reply = re.sub(r'</?reply>', '', clean_reply, flags=re.IGNORECASE).strip() or "Selesai dieksekusi."

    console.print(Panel(Markdown(clean_reply), title=f"[bold bright_green]{used_model}[/bold bright_green]", border_style="bright_green"))
    if exec_outputs:
        console.print(Panel("\n\n".join(exec_outputs), title="[bold bright_cyan]HASIL EKSEKUSI AKSI[/bold bright_cyan]", border_style="cyan"))

    timer_report = "\n".join(f"• {l}" for l in step_logs) + (
        f"\n────────────────────────────────────────────────────────\n"
        f"⏱️  [bold yellow]Total Waktu Giliran Ini :[/bold yellow] {format_duration(turn_total_sec)}\n"
        f"🧠 [bold bright_magenta]Total Akumulasi Mikir & Aksi (Sejak Pertama Kali / {cum_cnt}x Proses) :[/bold bright_magenta] [bold bright_green]{format_duration(cum_sec)}[/bold bright_green]"
    )
    console.print(Panel(timer_report, title="[bold yellow]STATISTIK WAKTU PEMIKIRAN & AKSI AI[/bold yellow]", border_style="magenta"))
    save_chat(user_prompt, clean_reply, used_model, turn_total_sec, cum_sec)

def show_note():
    note_content = (
        "Note: untuk membuka lagi tools dengan mengetik \"vortex\" atau \"python main.py\". "
        "Tools ini dalam tahap pengembangan, jika ada bug laporkan ke nomor ini:\n\n"
        "[bold bright_blue][link=https://wa.me/628987566890]628987566890[/link][/bold bright_blue]\n"
        "[bold bright_blue][link=https://wa.me/6289664210902]6289664210902[/link][/bold bright_blue]\n\n"
        "Ketuk nomor jika ingin melaporkan bug\n\n"
        "[bold italic]Created by vzxTeam[/bold italic]"
    )
    console.print(Panel(note_content, title="[bold bright_cyan]NOTE[/bold bright_cyan]", border_style="bright_cyan"))

def show_dashboard():
    os.system("clear")
    active = get_cfg("active_model", "chatgpt").upper()
    cum_sec = float(get_cfg("all_time_thinking_sec", 0.0))
    cum_cnt = int(get_cfg("all_time_thinking_count", 0))
    console.print(Panel(
        "[bold bright_cyan]██╗   ██╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗     █████╗ ██╗\n"
        "██║   ██║██╔═══██╗██╔══██╗╚══██╔══╝██╔════╝╚██╗██╔╝    ██╔══██╗██║\n"
        "╚██╗ ██╔╝██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝     ███████║██║\n"
        " ╚████╔╝ ╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗    ██║  ██║██║\n"
        "  ╚═══╝   ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚══════╝╚═╝  ╚═╝    ╚═╝  ╚═╝╚═╝[/bold bright_cyan]",
        subtitle="[bold italic]Created by vzxTeam[/bold italic]", border_style="bright_cyan"
    ))
    tbl = Table(show_header=False, box=None, expand=True)
    tbl.add_column("K", style="bold bright_green", width=20)
    tbl.add_column("V", style="white")
    tbl.add_row("ACTIVE AI", f"[bold bright_cyan]{active}[/bold bright_cyan]")
    tbl.add_row("TOTAL WAKTU MIKIR", f"[bold yellow]{format_duration(cum_sec)}[/bold yellow] ({cum_cnt}x pemikiran/aksi)")
    tbl.add_row("TOOLS TERSEDIA", f"[bold green]{len(TOOLS)} Functional Tools[/bold green] (Ketik [bold cyan]tools[/bold cyan] atau [bold c
