#!/data/data/com.termux/files/usr/bin/python
import os, sys, time, json, re, ast, math, uuid, base64, hashlib
import shutil, socket, sqlite3, platform, subprocess, threading
import urllib.parse, secrets, string, py_compile
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

with sqlite3.connect(DB_PATH) as conn:
    conn.execute("CREATE TABLE IF NOT EXISTS history (id INTEGER PRIMARY KEY, time TEXT, user TEXT, reply TEXT, model TEXT, step_time REAL, total_cumulative REAL)")
    conn.execute("CREATE TABLE IF NOT EXISTS config (key TEXT PRIMARY KEY, val TEXT)")

def get_cfg(k, d):
    with sqlite3.connect(DB_PATH) as c:
        r = c.execute("SELECT val FROM config WHERE key=?", (k,)).fetchone()
        return json.loads(r[0]) if r else d

def set_cfg(k, v):
    with sqlite3.connect(DB_PATH) as c:
        c.execute("INSERT OR REPLACE INTO config (key, val) VALUES (?,?)", (k, json.dumps(v)))

if get_cfg("active_model", "") in ("", "qwen-coder"):
    set_cfg("active_model", "chatgpt")

def add_cum_time(sec):
    tot = float(get_cfg("all_sec", 0.0)) + float(sec)
    cnt = int(get_cfg("all_cnt", 0)) + 1
    set_cfg("all_sec", tot)
    set_cfg("all_cnt", cnt)
    return tot, cnt

def fmt_dur(s):
    s = float(s)
    if s < 60: return f"{s:.1f} detik"
    m, rs = int(s // 60), s % 60
    if m < 60: return f"{m} menit {rs:.1f} detik"
    return f"{m//60} jam {m%60} menit {rs:.1f} detik"

def save_chat(u, r, m, st, ct):
    with sqlite3.connect(DB_PATH) as c:
        c.execute("INSERT INTO history (time,user,reply,model,step_time,total_cumulative) VALUES (?,?,?,?,?,?)",
                  (time.strftime("%Y-%m-%d %H:%M:%S"), u, r, m, round(st, 2), round(ct, 2)))

def get_chats(lim=5):
    with sqlite3.connect(DB_PATH) as c:
        rows = c.execute("SELECT time,user,reply,model,step_time,total_cumulative FROM history ORDER BY id DESC LIMIT ?", (lim,)).fetchall()
    return list(reversed(rows))

def run_timer(label, fn, *args):
    ev = threading.Event()
    el = [0.0]
    def tick():
        t0 = time.perf_counter()
        while not ev.is_set():
            el[0] = time.perf_counter() - t0
            sys.stdout.write(f"\r\033[1;33m[⏳] {label}... ({fmt_dur(el[0])})\033[K\033[0m")
            sys.stdout.flush()
            time.sleep(0.1)
    t = threading.Thread(target=tick, daemon=True)
    t.start()
    try: res = fn(*args)
    finally: ev.set(); t.join()
    log = f"{label} -> Selesai dalam {fmt_dur(el[0])}"
    sys.stdout.write(f"\r\033[1;32m[✓] {log}\033[K\033[0m\n")
    sys.stdout.flush()
    return res, el[0], log

def rpath(p):
    s = str(p).strip()
    return Path(os.path.expanduser(s)).resolve() if s else WORKSPACE

def run_sh(cmd):
    p = subprocess.run(cmd, shell=True, capture_output=True, text=True, timeout=45)
    return (p.stdout + p.stderr).strip() or "[Selesai]"

def t_py(a="main.py"):
    p = rpath(a)
    return run_sh(f"python '{p}'") if p.exists() else f"Tidak ada: {p}"

def t_write(a=""):
    pts = a.split("|", 1)
    if len(pts) < 2: return "Format: (code_writer file.py | kode)"
    p = rpath(pts[0]); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(pts[1].strip(), encoding="utf-8")
    return f"Disimpan: {p}"

def t_read(a=""):
    p = rpath(a)
    if not p.exists(): return "File tidak ditemukan."
    return "\n".join(f"{i+1:3d} | {l}" for i, l in enumerate(p.read_text(errors="replace").splitlines()))

def t_debug(a=""):
    p = rpath(a)
    if not p.exists(): return "File tidak ditemukan."
    try: ast.parse(p.read_text()); return f"[OK] Sintaks {p.name} valid."
    except SyntaxError as e: return f"[BUG] Baris {e.lineno}: {e.msg}"

def t_app(a="my_app"):
    n = a.strip() or "my_app"
    bp = Path(os.environ.get("PREFIX", "/data/data/com.termux/files/usr")) / "bin" / n
    bp.write_text(f"#!/data/data/com.termux/files/usr/bin/python\nprint('=== {n.upper()} AKTIF ===')\n")
    os.chmod(bp, 0o755)
    return f"Aplikasi '{n}' terpasang! Ketik '{n}' di Termux."

def t_sys(a=""):
    m = run_sh("getprop ro.product.model")
    v = run_sh("getprop ro.build.version.release")
    return f"Device: {m} (Android {v})\nKernel: {platform.release()} ({platform.machine()})\nPython: {platform.python_version()}"

def t_store(a=""):
    u = shutil.disk_usage(Path.home()); g = 1024**3
    return f"Total: {u.total/g:.1f}GB | Terpakai: {u.used/g:.1f}GB | Sisa: {u.free/g:.1f}GB"

def t_files(a="."):
    p = rpath(a)
    if not p.exists(): return "Tidak ditemukan."
    return "\n".join(f"{'[D]' if x.is_dir() else '[F]'} {x.name}" for x in sorted(p.iterdir())[:50])

def t_calc(a="25*4"):
    try: return f"{a} = {eval(a, {'__builtins__': None}, math.__dict__)}"
    except Exception as e: return str(e)

TOOLS = {
    "python_runner": ("CODING", "Jalankan file Python", t_py),
    "code_writer": ("CODING", "Tulis kode ke file (nama|isi)", t_write),
    "code_reader": ("CODING", "Baca isi kode file", t_read),
    "code_debugger": ("CODING", "Cek bug sintaks Python", t_debug),
    "app_builder": ("CODING", "Buat aplikasi CLI ke bin Termux", t_app),
    "terminal": ("SYSTEM", "Jalankan perintah bash & tools luar", run_sh),
    "system_info": ("SYSTEM", "Info HP Android & Termux", t_sys),
    "storage_info": ("SYSTEM", "Cek sisa penyimpanan HP", t_store),
    "file_manager": ("FILES", "Lihat daftar file direktori", t_files),
    "calculator": ("UTILS", "Kalkulator matematika ilmiah", t_calc),
}

MODELS = {
    "1": ("chatgpt", "ChatGPT (GPT-4o-mini) - Default Tanpa API Key"),
    "2": ("gemini", "Google Gemini Flash/Pro"),
    "3": ("llama", "Meta Llama 3.3 70B"),
}

SYS_PROMPT = """Anda adalah VORTEX AI, Agen Penuh Termux Android.
1. Jika hanya ngobrol, jawab langsung.
2. Jika diminta membuat file/aplikasi, gunakan:
<file path="~/nama_file">
isi kode
</file>
3. Jika diminta instal tools/jalankan perintah terminal, gunakan:
<shell>
perintah bash
</shell>"""

def ask_ai(prompt):
    ch = get_cfg("active_model", "chatgpt")
    key = get_cfg("api_keys", {}).get(ch, "").strip()
    msgs = [{"role": "system", "content": SYS_PROMPT}]
    for _, u, r, _, _, _ in get_chats(3):
        msgs.append({"role": "user", "content": u})
        msgs.append({"role": "assistant", "content": r[:600]})
    msgs.append({"role": "user", "content": prompt})

    if key:
        try:
            if ch == "chatgpt":
                r = requests.post("https://api.openai.com/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={"model": "gpt-4o-mini", "messages": msgs}, timeout=40)
                if r.status_code == 200: return True, r.json()["choices"][0]["message"]["content"], "ChatGPT (API)"
            elif ch == "gemini":
                u = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-1.5-flash:generateContent?key={key}"
                txt = "\n".join(f"{m['role']}: {m['content']}" for m in msgs)
                r = requests.post(u, json={"contents": [{"parts": [{"text": txt}]}]}, timeout=40)
                if r.status_code == 200: return True, r.json()["candidates"][0]["content"]["parts"][0]["text"], "Gemini (API)"
            elif ch == "llama":
                r = requests.post("https://api.groq.com/openai/v1/chat/completions", headers={"Authorization": f"Bearer {key}"}, json={"model": "llama-3.3-70b-versatile", "messages": msgs}, timeout=40)
                if r.status_code == 200: return True, r.json()["choices"][0]["message"]["content"], "Llama (API)"
        except Exception as e:
            return False, f"API Error: {e}", ch.upper()

    for m in ["openai", "openai-fast"]:
        try:
            r = requests.post("https://text.pollinations.ai/", json={"messages": msgs, "model": m}, timeout=40)
            if r.status_code == 200 and r.text.strip() and '"status":40' not in r.text:
                return True, r.text.strip(), ch.upper()
        except Exception: pass

    try:
        q = urllib.parse.quote(f"{SYS_PROMPT}\nUser: {prompt}"[:1400])
        r2 = requests.get(f"https://text.pollinations.ai/{q}", timeout=40)
        if r2.status_code == 200 and r2.text.strip(): return True, r2.text.strip(), ch.upper()
    except Exception as e:
        return False, f"Gagal terhubung: {e}", ch.upper()
    return False, "Server sibuk, coba lagi.", ch.upper()

def save_f(fn, code):
    p = rpath(fn); p.parent.mkdir(parents=True, exist_ok=True)
    p.write_text(code, encoding="utf-8"); os.chmod(p, 0o755)
    return str(p)

def handle_chat(u):
    logs, outs, turn_t = [], [], 0.0
    act = get_cfg("active_model", "chatgpt").upper()
    (ok, raw, mod), ts, tl = run_timer(f"AI ({act}) sedang berpikir", ask_ai, u)
    logs.append(tl); turn_t += ts
    if not ok:
        add_cum_time(turn_t)
        console.print(Panel(f"[red]{raw}[/red]", title="ERROR", border_style="red")); return

    for m in re.finditer(r'<file\s+path=["\']([^"\']+)["\']\s*>(.*?)</file>', raw, re.S | re.I):
        fn, cd = m.group(1).strip(), re.sub(r'^```\w*\n|\n```$', '', m.group(2).strip())
        sp, fs, fl = run_timer(f"Aksi membuat file '{fn}'", save_f, fn, cd)
        logs.append(fl); turn_t += fs; outs.append(f"[✓] File: {sp}")

    for m in re.finditer(r'<shell>(.*?)</shell>', raw, re.S | re.I):
        for cmd in re.sub(r'^```\w*\n|\n```$', '', m.group(1).strip()).splitlines():
            cmd = cmd.strip()
            if not cmd or cmd.startswith("#"): continue
            co, ss, sl = run_timer(f"Aksi eksekusi '{cmd}'", run_sh, cmd)
            logs.append(sl); turn_t += ss; outs.append(f"$ {cmd}\n{co[:600]}")

    cum_s, cum_c = add_cum_time(turn_t)
    clean = re.sub(r'<file.*?>.*?</file>|<shell>.*?</shell>|</?reply>', '', raw, flags=re.S | re.I).strip() or "Selesai."
    console.print(Panel(Markdown(clean), title=f"[bold green]{mod}[/bold green]", border_style="green"))
    if outs: console.print(Panel("\n\n".join(outs), title="HASIL EKSEKUSI", border_style="cyan"))
    rep = "\n".join(f"• {l}" for l in logs) + f"\n────────────────────────────────────\n⏱️ Giliran Ini: {fmt_dur(turn_t)}\n🧠 Total Akumulasi Mikir ({cum_c}x): [bold green]{fmt_dur(cum_s)}[/bold green]"
    console.print(Panel(rep, title="STATISTIK WAKTU MIKIR & AKSI", border_style="magenta"))
    save_chat(u, clean, mod, turn_t, cum_s)

def show_note():
    txt = (
        "Note: untuk membuka lagi tools dengan mengetik \"vortex\" atau \"python main.py\". "
        "Tools ini dalam tahap pengembangan, jika ada bug laporkan ke nomor ini:\n\n"
        "[bold bright_blue][link=https://wa.me/628987566890]628987566890[/link][/bold bright_blue]\n"
        "[bold bright_blue][link=https://wa.me/6289664210902]6289664210902[/link][/bold bright_blue]\n\n"
        "Ketuk nomor jika ingin melaporkan bug\n\n"
        "[bold italic]Created by vzxTeam[/bold italic]"
    )
    console.print(Panel(txt, title="[bold cyan]NOTE[/bold cyan]", border_style="cyan"))

def show_dash():
    os.system("clear")
    act = get_cfg("active_model", "chatgpt").upper()
    cs, cc = float(get_cfg("all_sec", 0.0)), int(get_cfg("all_cnt", 0))
    console.print(Panel(
        "[bold bright_cyan]██╗   ██╗ ██████╗ ██████╗ ████████╗███████╗██╗  ██╗\n"
        "╚██╗ ██╔╝██║   ██║██████╔╝   ██║   █████╗   ╚███╔╝\n"
        " ╚████╔╝ ╚██████╔╝██║  ██║   ██║   ███████╗██╔╝ ██╗[/bold bright_cyan]",
        subtitle="[bold italic]Created by vzxTeam[/bold italic]", border_style="bright_cyan"
    ))
    t = Table(show_header=False, box=None, expand=True)
    t.add_column("K", style="bold green", width=18); t.add_column("V", style="white")
    t.add_row("ACTIVE AI", f"[bold cyan]{act}[/bold cyan]")
    t.add_row("TOTAL MIKIR", f"[bold yellow]{fmt_dur(cs)}[/bold yellow] ({cc}x proses)")
    t.add_row("TOOLS READY", f"{len(TOOLS)} Tools (Panggil: [cyan](nama_tool)[/cyan])")
    t.add_row("COMMANDS", "[cyan]Note[/cyan] | [cyan]model[/cyan] | [cyan]apikey[/cyan] | [cyan]tools[/cyan] | [cyan]history[/cyan] | [cyan]clear[/cyan] | [cyan]exit[/cyan]")
    console.print(Panel(t, title="[bold green]VORTEX TELEMETRY[/bold green]", border_style="green"))

def main():
    show_dash()
    while True:
        try:
            u = input("\n\033[1;32mchat:\033[0m ").strip()
            if not u: continue
            low = u.lower()
            if low in ("exit", "quit", "keluar"): break
            if low in ("clear", "cls"): show_dash(); continue
            if low == "note": show_note(); continue
            if low == "tools":
                tb = Table(title="VORTEX TOOLS", expand=True)
                tb.add_column("Kat", style="magenta"); tb.add_column("Panggil", style="cyan"); tb.add_column("Fungsi")
                for k, (c, d, _) in TOOLS.items(): tb.add_row(c, f"({k})", d)
                console.print(tb); continue
            if low == "model":
                for k, (m, d) in MODELS.items(): console.print(f"[{k}] {m.upper()} - {d}")
                c = input("Pilih (1-3): ").strip()
                if c in MODELS: set_cfg("active_model", MODELS[c][0]); show_dash()
                continue
            if low == "apikey":
                act = get_cfg("active_model", "chatgpt"); ks = get_cfg("api_keys", {})
                k = input(f"API Key {act.upper()} (Enter=Gratis): ").strip()
                if k: ks[act] = k
                else: ks.pop(act, None)
                set_cfg("api_keys", ks); console.print("[green]Tersimpan![/green]"); continue
            if low == "history":
                rows = get_chats(10)
                txt = "\n\n".join(f"[{t}] {m} (Aksi: {fmt_dur(s)} | Total: {fmt_dur(c)})\n  chat: {usr}\n  AI: {r[:100]}..." for t, usr, r, m, s, c in rows)
                console.print(Panel(txt or "Kosong.", title="HISTORY", border_style="magenta")); continue
            tm = re.match(r"^\(([a-zA-Z0-9_\-]+)(?:\s+(.*))?\)$", u)
            if tm:
                tn, ta = tm.group(1), (tm.group(2) or "").strip("\"'")
                fn = TOOLS[tn][2] if tn in TOOLS else lambda x: run_sh(f"{tn} {x}".strip())
                out, ts, _ = run_timer(f"Menjalankan ({tn})", fn, ta)
                cs, _ = add_cum_time(ts)
                console.print(Panel(str(out), title=f"({tn})", subtitle=f"Waktu: {fmt_dur(ts)} | Total: {fmt_dur(cs)}", border_style="cyan"))
                continue
            handle_chat(u)
        except KeyboardInterrupt:
            console.print("\n[yellow]Ketik 'exit' untuk keluar.[/yellow]")

if __name__ == "__main__":
    main()
        
