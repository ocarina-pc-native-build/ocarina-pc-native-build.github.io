"""Ocarina Reborn Alpha launcher: alpha notice, activation, game files (find .nup, build), play, logs, debug package.

Started by OcarinaReborn.exe as <install>/python/pythonw.exe <install>/launcher/launcher.py. Everything the player
creates lives in %LOCALAPPDATA%\\Ocarina Reborn (Config, Logs, CrashDumps, ShaderDumps, Reports, PrepareLogs,
license.dat) and the game folder the player picks; the install folder is never written.
The game is built by Hookshot's pipeline (ocarina_prepare.py, <install>/engine, GPL-3.0).
"""
import datetime
import json
import os
import platform
import queue
import shutil
import subprocess
import sys
import threading
import time
import tkinter as tk
import zipfile
from pathlib import Path
from tkinter import filedialog, messagebox, ttk, colorchooser, simpledialog

sys.path.insert(0, str(Path(__file__).resolve().parent))
import license as lic  # noqa: E402
from build_screen import BuildScreen  # noqa: E402
import game_settings  # noqa: E402
import save_manager as sm  # noqa: E402
import fairy  # noqa: E402
import enemy_health  # noqa: E402
import ui  # noqa: E402
import advisor  # noqa: E402
import performance  # noqa: E402
import diagnostics  # noqa: E402
import debug_package as debug_export  # noqa: E402
import trace_capture  # noqa: E402
import mods_manager  # noqa: E402
import classic_voices  # noqa: E402
import tunic_colors  # noqa: E402
import amiibo  # noqa: E402
import gamepad  # noqa: E402

INSTALL = Path(__file__).resolve().parent.parent
ASSETS = Path(__file__).resolve().parent / 'assets'
INFO = json.loads((INSTALL / 'build-info.json').read_text())
PUBLIC_KEY = (INSTALL / 'data' / 'license-public.hex').read_text().strip()
APP = Path(os.environ.get('LOCALAPPDATA', str(Path.home()))) / 'Ocarina Reborn'
DIRS = {k: APP / k for k in ('Config', 'Logs', 'CrashDumps', 'ShaderDumps', 'Reports', 'PrepareLogs')}
for d in DIRS.values():
    d.mkdir(parents=True, exist_ok=True)
LICENSE = APP / 'license.dat'
SETTINGS = DIRS['Config'] / 'settings.json'
STATE = DIRS['Config'] / 'build-state.json'   # a build in progress: its settings, removed when it completes
NOW = datetime.datetime.now().strftime('%Y-%m-%d-%H%M%S')
LOG = DIRS['Logs'] / f'ocarina-reborn-{NOW}.log'
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
NEED_GB = 45
AUTO = 'Auto'   # Hookshot picks the compiler count by CPU threads and free memory (nx2/build.py)

BG, PANEL, PANEL2, LINE = '#060d22', '#0b1834', '#10224a', '#1d3a74'
CYAN, CYAN_MID, CYAN_DIM = '#00e5ff', '#0aa8e8', '#0a5a9c'   # the glowing edges (as the game's F1 HUD)
BLUE, BLUE_HI, TEXT, SUB, GOLD, RED = '#1f6fe0', '#2f8cff', '#eef4ff', '#93acd9', '#f4c430', '#ff8a80'
# All 16 languages the game has (engine host/nn_applet.c, nx2/make_game.py LANGUAGES). HOS_LANGUAGE from here overrides
# language.txt, so a language missing in this list could not be chosen at all (pt-BR: Discord, 1.0.0).
LANGS = [('de', 'Deutsch'), ('en-US', 'English (US)'), ('en-GB', 'English (UK)'), ('fr', 'Français'),
         ('fr-CA', 'Français (Canada)'), ('it', 'Italiano'), ('es', 'Español'), ('es-419', 'Español (Latinoamérica)'),
         ('pt-BR', 'Português (Brasil)'), ('nl', 'Nederlands'), ('pl', 'Polski'), ('ru', 'Русский'), ('ja', '日本語'),
         ('ko', '한국어'), ('zh-Hans', '简体中文'), ('zh-Hant', '繁體中文')]


UI_LANG = ['de']   # the launcher's language: settings.json "ui_language", else Windows' language


def T(de, en):
    return de if UI_LANG[0] == 'de' else en


def audio_devices():
    """the waveOut output devices (Hookshot's HOS_AUDIO_DEVICE numbers), in order"""
    import ctypes

    class Caps(ctypes.Structure):
        _fields_ = [('mid', ctypes.c_ushort), ('pid', ctypes.c_ushort), ('ver', ctypes.c_uint), ('name', ctypes.c_wchar * 32),
                    ('formats', ctypes.c_uint), ('channels', ctypes.c_ushort), ('r', ctypes.c_ushort), ('support', ctypes.c_uint)]
    out = []
    try:
        w = ctypes.windll.winmm
        for i in range(w.waveOutGetNumDevs()):
            c = Caps()
            if w.waveOutGetDevCapsW(i, ctypes.byref(c), ctypes.sizeof(c)) == 0:
                out.append(c.name)
    except (OSError, AttributeError):
        pass
    return out


class Music:
    """assets/music.wav looped quietly through Windows' PlaySound (winmm): plain PCM, so it needs no codec. (It was
    music.mp3 through MCI, which some PCs cannot open: no music there.) The quiet level is in the file itself; muted by
    the button in the header, the choice is kept"""
    SND_ASYNC, SND_NODEFAULT, SND_LOOP, SND_FILENAME = 0x1, 0x2, 0x8, 0x20000

    def __init__(self):
        self.ok = False
        self.file = ASSETS / 'music.wav'
        if not self.file.is_file():
            return log('music: assets/music.wav is missing')
        try:
            import ctypes
            self.play_sound = ctypes.windll.winmm.PlaySoundW
            self.play_sound.argtypes = [ctypes.c_wchar_p, ctypes.c_void_p, ctypes.c_uint]
            self.ok = True
        except (OSError, AttributeError) as e:
            log(f'music: no PlaySound ({e})')

    def play(self):
        if self.ok:
            r = self.play_sound(str(self.file), None, self.SND_ASYNC | self.SND_LOOP | self.SND_FILENAME | self.SND_NODEFAULT)
            log(f'music: {"playing" if r else "Windows could not play music.wav"}')

    def stop(self):
        if self.ok:
            self.play_sound(None, None, 0)

    def close(self):
        self.stop()


def log(msg):
    with open(LOG, 'a', encoding='utf-8') as f:
        f.write(f'[{datetime.datetime.now():%H:%M:%S}] {msg}\n')


def system_info():
    lines = [f'Windows: {platform.platform()}', f'CPU: {platform.processor()} ({os.cpu_count()} threads)']
    try:
        import ctypes

        class MS(ctypes.Structure):
            _fields_ = [('l', ctypes.c_ulong), ('load', ctypes.c_ulong), ('total', ctypes.c_ulonglong),
                        ('avail', ctypes.c_ulonglong), ('a', ctypes.c_ulonglong), ('b', ctypes.c_ulonglong),
                        ('c', ctypes.c_ulonglong), ('d', ctypes.c_ulonglong), ('e', ctypes.c_ulonglong)]
        m = MS()
        m.l = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        lines.append(f'RAM: {m.total / 2**30:.1f} GB')
    except (OSError, AttributeError):
        pass
    try:   # the GPU names Windows knows; the Vulkan device, driver and features are in the game log (vk: lines)
        out = subprocess.run(['powershell', '-NoProfile', '-Command',
                              'Get-CimInstance Win32_VideoController | ForEach-Object { $_.Name + " | driver " + $_.DriverVersion }'],
                             capture_output=True, text=True, timeout=20, creationflags=NO_WINDOW).stdout.strip()
        lines += [f'Display adapter (Windows): {l}' for l in out.splitlines() if l.strip()]   # (the game's own GPU: its log)
    except (OSError, subprocess.SubprocessError):
        pass
    return lines



def display_info():
    """the primary display's mode (the game opens on it): resolution and refresh rate, as Windows reports them"""
    try:
        import ctypes
        from ctypes import wintypes

        class DEVMODE(ctypes.Structure):
            _fields_ = [('name', ctypes.c_wchar * 32), ('spec', wintypes.WORD), ('drv', wintypes.WORD), ('size', wintypes.WORD),
                        ('extra', wintypes.WORD), ('fields', wintypes.DWORD), ('pos', ctypes.c_long * 2), ('orient', wintypes.DWORD),
                        ('fixed', wintypes.DWORD), ('color', ctypes.c_short), ('duplex', ctypes.c_short), ('yres', ctypes.c_short),
                        ('tt', ctypes.c_short), ('collate', ctypes.c_short), ('form', ctypes.c_wchar * 32), ('logpix', wintypes.WORD),
                        ('bpp', wintypes.DWORD), ('w', wintypes.DWORD), ('h', wintypes.DWORD), ('flags', wintypes.DWORD),
                        ('hz', wintypes.DWORD)]
        dm = DEVMODE()
        dm.size = ctypes.sizeof(DEVMODE)
        if ctypes.windll.user32.EnumDisplaySettingsW(None, -1, ctypes.byref(dm)):   # ENUM_CURRENT_SETTINGS
            return f'{dm.w}x{dm.h} @ {dm.hz} Hz'
    except (OSError, AttributeError, ValueError):
        pass
    return 'unknown'


SESSION_KEEP = ('[perf]', '[Performance Warning]', 'VRAM full', 'over budget', '[HDR]', '[OcarinaReborn/GFX]', 'swapchain ',
                'allocation fail', 'import fail', 'translation fail', 'rejected', 'device lost', 'DEVICE_LOST',
                'GPU queue submission failed')


def session_from_game_log(game):
    """the game's own performance lines of the last run, for the launcher's session log: the Vulkan GPU it renders on, its
    swapchains, the [perf] summaries (every 5 s), the warnings and memory/shader failures. Real renderer values only"""
    from collections import deque
    f = Path(game) / 'ocarina_reborn_log.txt'
    first, tail, gpu, kept = [], deque(maxlen=1200), None, 0
    try:
        # Long sessions can produce hundreds of MB. Keep the same first/last
        # evidence without loading and splitting the entire log in RAM.
        with f.open(encoding='utf-8', errors='replace') as stream:
            for line in stream:
                line = line.rstrip('\r\n')
                if gpu is None and ', Vulkan ' in line and 'vk: ' in line and 'device ' not in line:
                    gpu = line.split('vk: ', 1)[1].split(', Vulkan ')[0]
                if (any(k in line for k in SESSION_KEEP) or performance.HOST_MEMORY_ERROR.search(line) or
                        performance.GPU_SUBMIT_ERROR.search(line) or performance.CACHE_PIPELINE.search(line) or
                        performance.CACHE_PROGRAM.search(line)):
                    line = line.split('] ', 1)[-1] if line.startswith('[hos') else line
                    kept += 1
                    if kept <= 300:
                        first.append(line)
                    else:
                        tail.append(line)
    except OSError as e:
        return [f'game log not read: {e}']
    head = [f'Active GPU (Vulkan): {gpu or "not in the game log"}']
    omitted = [f'... {kept - 1500} lines left out (in the game log) ...'] if kept > 1500 else []
    return head + first + omitted + list(tail)


def game_exe(game):
    """the game's exe: ocarina_reborn.exe (the engine's build names it so), older names in a folder built before"""
    for name in ('ocarina_reborn.exe', 'OcarinaReborn-Game.exe', 'hookshot.exe'):   # (newest first: folders built before)
        if (Path(game) / name).is_file():
            return Path(game) / name
    return Path(game) / 'ocarina_reborn.exe'


def backup_root():
    r"""where backups go: the folder the player picked (settings.json "backup_dir"), else %LOCALAPPDATA%\Ocarina Reborn\Backups"""
    s = settings()
    return Path(s['backup_dir']) if s.get('backup_dir') else APP / 'Backups'


def backup_saves(game, why):
    r"""a copy of the game's saves (<game>/user/save) in %LOCALAPPDATA%\Ocarina Reborn\SaveBackups\<time>-<why>; the newest
    10 are kept. A build or update never touches the saves, this is for safety"""
    kind = {'before-build': 'Before-Update', 'before-import': 'Before-Import'}.get(why, 'Automatic')
    try:
        dst = sm.backup(game, backup_root(), kind, why, INFO.get('version', ''))
        if dst:
            sm.prune(backup_root(), int(settings().get('backup_keep', 10)))
            log(f'saves backed up to {dst}')
        return dst
    except (OSError, sm.SaveError) as e:
        log(f'save backup failed: {e}')
        return None


def tester_id():
    try:
        return json.loads(json.loads(LICENSE.read_text())['payload'])['tester_id']
    except (OSError, ValueError, KeyError):
        return '-'


def settings():
    import ctypes
    try:
        de = (ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3ff) == 0x07
    except (OSError, AttributeError):
        de = False
    s = dict(game_dir=str(Path.home() / 'Games' / 'Ocarina Reborn'), language='de' if de else 'en-US', workers='auto',
             ui_language='de' if de else 'en', audio='default')
    try:
        s.update(json.loads(SETTINGS.read_text()))
    except (OSError, ValueError):
        pass
    return s


def save_settings(s):
    SETTINGS.write_text(json.dumps(s, indent=2))


def find_nups():
    """.nup files in the usual places (Downloads, Desktop, Documents, two folders deep), newest first"""
    found, home = {}, Path.home()
    for base in (home / 'Downloads', home / 'Desktop', home / 'Documents', home / 'Games'):
        if not base.is_dir():
            continue
        for pat in ('*.nup', '*/*.nup', '*/*/*.nup'):
            try:
                for f in base.glob(pat):
                    if f.is_file() and f.stat().st_size > 1 << 30:
                        found[str(f.resolve())] = f
            except OSError:
                pass
    return sorted(found.values(), key=lambda f: f.stat().st_mtime, reverse=True)


def age(ts):
    d = (time.time() - ts) / 86400
    return 'heute' if d < 1 else 'gestern' if d < 2 else f'vor {int(d)} Tagen'


def free_gb(path):
    p = Path(path)
    while not p.exists() and p.parent != p:
        p = p.parent
    try:
        return shutil.disk_usage(p).free / 2**30
    except OSError:
        return 0.0


def layout(ctx, top, blocks, bottom_margin=30):
    """vertical flow: blocks of (design height, design gap before, share of the room left over); returns each block's top
    and height in pixels. The room a taller window has goes to the blocks and gaps by their shares (no empty band at the
    bottom), a shorter one takes it from the gaps first"""
    s = ctx.s
    need = sum(h + g for h, g, _ in blocks) + bottom_margin
    room = ctx.H / s - top / s - need
    shares = sum(w for _, _, w in blocks) or 1
    out, y = [], top / s
    for h, g, w in blocks:
        extra = room * w / shares
        if room >= 0:
            gx, hx = (extra * 0.15, extra * 0.85) if h else (extra, 0)
        else:   # (short: the gaps give way, down to a third)
            gx, hx = max(-g * 0.66, extra), 0
        y += g + gx
        out.append((y * s, (h + hx) * s))
        y += h + hx
    return out


# (the settings the launcher keeps itself, in settings.json, and hands to the game at Play)
# (Ocarina Reborn) the low-end rows on the Memory tab: the launcher keeps them and hands them to the engine at Play
# (low_end_env). Each is an engine switch with a real effect: engine_v21.py RAM_GUARD, and Hookshot's own RX_VK_* switches
LOW_END_ROWS = (
    ('ram_guard', 'RAM-Schutz', 'RAM guard',
     ['Notfall (512 MB Reserve)', 'Standard (1 GB Reserve)', 'Stark (3 GB Reserve)'], ['Emergency (512 MB reserve)', 'Standard (1 GB reserve)', 'Strong (3 GB reserve)'],
     'Bei knappem RAM oder Windows-Speicher gibt das Spiel ungenutzte Texturen frei. Auch Notfall hält einen Mindestschutz aktiv; '
     'Auto-Texturspeicher bleibt begrenzt. Stark: für lange Sitzungen, 16 GB RAM oder viele offene Programme.',
     'When RAM or Windows commit runs short, the game releases unused textures. Emergency keeps minimum protection active; '
     'Auto texture memory stays capped. Strong: for long sessions, 16 GB RAM or many open programs.', 'low'),
    ('tex_max_dim', 'Größte Texturen', 'Largest textures',
     ['Standard (2048)', '1024 (weniger VRAM)'], ['Standard (2048)', '1024 (less VRAM)'],
     'Sehr große Texturen (ab 64 MB) werden höchstens so breit geladen. 1024 spart Grafikspeicher auf Karten mit 4–6 GB; '
     'diese Texturen werden etwas unschärfer. Spiel neu starten.',
     'Very large textures (64 MB and up) load at most this wide. 1024 saves video memory on 4-6 GB cards; '
     'those textures look a little softer. Restart the game.', 'low'),
    ('low_spec', 'Low-Spec-Modus', 'Low-spec mode',
     ['Aus', 'An'], ['Off', 'On'],
     'Keine zusätzlichen Hilfsthreads für Speicherkopien: entlastet CPUs mit 4 Kernen oder weniger. Auf starken CPUs '
     'eher langsamer. Spiel neu starten.',
     'No extra helper threads for memory copies: eases CPUs with 4 cores or fewer. On strong CPUs rather slower. '
     'Restart the game.', 'low'),
    ('vram_compact', 'Grafikspeicher verdichten (Test)', 'Compact video memory (test)',
     ['Aus', 'An'], ['Off', 'On'],
     'Hält Texturen in einem eigenen, verdichteten Speicherbereich und lässt der Karte mehr Luft. Kann auf knappen Karten '
     'Ruckler verringern. Experimentell. Spiel neu starten.',
     'Keeps textures in a compacted area of their own, leaving the card more room. Can reduce stutter on tight cards. '
     'Experimental. Restart the game.', 'medium'),
)
LOW_END_ROWS += (
    ('fps_target', 'Auto-Auflösung: FPS-Ziel', 'Auto resolution: FPS target',
     ['Aus', '30 FPS', '45 FPS', '60 FPS'], ['Off', '30 FPS', '45 FPS', '60 FPS'],
     'Senkt die Render-Auflösung schrittweise (bis 50 %), wenn die Grafikkarte das Ziel nicht schafft, und hebt sie wieder an, '
     'wenn Luft ist – höchstens bis zur eingestellten Render-Auflösung. Prüft alle 5 Sekunden, damit es nicht ständig springt. '
     'Hilft nur, wenn die Grafikkarte bremst. Spiel neu starten.',
     'Lowers the render resolution step by step (down to 50%) when the graphics card misses the target, and raises it again '
     'when there is room, up to the Render resolution setting. Checks every 5 seconds so it does not jump around. Only helps '
     'when the graphics card is the bottleneck. Restart the game.', 'low'),
)
LOW_END_ROWS += (
    # (Hookshot's own RX_VK_GPL, off upstream: vk_draw.cpp gpl_wanted. A new pipeline is linked at once from the driver's stage
    # libraries so the draw is not left out while the full build runs; a cold library can stall the draw instead. Needs the
    # driver's pipeline libraries and extended dynamic state 3, else no effect. Debug package 2026-11-12 04:48: a cutscene's
    # new pipelines took 2.5-13 s each on an RX 7900 XTX, 35-53 draws a frame left out, the character a flat silhouette)
    ('fast_pipelines', 'Schnelle Pipelines (GPL, Test)', 'Fast pipelines (GPL, test)',
     ['Aus', 'An'], ['Off', 'On'],
     'Neue Szenen werden sofort mit einer schnell verknüpften Pipeline gezeichnet, während die vollständige im Hintergrund '
     'entsteht. Hilft, wenn Figuren beim ersten Mal als flache Silhouette oder gar nicht erscheinen. Experimentell: kann auf '
     'manchen Treibern kurz hängen. Spiel neu starten.',
     'New scenes are drawn at once with a quickly linked pipeline while the full one is built in the background. Helps when '
     'characters show up as a flat silhouette or not at all the first time. Experimental: can stall briefly on some drivers. '
     'Restart the game.', 'medium'),
)
LOW_END_DEFAULTS = {'ram_guard': 1, 'tex_max_dim': 0, 'low_spec': 0, 'vram_compact': 0, 'fps_target': 0, 'fast_pipelines': 0}


def low_end_env(cfg):
    """the low-end rows as the engine's switches (only what differs from the engine's own defaults)"""
    get = lambda k: int(cfg.get(k, LOW_END_DEFAULTS[k]))
    env = {'OCR_RAM_RESERVE_MB': str((512, 1024, 3072)[min(get('ram_guard'), 2)])}
    if get('tex_max_dim') == 1:
        env['RX_VK_TEX_MAX_DIM'] = '1024'
    if get('low_spec'):
        env['RX_VK_LOW_SPEC'] = '1'
    if get('vram_compact'):
        env['RX_VK_COMPACT'] = '1'
    if get('fps_target'):
        env['OCARINA_FPS_TARGET'] = str((0, 30, 45, 60)[min(get('fps_target'), 3)])
    if get('fast_pipelines'):
        env['RX_VK_GPL'] = '1'
    return env


# (mesh_shaders: Hookshot v2.2.0 reads it only as the launch switch RX_VK_MESH_SHADERS, and its menu drops the old line from the
# options file: kept in the launcher's settings, handed over at Play, game_env)
LAUNCHER_KEYS = ('monster_health', 'boss_health', 'enemy_damage', 'one_hit', 'cheats', 'protect_hearts', 'mesh_shaders') + tuple(LOW_END_DEFAULTS)


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title('Ocarina Reborn')
        self.configure(bg=ui.BG_BOTTOM)
        sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
        f = max(1.0, self.winfo_fpixels('1i') / 96)
        # (the window: 1440 x 810 at 100 %, as much more as Windows scales, never past the screen; it can be made as small as
        # 1100 x 620, where the design is drawn at about two thirds of its size, and as large as the screen)
        ww, wh = min(int(1440 * f), sw - 40), min(int(810 * f), sh - 80)
        self.geometry(f'{ww}x{wh}+{max(0, (sw - ww) // 2)}+{max(0, (sh - wh) // 2 - 20)}')
        self.minsize(min(int(1100 * f), ww), min(int(620 * f), wh))
        ico = INSTALL / 'OcarinaReborn.ico'
        if ico.is_file():
            self.iconbitmap(default=str(ico))
        self.logos = {}
        for n in (24, 32, 40, 48, 56, 64, 72, 80, 96, 112):
            try:
                self.logos[n] = tk.PhotoImage(file=str(ASSETS / f'ocarina-{n}.png'))
            except tk.TclError:
                pass
        st = ttk.Style(self)
        st.theme_use('clam')
        st.configure('Blue.Horizontal.TProgressbar', background=BLUE, troughcolor=LINE, bordercolor=LINE,
                     lightcolor=BLUE_HI, darkcolor=BLUE, thickness=10)
        self.q = queue.Queue()
        self.cfg = settings()
        UI_LANG[0] = self.cfg.get('ui_language', 'de')
        self.busy = False
        log(f'{INFO["name"]} {INFO["version"]} build {INFO["build_id"]} commit {INFO["commit"]}')
        self.sysinfo = []
        self.facts = None
        self.diag = self.cfg.get('last_diagnosis') or []
        self.active_gpu = self.cfg.get('active_gpu')

        def pc():
            try:
                self.facts = advisor.pc_facts()
                log(f'pc: {self.facts}')
            except Exception as e:
                log(f'pc facts failed: {e}')
        threading.Thread(target=pc, daemon=True).start()

        def facts():
            self.sysinfo = system_info()
            for l in self.sysinfo:
                log(l)
        threading.Thread(target=facts, daemon=True).start()
        if self.cfg.get('dlss_sdk') and (Path(self.cfg['dlss_sdk']) / 'lib' / 'nvsdk_ngx_s.lib').is_file():
            os.environ['HOOKSHOT_NGX_SDK'] = self.cfg['dlss_sdk']   # (NVIDIA DLSS: every build from now on has it)
        self.canvas = tk.Canvas(self, bg=ui.BG_BOTTOM, highlightthickness=0, bd=0)
        self.canvas.pack(fill='both', expand=True)
        self.stage = ui.Stage(self, self.canvas)
        self.stage.on_double = self.toggle_max
        self.page_tab = None   # (the settings page's tab while it shows: the controller's LB/RB)
        self.gamepad = gamepad.Gamepad(self, self.stage, back=self.pad_back, play=self.pad_play, tab=self.pad_tab)
        self.stage.on_render = self.gamepad.refresh
        self.chrome = ui.Chrome(self, on_drop=self.dropped)
        self.music = Music()
        self.muted = bool(self.cfg.get('music_muted'))
        if self.music.ok and not self.muted:
            self.music.play()
        self.fairy = None
        self.float_ctl = None
        self.step = 'files'
        self.update_info = None
        self.news = None
        threading.Thread(target=self.check_update, daemon=True).start()
        self.news_new = False
        self.after(500, self.poll_update)
        self.protocol('WM_DELETE_WINDOW', self.quit_app)
        self.after(50, self.route)
        self.after(600, self.start_fairy)

    def quit_app(self):
        self.music.close()
        if self.fairy:
            self.fairy.close()
        self.destroy()

    def start_fairy(self):
        """the fairy over the launcher (fairy.py); without it (an old Windows, no asset) the launcher is as it was"""
        if self.fairy and self.fairy.alive:
            return
        try:
            self.fairy = fairy.Fairy(self, ASSETS / 'fairy.bin')
        except Exception as e:
            log(f'fairy not shown: {type(e).__name__}: {e}')

    def toggle_max(self):
        self.state('normal' if self.state() == 'zoomed' else 'zoomed')

    def toggle_music(self):
        self.muted = not self.muted
        self.cfg['music_muted'] = self.muted
        save_settings(self.cfg)
        self.music.stop() if self.muted else self.music.play()
        self.stage.render()

    def dropped(self, paths):
        """files dropped on the window: a .nup (or a folder with one) is picked on the game files page"""
        if self.busy:
            return
        nups = []
        for p in map(Path, paths):
            if p.is_dir():
                nups += sorted(p.glob('*.nup')) + sorted(p.glob('*/*.nup'))
            elif p.suffix.lower() == '.nup':
                nups.append(p)
        if not nups:
            return messagebox.showinfo('Ocarina Reborn', T('Darin ist keine .nup-Datei.', 'There is no .nup file in it.'))
        if self.step != 'files' or not hasattr(self, 'nup'):
            self.game_files()
        self.nup.set(str(nups[0]))
        self.nup_files = [nups[0]] + [x for x in self.nup_files if str(x) != str(nups[0])]
        self.game_files(keep=True)

    def show_diagnosis(self):
        de = UI_LANG[0] == 'de'
        lines = []
        for w_ in (advisor.pc_warnings(self.facts, self.active_gpu, de) if self.facts else []):
            lines.append('⚠  ' + w_)
        mark = {'ok': '✓  ', 'warn': '•  ', 'tip': '→  '}
        for kind, text in self.diag:
            lines.append(mark.get(kind, '•  ') + text)
        if not lines:
            lines = [T('Noch keine Messung: spiel eine Runde, danach steht hier, was bremst und was hilft.',
                       'Nothing measured yet: play a while, then this shows what holds it back and what helps.')]
        report = T('Aus deiner letzten Spielsitzung (echte Messwerte des Spiels):',
                   'From your last session (the game\'s own measurements):') + '\n\n' + '\n\n'.join(lines)
        record = self.cfg.get('last_performance') or {}
        game = Path(self.cfg['game_dir'])
        current = game_settings.read(game)
        changes, reasons = {}, []
        if (record.get('build') == INFO.get('stamp') and record.get('game') == str(game.resolve()) and
                self.facts and record.get('hardware') == performance.hardware_signature(self.facts)):
            changes, reasons = performance.suggest(record.get('summary'), current, record.get('settings'), de)
        if reasons:
            report += '\n\n' + '\n'.join(reasons)
        if not changes:
            return messagebox.showinfo(T('Leistung', 'Performance'), report)
        values = performance.signature(current)
        labels = {key: (d if de else e, {str(v): cd if de else ce for v, cd, ce in choices})
                  for key, d, e, choices in game_settings.ROWS}
        preview = []
        for key, value in changes.items():
            name, choices = labels.get(key, (key, {}))
            old = values.get(key, current.get(key, '0'))
            preview.append(f'{name}: {choices.get(str(old), str(old))} → {choices.get(str(value), str(value))}')
        report += '\n\n' + T('Vorschlag für den nächsten Start:', 'Suggested changes for the next start:')
        report += '\n' + '\n'.join(preview)
        report += '\n\n' + T('Diese Änderungen übernehmen?', 'Apply these changes?')
        if messagebox.askyesno(T('Leistung', 'Performance'), report):
            try:
                backup = DIRS['Reports'] / ('settings-before-tuning-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.ini')
                source = game_settings.ini_file(game)
                if source.is_file():
                    shutil.copy2(source, backup)
                game_settings.write(game, changes)
                log(f'measured performance settings applied: {changes}')
                messagebox.showinfo(T('Leistung', 'Performance'), T(
                    'Gespeichert. Vergleiche beim nächsten Start dieselben Spielszenen. Die bisherigen Einstellungen liegen im Reports-Ordner.',
                    'Saved. Compare the same scenes on your next run. Previous settings are in the Reports folder.'))
            except OSError as exc:
                messagebox.showerror(T('Leistung', 'Performance'), str(exc))

    def apply_preset(self, key):
        """a preset's options into the game's options file (the same keys the in-game menu saves)"""
        game = Path(self.cfg['game_dir'])
        if key == 'recommended':
            if not self.facts:
                return messagebox.showinfo('Ocarina Reborn', T('Dein PC wird noch erkannt, versuch es gleich nochmal.',
                                                               'Still looking at your PC, try again in a moment.'))
            key, values, gpu, why = advisor.recommend(self.facts, self.dlss_ready())
            log(f'preset recommended for {gpu} ({why}): {key} {values}')
        else:
            values = advisor.build_preset(key, self.facts, self.dlss_ready())
        # (the monitor's own resolution as the output, full screen: what the preset's scaling is meant for)
        mode = display_info().split(' @ ')[0]
        res = next((v for k, _d, _e, ch in game_settings.ROWS if k == 'output_res' for v, _x, e in ch if e == mode), None)
        if res is not None and 'output_res' not in values:
            values = dict(values, output_res=mode, fullscreen=1)   # (as the game writes it: WxH)
        elif 'output_res' in values:
            values['fullscreen'] = 1
            try:
                mw, mh = map(int, mode.split('x'))
                pw, ph = map(int, values['output_res'].split('x'))
                if mw < pw or mh < ph:
                    values['output_res'] = mode
            except (ValueError, AttributeError):
                pass
        try:
            # (launcher keys in a preset, e.g. the FPS target: the launcher's own settings, not the game's options file)
            for k in [k for k in values if k in LAUNCHER_KEYS]:
                self.cfg[k] = values.pop(k)
                save_settings(self.cfg)
            game_settings.write(game, {k: v for k, v in values.items()})
            self.pending_settings = {k: v for k, v in getattr(self, 'pending_settings', {}).items() if k not in values}
            self.settings_status = (T('Preset übernommen. Gilt ab dem nächsten Spielstart.', 'Preset applied. Applies at the next start.'), ui.GOLD)
            log(f'preset {key}: {values}')
        except OSError as e:
            self.settings_status = (str(e), RED)
        self.settings_page(1, True)

    # ---- NVIDIA DLSS: NVIDIA's SDK may not be shipped with this GPL engine (its license, 4(e)); the player accepts it and
    # it is fetched from NVIDIA's GitHub onto this PC (the engine's scripts/ngx_sdk.py), then the game is built with it here
    def has_nvidia(self):
        return any('NVIDIA' in l and 'Display adapter' in l for l in self.sysinfo)

    def dlss_ready(self):
        s = self.cfg.get('dlss_sdk')
        return bool(s) and (Path(s) / 'lib' / 'nvsdk_ngx_s.lib').is_file()

    def setup_dlss(self):
        if self.busy:
            return
        lic = 'https://github.com/NVIDIA/DLSS/blob/main/LICENSE.txt'
        if not messagebox.askyesno('NVIDIA DLSS', T(
                'NVIDIA DLSS kommt von NVIDIA und steht unter NVIDIAs eigener Lizenz:\n' + lic + '\n\n'
                'Ocarina Reborn darf DLSS nicht mitliefern. Wenn du zustimmst, lädt der Launcher NVIDIAs DLSS-SDK von NVIDIAs '
                'GitHub auf diesen PC und baut dein Spiel damit neu (wie ein Update, deine Spielstände bleiben).\n\n'
                'Akzeptierst du NVIDIAs Lizenz?',
                'NVIDIA DLSS comes from NVIDIA and is under NVIDIA\'s own license:\n' + lic + '\n\n'
                'Ocarina Reborn may not ship DLSS. If you agree, the launcher downloads NVIDIA\'s DLSS SDK from NVIDIA\'s GitHub '
                'onto this PC and rebuilds your game with it (like an update; your saves stay).\n\n'
                'Do you accept NVIDIA\'s license?')):
            return
        sdk = APP / 'NVIDIA-DLSS'
        cmd = [str(INSTALL / 'python' / 'python.exe'), '-I', str(INSTALL / 'engine' / 'scripts' / 'ngx_sdk.py'), str(sdk),
               '--accept-nvidia-license', '--platform', 'windows']
        log('dlss: the player accepted NVIDIA\'s license; fetching the SDK')
        self.busy = True
        state = {'done': None}

        def work():
            try:
                r = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=900,
                                   creationflags=NO_WINDOW)
                log('dlss: ' + (r.stdout + r.stderr).strip().replace('\n', ' | ')[-800:])
                state['done'] = 'ok' if r.returncode == 0 and (sdk / 'lib' / 'nvsdk_ngx_s.lib').is_file() else \
                    (r.stderr.strip().splitlines() or ['exit %d' % r.returncode])[-1]
            except (OSError, subprocess.SubprocessError) as e:
                state['done'] = str(e)

        def poll():
            if state['done'] is None:
                return self.after(300, poll)
            self.busy = False
            if state['done'] != 'ok':
                messagebox.showerror('NVIDIA DLSS', T('DLSS konnte nicht geladen werden:\n', 'DLSS could not be downloaded:\n') + state['done'])
                return self.stage.render()
            self.cfg['dlss_sdk'] = str(sdk)
            save_settings(self.cfg)
            os.environ['HOOKSHOT_NGX_SDK'] = str(sdk)
            log('dlss: SDK ready, rebuilding the game with it')
            self.run_build(dict(update=True, dest=self.cfg['game_dir'], language=self.cfg.get('language', 'de'),
                                workers=self.cfg.get('workers', 'auto')))

        def body(ctx, top):
            x, w = self.content(ctx)
            self.heading(ctx, x, top + 34 * ctx.s, 'NVIDIA DLSS', T('NVIDIAs DLSS-SDK wird von NVIDIAs GitHub geladen …',
                                                                    'Downloading NVIDIA\'s DLSS SDK from NVIDIA\'s GitHub …'),
                         icon='download', w=w)
        self.show('play', body)
        threading.Thread(target=work, daemon=True).start()
        poll()

    # ---- updates: the newest release on the site's GitHub, offered in the header; downloaded, checked, started
    RELEASES = 'https://api.github.com/repos/ocarina-pc-native-build/ocarina-pc-native-build.github.io/releases/latest'
    SETUP_NAME = 'Ocarina-Reborn-Alpha-Setup.exe'

    def check_update(self):
        import re
        import urllib.request

        def ver(s):
            return tuple(int(x) for x in re.findall(r'\d+', s.split('-')[0])[:3])
        try:
            req = urllib.request.Request(self.RELEASES, headers={'User-Agent': 'OcarinaReborn-Launcher',
                                                                 'Accept': 'application/vnd.github+json'})
            with urllib.request.urlopen(req, timeout=15) as r:
                rel = json.loads(r.read().decode('utf-8'))
            tag = rel.get('tag_name', '')
            self.news = (tag.lstrip('v'), rel.get('body') or '')
            self.news_new = True
            asset = next((a for a in rel.get('assets', []) if a.get('name') == self.SETUP_NAME), None)
            mine = INFO.get('version', '0')
            if asset and ver(tag) > ver(mine):
                sha = re.search(r'\b[0-9a-f]{64}\b', rel.get('body') or '')
                self.update_info = dict(version=tag.lstrip('v'), url=asset['browser_download_url'], size=asset.get('size', 0),
                                        notes=rel.get('body') or '', sha=sha.group(0) if sha else None)
                log(f'update available: {tag} (this is {mine})')
                self.news_new = True
            else:
                log(f'updates: {mine} is the newest ({tag or "no release"})')
        except Exception as e:   # (offline, GitHub unreachable: no update offered, nothing else changes)
            log(f'update check failed: {type(e).__name__}: {e}')

    def poll_update(self):
        """(the check runs in a thread; what it found is drawn from here, Tk's own thread)"""
        if self.news_new:
            self.news_new = False
            if not self.busy and self.step in ('play', 'files'):
                self.stage.render()
            return
        self.after(500, self.poll_update)

    def show_news(self):
        ver, body = self.news
        text = body.replace('**', '').replace('## ', '').split('SHA-256')[0].strip()
        messagebox.showinfo('Ocarina Reborn', T(f'Neu in {ver}', f'New in {ver}') + '\n\n' + text[:2500])

    def offer_update(self):
        info = self.update_info
        if not info or self.busy:
            return
        notes = info['notes'].replace('**', '').replace('## ', '')
        notes = notes[:1400] + (' …' if len(notes) > 1400 else '')
        if not messagebox.askyesno('Ocarina Reborn', T(f'Ocarina Reborn {info["version"]} ist da.\n\n', f'Ocarina Reborn {info["version"]} is out.\n\n')
                                   + notes + T('\n\nJetzt herunterladen und installieren? Der Launcher schließt sich dafür.',
                                               '\n\nDownload and install it now? The launcher closes for it.')):
            return
        self.download_update(info)

    def download_update(self, info):
        import hashlib
        import tempfile
        import urllib.request
        # (a name of its own each time: a setup of the same version from an earlier try, still open or held by an antivirus
        # scan, made the download fail with PermissionError on a tester's PC, 1.0.1)
        dst = Path(tempfile.gettempdir()) / f'Ocarina-Reborn-Setup-{info["version"]}-{os.getpid()}-{int(time.time())}.exe'
        state = {'frac': 0.0, 'text': T('Wird heruntergeladen …', 'Downloading …'), 'done': None}
        self.busy = True

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (py, ph) = layout(ctx, top, [(76, 34, 0), (150, 40, 1)])
            self.heading(ctx, x, hy, T(f'Update auf {info["version"]}', f'Updating to {info["version"]}'),
                         T('Das neue Setup wird von GitHub geladen und geprüft, dann startet es.',
                           'The new setup is downloaded from GitHub and checked, then it starts.'), icon='download', w=w)
            ctx.panel(x, py, w, 150 * s, r=16, fill=ui.PANEL, alpha=0.85, border=ui.LINE)
            ctx.text(x + 30 * s, py + 34 * s, state['text'], 20, 'semibold', ui.TEXT, key='dl_text')
            ctx.progress('dl', x + 30 * s, py + 84 * s, w - 60 * s, 16 * s, state['frac'])
        self.show('files', body)

        def work():
            try:
                req = urllib.request.Request(info['url'], headers={'User-Agent': 'OcarinaReborn-Launcher'})
                h = hashlib.sha256()
                got = 0
                with urllib.request.urlopen(req, timeout=60) as r, open(dst, 'wb') as f:
                    total = int(r.headers.get('Content-Length') or info['size'] or 0)
                    while True:
                        chunk = r.read(1 << 20)
                        if not chunk:
                            break
                        f.write(chunk)
                        h.update(chunk)
                        got += len(chunk)
                        if total:
                            state['frac'] = got / total
                            state['text'] = T(f'Wird heruntergeladen … {got >> 20} / {total >> 20} MB',
                                              f'Downloading … {got >> 20} / {total >> 20} MB')
                if total and got != total:
                    raise OSError(f'{got} of {total} bytes')
                if info['sha'] and h.hexdigest() != info['sha']:
                    raise OSError('the checksum does not match the release')
                state['done'] = 'ok'
            except Exception as e:
                state['done'] = f'{type(e).__name__}: {e}'

        def poll():
            self.stage.set_bar('dl', state['frac'])
            self.stage.set_text('dl_text', state['text'])
            if state['done'] is None:
                return self.after(200, poll)
            self.busy = False
            if state['done'] != 'ok':
                log(f'update download failed: {state["done"]}')
                messagebox.showerror('Ocarina Reborn', T('Das Update konnte nicht geladen werden:\n', 'The update could not be downloaded:\n')
                                     + state['done'])
                return self.route()
            log(f'update {info["version"]} downloaded and checked: {dst}')
            subprocess.Popen([str(dst)])
            self.quit_app()
        threading.Thread(target=work, daemon=True).start()
        poll()

    # ---- the frame every page has: the header (logo, name, the steps, music, the window's buttons)
    # ---- the controller (gamepad.py): B back to the ready page, Start plays from it, LB/RB the settings tabs ----------------
    def pad_back(self):
        if self.step == 'play' and not self.busy and not any(h.cmd == self.play for h in self.stage.hots):
            self.ready()

    def pad_play(self):
        if self.step == 'play' and not self.busy and any(h.cmd == self.play for h in self.stage.hots):
            self.play()

    def pad_tab(self, d):
        if self.page_tab is not None:
            n = len(game_settings.SECTIONS) + 2   # (the sections, Difficulty, Cheats)
            self.settings_page((self.page_tab + d) % n, True)

    def show(self, step, body):
        """draws the page: the header, then body(ctx, top) under it"""
        self.step = step
        self.page_tab = None
        if self.float_ctl:
            self.float_ctl.destroy()
            self.float_ctl = None

        def draw(ctx):
            top = self.header(ctx)
            body(ctx, top)
        self.stage.show(draw)

    def header(self, ctx):
        s, W = ctx.s, ctx.W
        hh = 84 * s
        ctx.p.rect(0, 0, W, hh, ui.HEAD, 0.55)
        ctx.hline(0, hh, W, ui.LINE, 0.8)
        if self.chrome.ok:
            ctx.hot(0, 0, W, hh, self.chrome.drag, cursor='', kind='drag')
            if self.state() != 'zoomed':
                ctx.hot(0, 0, W, 5, self.chrome.resize_top, cursor='sb_v_double_arrow', kind='drag')
        # logo, a rule, the name
        want = 62 * s
        n = min(self.logos, key=lambda k: abs(k - want)) if self.logos else None
        if n:
            ctx.image(48 * s + want / 2, hh / 2, self.logos[n], anchor='center')
        ctx.vline(128 * s, hh / 2 - 17 * s, 34 * s, ui.LINE_HI, 0.8)
        ctx.text(152 * s, hh / 2, 'Ocarina Reborn', 28, 'bold', ui.TEXT, anchor='w')
        title_end = 152 * s + ctx.text_width('Ocarina Reborn', 28, 'bold')
        # the steps: Game files > Build > Play, the current one lit
        items = (('files', 'folder', 'Game files'), ('build', 'cube', 'Build'), ('play', 'play', 'Play'))
        pad, isz, gap, chev = 30 * s, 26 * s, 12 * s, 44 * s
        widths = [pad * 2 + isz + gap + ctx.text_width(t, 21) for _, _, t in items]
        total = sum(widths) + chev * 2 + 8 * s
        x0 = max(W / 2 - total / 2, title_end + 30 * s)
        right_room = (3 * 66 + 150) * s
        x0 = min(x0, W - right_room - total)
        cy, ch = hh / 2 - 2 * s, 58 * s
        ctx.panel(x0, cy - ch / 2, total, ch, r=29, fill=ui.CELL, alpha=0.8, border=ui.LINE, balpha=0.9)
        x = x0 + 4 * s
        for i, ((key, icon, text), w) in enumerate(zip(items, widths)):
            on = key == self.step
            if on:
                ctx.panel(x, cy - ch / 2 + 4 * s, w, ch - 8 * s, r=25, fill='#3b8bff', fill2=ui.ACCENT_LO, alpha=1,
                          border='#8cc2ff', border2=ui.ACCENT, bw=1.2, glow=ui.GLOW, gr=16, ga=0.45)
            col = ui.TEXT if on else ui.SUB
            ctx.icon(x + pad + isz / 2, cy, icon, 23, col)
            ctx.text(x + pad + isz + gap, cy, text, 21, 'semibold' if on else 'regular', col, anchor='w')
            x += w
            if i < 2:
                ctx.icon(x + chev / 2, cy, 'right', 15, ui.SUB)
                x += chev
        # the window's buttons, and the music
        bx = W
        if self.chrome.ok:
            for name, cmd, danger in (('close', self.quit_app, True),
                                      ('restore' if self.state() == 'zoomed' else 'maximize', self.toggle_max, False),
                                      ('minimize', self.iconify, False)):
                bw = 66 * s
                bx -= bw

                def look(c, on, bx=bx, bw=bw, danger=danger):
                    if on:
                        c.p.rect(bx, 0, bw, hh * 0.62, '#c42b1c' if danger else ui.PANEL_HI, 0.95)
                ctx.icon(bx + bw / 2, hh * 0.31, name, 17 if name != 'close' else 18, ui.SUB)
                ctx.hot(bx, 0, bw, hh * 0.62, cmd, hover=look)
            bx -= 14 * s
        if self.update_info and not self.busy:
            label = T(f'Update {self.update_info["version"]}', f'Update {self.update_info["version"]}')
            uw = 56 * s + ctx.text_width(label, 16, 'semibold')
            bx -= uw + 10 * s
            ctx.button(bx, hh / 2 - 19 * s, uw, 38 * s, label, self.offer_update, kind='primary', icon='download', size=16, r=19)
        if self.music.ok:
            label = T('Musik aus', 'Music off') if self.muted else T('Musik an', 'Music on')
            mw = 48 * s + ctx.text_width(label, 16)
            ctx.button(bx - mw, hh / 2 - 19 * s, mw, 38 * s, label, self.toggle_music, kind='quiet',
                       icon='mute' if self.muted else 'speaker', size=16, weight='regular')
        return hh

    def content(self, ctx, margin=54):
        """the column the page uses: the window's width less the margins, at most 1900 design units, in the middle"""
        s = ctx.s
        w = min(ctx.W - 2 * margin * s, 1900 * s)
        return (ctx.W - w) / 2, w

    def heading(self, ctx, x, y, title, sub=None, icon='download', icon_color=ui.ACCENT_HI, w=None):
        s = ctx.s
        ctx.icon_box(x + 6 * s, y, 76 * s, icon, 34, icon_color, r=14)
        ctx.text(x + 106 * s, y + 2 * s, title, 40, 'bold', ui.TEXT)
        if sub:
            ctx.text(x + 107 * s, y + 56 * s, sub, 19, 'regular', '#c3d0ea', width=(w or ctx.W) - 120 * s)

    def footer_line(self, ctx, x, w, y):
        ctx.hline(x, y, w, ui.LINE, 0.6)

    # ---- flow: notice -> game files / build -> play
    def route(self):
        ack = DIRS['Config'] / 'alpha-ack.json'
        if not (ack.is_file() and json.loads(ack.read_text()).get('build_id') == INFO['build_id']):
            return self.notice(ack)
        # (no license: the alpha is open to everyone who has the game; activation() stays unused)
        game = Path(self.cfg['game_dir'])
        if not ((game / 'ready.json').is_file() and game_exe(game).is_file()):
            if STATE.is_file() and not self.busy:
                try:
                    return self.resume_page(json.loads(STATE.read_text()))
                except ValueError:
                    STATE.unlink(missing_ok=True)
            return self.game_files()
        try:
            built = json.loads((game / 'ready.json').read_text()).get('built_by')
        except (OSError, ValueError):
            built = None
        if built != INFO.get('stamp') and not getattr(self, 'update_later', False):
            return self.update_page()
        self.ready()

    def notice(self, ack):
        self.notice_ok = getattr(self, 'notice_ok', False)

        def go():
            if self.notice_ok:
                ack.write_text(json.dumps({'build_id': INFO['build_id'], 'at': NOW}))
                self.route()

        def toggle():
            self.notice_ok = not self.notice_ok
            self.stage.render()

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (cy, chh), (fy, fh) = layout(ctx, top, [(76, 34, 0), (300, 34, 1), (82, 30, 0)])
            self.heading(ctx, x, hy, 'Private Alpha Build', T('Bitte vor dem Start lesen.', 'Please read before you start.'),
                         icon='warning', icon_color=ui.GOLD, w=w)
            ctx.panel(x, cy, w, chh, r=16, fill=ui.PANEL, alpha=0.85, border=ui.LINE)
            ctx.text(x + 40 * s, cy + 36 * s, 'PRIVATE ALPHA BUILD', 18, 'semibold', ui.GOLD)
            ctx.text(x + 40 * s, cy + 76 * s, T(
                'Dies ist eine sehr instabile Testversion. Abstürze, Hänger, Grafikfehler und kaputtes Gameplay sind zu '
                'erwarten. Sie ist nur zum Testen gedacht.', 'This is a highly unstable development build. Crashes, '
                'freezes, graphical issues and broken gameplay are expected. It is provided only for testing.'),
                22, 'regular', ui.TEXT, width=w - 80 * s)
            d = 30 * s
            ry = cy + chh - 70 * s
            ctx.check(x + 40 * s, ry, d, self.notice_ok, toggle)
            label = T('Ich habe verstanden, dass dies eine instabile Alpha ist.', 'I understand this is an unstable alpha.')
            ctx.text(x + 40 * s + d + 16 * s, ry + d / 2, label, 20, 'regular', ui.TEXT, anchor='w')
            ctx.hot(x + 30 * s, ry - 8 * s, d + 40 * s + ctx.text_width(label, 20), d + 16 * s, toggle)
            bw = 297 * s
            ctx.button(x + w - bw, fy, bw, fh, T('Weiter', 'Continue'), go, kind='primary' if self.notice_ok else 'secondary',
                       icon='right', size=28, weight='bold', r=16)
        self.show('files', body)

    def activation(self, reason=None):
        """(unused: the alpha needs no license; kept for a later build that does)"""
        try:
            hw = lic.hardware_id()
        except RuntimeError as ex:
            hw = str(ex)

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            self.heading(ctx, x, top + 34 * s, T('Alpha-Zugang freischalten', 'Activate Alpha Access'), reason, icon='key', w=w)
            ctx.panel(x, top + 160 * s, w, 90 * s, r=14, fill=ui.PANEL, alpha=0.9, border=ui.LINE)
            ctx.text(x + 24 * s, top + 178 * s, T('DEINE PC-ID', 'YOUR PC-ID'), 16, 'semibold', ui.SUB)
            ctx.text(x + 24 * s, top + 206 * s, hw, 20, 'regular', ui.TEXT)

            def copy():
                self.clipboard_clear()
                self.clipboard_append(hw)

            def load():
                f = filedialog.askopenfilename(title=T('Lizenzdatei auswählen', 'Select your license file'),
                                               filetypes=[('Ocarina Reborn license', '*.dat'), ('*', '*.*')])
                if not f:
                    return
                try:
                    text = Path(f).read_text(encoding='utf-8')
                    p = lic.check(text, PUBLIC_KEY, hw)
                    LICENSE.write_text(text)
                    log(f'license loaded, tester {p["tester_id"]}')
                    self.route()
                except (OSError, ValueError, lic.LicenseError) as ex:
                    messagebox.showerror('Ocarina Reborn', str(ex))
            ctx.button(x, top + 280 * s, 220 * s, 52 * s, T('PC-ID kopieren', 'Copy PC-ID'), copy)
            ctx.button(x + 240 * s, top + 280 * s, 260 * s, 52 * s, T('Lizenzdatei laden', 'Load license file'), load,
                       kind='primary')
        self.show('files', body)

    # ---- game files: the design's page
    def game_files(self, keep=False):
        game = Path(self.cfg['game_dir'])
        update = game_exe(game).is_file()
        if not keep or not hasattr(self, 'nup'):
            self.nup = tk.StringVar()
            self.nup_files = find_nups()
            self.dest = tk.StringVar(value=self.cfg['game_dir'])
            self.sel_language = dict(LANGS).get(self.cfg['language'], 'Deutsch')
            self.sel_workers = AUTO if self.cfg['workers'] == 'auto' else self.cfg['workers']
            self.nup_status = {}
            self.dest.trace_add('write', lambda *a: self.stage.set_text('space', self.space_text()[0], self.space_text()[1]))
        if not self.nup.get() and self.nup_files:
            self.nup.set(str(self.nup_files[0]))
        for f in self.nup_files[:3]:
            if str(f) not in self.nup_status:
                self.nup_status[str(f)] = (T('Überprüfe …', 'Checking …'), ui.SUB)
                self.check_nup(f)

        def pick_lang(v):
            self.sel_language = v
            self.stage.render()

        def pick_workers(v):
            self.sel_workers = v
            self.stage.render()

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            files = self.nup_files[:3]
            room = ctx.H / s - top / s
            n_cards = max(1, min(len(files), 1 + int(max(0, room - 857) // 104)))
            card_h = 92 * n_cards + 12 * (n_cards - 1)
            (hy, _), (dv1, _), (ly, _), (cy, _), (by, _), (dv2, _), (oy, _), (iy, _), (py, ph), (dv3, _), (fy, fh) = layout(
                ctx, top, [(76, 34, 0), (0, 27, 0.25), (22, 15, 0), (card_h, 16, 0), (34, 12, 0), (0, 20, 0.25), (24, 17, 0),
                           (52, 16, 0), (205, 38, 3), (0, 39, 0.3), (82, 7, 0)])
            self.heading(ctx, x, hy, T('Spiel neu bauen', 'Rebuild the game') if update else T('Spiel einrichten', 'Set up the game'),
                         T('Der Launcher liest deine eigene NUP-Datei, baut das Spiel daraus auf diesem PC und startet es '
                           'anschließend. Die NUP-Datei wird nie verändert oder hochgeladen.',
                           'The launcher reads your own NUP file, builds the game from it on this PC and then starts it. '
                           'The NUP file is never changed or uploaded.'), icon='download', w=w)
            ctx.hline(x, dv1, w, ui.LINE, 0.55)
            ctx.text(x + 10 * s, ly, T('NUP-DATEI AUF DIESEM PC', 'NUP FILE ON THIS PC'), 18, 'semibold', ui.SUB)
            if not files:
                ctx.panel(x, cy, w, 92 * s, r=14, fill=ui.PANEL, alpha=0.85, border=ui.LINE)
                ctx.icon_box(x + 18 * s, cy + 16 * s, 60 * s, 'file', 26, ui.SUB)
                ctx.text(x + 100 * s, cy + 46 * s, T('Keine .nup-Datei gefunden. Wähle sie mit „Durchsuchen…“ aus oder ziehe '
                                                     'sie hier hinein.', 'No .nup file found. Select it with "Browse…" or '
                                                     'drop it here.'), 20, 'regular', ui.SUB, anchor='w')
            for i, f in enumerate(files[:n_cards]):
                y = cy + i * 104 * s
                on = self.nup.get() == str(f)
                ch = 92 * s
                ctx.panel(x, y, w, ch, r=16, fill=ui.PANEL_HI if on else ui.PANEL, fill2=ui.PANEL, alpha=0.9,
                          border=ui.LINE_HI if on else ui.LINE, bw=1.3, glow=ui.GLOW if on else None, gr=18, ga=0.18)
                ctx.p.rect(x + 90 * s, y + 1, 76 * s, ch - 2, ui.CELL, 0.55)
                ctx.radio(x + 31 * s, y + ch / 2 - 15 * s, 30 * s, on)
                ctx.icon(x + 128 * s, y + ch / 2, 'file', 30, ui.TEXT)
                try:
                    st = f.stat()
                    meta = f'{st.st_size / 2**30:.1f} GB  •  {f.parent.name}  •  {age(st.st_mtime)}'
                except OSError:
                    meta = str(f.parent)
                ctx.text(x + 179 * s, y + 18 * s, f.name, 22, 'semibold', ui.TEXT, width=w - 440 * s)
                ctx.text(x + 179 * s, y + 52 * s, meta, 18, 'regular', ui.SUB)
                text, col = self.nup_status.get(str(f), ('', ui.SUB))
                pw = 193 * s
                ctx.panel(x + w - pw - 25 * s, y + ch / 2 - 23 * s, pw, 46 * s, r=10, fill=ui.CELL, alpha=0.9, border=ui.LINE)
                ctx.icon(x + w - pw - 25 * s + 36 * s, y + ch / 2, 'sync' if text.startswith(('Überprüfe', 'Checking')) else
                         'check' if col == ui.GREEN else 'info', 20, col, key=f'nupi{i}')
                ctx.text(x + w - pw - 25 * s + 64 * s, y + ch / 2, text.lstrip('✓✗ '), 18, 'regular',
                         ui.TEXT if col == ui.SUB else col, anchor='w', key=f'nup{i}')

                def choose(f=f):
                    self.nup.set(str(f))
                    self.stage.render()
                ctx.hot(x, y, w - pw - 40 * s, ch, choose)
            # not listed: browse, or drop
            t1 = T('Nicht gelistet?', 'Not listed?')
            ctx.text(x + 12 * s, by + 17 * s, t1, 20, 'regular', ui.TEXT, anchor='w')
            bx = x + 12 * s + ctx.text_width(t1, 20) + 18 * s
            bw = ctx.text_width(T('Durchsuchen…', 'Browse…'), 20, 'semibold') + 36 * s
            ctx.button(bx, by, bw, 34 * s, T('Durchsuchen…', 'Browse…'), self.browse, kind='pill', size=20)
            ctx.text(bx + bw + 18 * s, by + 17 * s, T('oder den NUP-Ordner hier hineinziehen.',
                                                       'or drop the NUP folder here.'), 20, 'regular', ui.TEXT, anchor='w')
            ctx.hline(x, dv2, w, ui.LINE, 0.55)
            # install folder | game language | build workers
            lw, ww_ = 263 * s, 272 * s
            sep = 32 * s
            wx = x + w - ww_ - 6 * s
            lx = wx - sep * 2 - lw
            ex1 = lx - sep * 2 - 154 * s - 22 * s
            ctx.icon(x + 24 * s, oy + 12 * s, 'folder', 24, ui.TEXT)
            ctx.text(x + 58 * s, oy + 12 * s, T('Installiere das Spiel nach', 'Install the game to'), 20, 'regular', ui.TEXT, anchor='w')
            ctx.entry('dest', x + 9 * s, iy, ex1 - x - 9 * s, 52 * s, self.dest, 20)
            ctx.button(ex1 + 22 * s, iy, 154 * s, 52 * s, T('Ändern', 'Change'), self.pick_dest, icon='folder', size=20,
                       weight='regular', r=10)
            ctx.vline(lx - sep, oy, 90 * s, ui.LINE, 0.6)
            ctx.icon(lx + 12 * s, oy + 12 * s, 'globe', 24, ui.TEXT)
            ctx.text(lx + 42 * s, oy + 12 * s, T('Spielsprache', 'Game language'), 20, 'regular', ui.TEXT, anchor='w')
            ctx.dropdown(lx, iy, lw, 52 * s, [n for _, n in LANGS], self.sel_language, pick_lang, size=21)
            ctx.vline(wx - sep, oy, 90 * s, ui.LINE, 0.6)
            ctx.icon(wx + 18 * s, oy + 12 * s, 'chip', 24, ui.TEXT)
            ctx.text(wx + 46 * s, oy + 12 * s, 'Build Workers', 20, 'regular', ui.TEXT, anchor='w')
            workers = [AUTO] + [str(i) for i in (2, 4, 6, 8, 12, 16) if i <= (os.cpu_count() or 8)]
            shown = {AUTO: T('Automatisch', 'Automatic')}
            ctx.dropdown(wx, iy, ww_, 52 * s, [shown.get(v, v) for v in workers], shown.get(self.sel_workers, self.sel_workers),
                         lambda v: pick_workers(AUTO if v == shown[AUTO] else v), size=21)
            # the two progress rows
            ctx.panel(x - 21 * s, py, w + 42 * s, ph, r=18, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE,
                      bw=1.2)
            rows = ((('layers', T('Bereit zum Bauen', 'Ready to build'),
                      T('Das Spiel wird aus deiner NUP-Datei auf diesem PC gebaut.', 'The game is built from your NUP file on this PC.')),
                     ('download', T('Gesamt', 'Overall'),
                      T('Danach bereitet der erste Start die Shader vor.', 'The first start then prepares the shaders.'))))
            rh = ph / 2
            for i, (icon, title, sub) in enumerate(rows):
                ry = py + i * rh
                if i:
                    ctx.hline(x + 14 * s, ry, w - 28 * s, ui.LINE, 0.5)
                ctx.icon_box(x + 15 * s, ry + rh / 2 - 32 * s, 64 * s, icon, 28, ui.ACCENT_HI, r=12)
                ctx.text(x + 106 * s, ry + rh / 2 - 6 * s, title, 22, 'semibold', ui.TEXT, anchor='sw')
                ctx.text(x + 106 * s, ry + rh / 2 + 2 * s, sub, 18, 'regular', '#c3d0ea', anchor='nw')
                bx0 = x + max(w * 0.44, 560 * s)
                ctx.progress(f'bar{i}', bx0, ry + rh / 2 + 4 * s, x + w - 10 * s - bx0, 14 * s, 0.0)
            # disk space | the button
            ctx.hline(x - 21 * s, dv3, w + 42 * s, ui.LINE, 0.5)
            mid = fy + fh / 2
            ctx.icon(x + 12 * s, mid, 'drive', 30, ui.TEXT)
            ctx.text(x + 52 * s, mid, T('Speicherplatz', 'Disk space'), 20, 'regular', ui.TEXT, anchor='w')
            sx0 = x + 208 * s
            text, col = self.space_text()
            free = free_gb(self.dest.get() or self.cfg['game_dir'])
            ctx.progress('space', sx0, mid - 8 * s, 362 * s, 16 * s, min(1.0, NEED_GB / max(free, 1)))
            ctx.text(sx0 + 397 * s, mid, text, 19, 'regular', col, anchor='w', key='space')
            bw = 297 * s
            ctx.button(x + w + 21 * s - bw, fy, bw, fh, T('Update', 'Update') if update else T('Installieren', 'Install'),
                       self.start_build, kind='primary', icon='sync' if update else 'download', size=30, weight='bold', r=16)
        self.show('files', body)

    def space_text(self):
        free = free_gb(self.dest.get() or self.cfg['game_dir'])
        drive = Path(self.dest.get() or '.').anchor.rstrip('\\') or 'C:'
        return (T(f'Benötigt: {NEED_GB},0 GB  •  {drive} hat {free:.0f} GB frei', f'Needs {NEED_GB} GB  •  {drive} has {free:.0f} GB free'),
                '#c3d0ea' if free >= NEED_GB else RED)

    def check_nup(self, f):
        cmd = [str(INSTALL / 'python' / 'python.exe'), '-I', str(INSTALL / 'ocarina_prepare.py'), '--nup', str(f),
               '--dest', str(Path(self.cfg['game_dir'])), '--tools', str(INSTALL), '--check-only']

        def run():
            try:
                out = subprocess.run(cmd, capture_output=True, text=True, encoding='utf-8', errors='replace',
                                     creationflags=NO_WINDOW).stdout
            except OSError as e:
                out = '{"error": "%s"}' % e
            ok = '"error"' not in out and 'recognised' in out or 'supports' in out
            err = next((json.loads(l)['error'] for l in out.splitlines() if l.startswith('{"error"')), '')
            good = ok and not err
            self.nup_status[str(f)] = (T('Unterstützt', 'Supported'), ui.GREEN) if good else \
                (T('Nicht unterstützt', 'Not supported'), RED)
            self.after(0, lambda: self.step == 'files' and self.stage.render())
            if err:
                log(f'nup check {f.name}: {err}')
        threading.Thread(target=run, daemon=True).start()

    def browse(self):
        f = filedialog.askopenfilename(title=T('Deine Ocarina-of-Time-Spieldatei auswählen', 'Select your Ocarina of Time game file'), filetypes=[('NUP', '*.nup')])
        if f:
            self.nup.set(f)
            self.nup_files = [Path(f)] + [x for x in self.nup_files if str(x) != f]
            self.game_files(keep=True)

    def pick_dest(self):
        d = filedialog.askdirectory(title=T('Ordner für das Spiel wählen', 'Choose the game folder'))
        if d:
            self.dest.set(str(Path(d) / 'Ocarina Reborn') if Path(d).name != 'Ocarina Reborn' else d)
            self.stage.render()

    def start_build(self):
        if self.busy:
            return
        nup = self.nup.get()
        if not nup or not Path(nup).is_file():
            return messagebox.showinfo('Ocarina Reborn', T('Bitte zuerst deine .nup-Datei auswählen.', 'Please select your .nup file first.'))
        if free_gb(self.dest.get()) < NEED_GB:
            return messagebox.showerror('Ocarina Reborn', T('Nicht genügend Speicherplatz.', 'Not enough disk space.') +
                                        f'\n\n{T("Benötigt", "Needed")}: {NEED_GB} GB  •  {T("Frei", "Free")}: '
                                        f'{free_gb(self.dest.get()):.0f} GB')
        lang = next((c for c, n in LANGS if n == self.sel_language), 'de')
        w = self.sel_workers
        self.cfg.update(game_dir=self.dest.get(), language=lang, workers='auto' if w == AUTO else w)
        save_settings(self.cfg)
        self.run_build(dict(nup=nup, dest=self.cfg['game_dir'], language=lang, workers=self.cfg['workers']))

    def run_build(self, job):
        """the animated build screen (build_screen.py) over the window; build-state.json marks a build in progress"""
        STATE.write_text(json.dumps(job, indent=2))
        backup_saves(job['dest'], 'before-build')
        log(f'prepare: {"update" if job.get("update") else Path(job["nup"]).name} -> {job["dest"]}')
        src = ['--update'] if job.get('update') else ['--nup', job['nup']]
        cmd = [str(INSTALL / 'python' / 'python.exe'), '-I', str(INSTALL / 'ocarina_prepare.py')] + src + \
              ['--dest', job['dest'], '--tools', str(INSTALL), '--language', job['language'], '--logs', str(DIRS['PrepareLogs'])]
        if job.get('workers', 'auto') != 'auto':
            cmd += ['--jobs', str(job['workers'])]
        if os.environ.get('OCARINA_BUILD_REPLAY'):   # (developer test of the screen: a recorded build.log, no build)
            cmd = [str(INSTALL / 'python' / 'python.exe'), '-I', str(INSTALL / 'ocarina_prepare.py'), '--replay',
                   os.environ['OCARINA_BUILD_REPLAY'], '--speed', os.environ.get('OCARINA_BUILD_REPLAY_SPEED', '40')]
        self.busy = True
        self.step = 'build'

        def done():
            self.busy = False
            STATE.unlink(missing_ok=True)
            log('prepare finished')
            self.route()
            if game_exe(job['dest']).is_file():
                self.play()

        def back():
            self.busy = False
            log('prepare stopped or failed')
            self.route()
        bs = BuildScreen(self, cmd, ASSETS, UI_LANG[0] == 'de', DIRS['Logs'] / f'build-{NOW}.log', done, back, INFO['version'])
        if self.chrome.ok:   # (the build screen fills the window: its top moves the window, the window's buttons float over it)
            bs.c.bind('<Button-1>', lambda e: self.chrome.drag() if e.y < 70 * self.stage.scale(*self.stage.size) else None,
                      add='+')
            self.window_buttons_over(bs.c)

    def window_buttons_over(self, under):
        s = self.stage.scale(self.winfo_width(), self.winfo_height())
        bw, bh = int(56 * s), int(44 * s)
        c = tk.Canvas(self, width=bw * 3, height=bh, bg='#050b1c', highlightthickness=0, bd=0)
        c.place(relx=1.0, x=0, y=0, anchor='ne')
        for i, (name, cmd) in enumerate((('minimize', self.iconify), ('maximize', self.toggle_max), ('close', self.quit_app))):
            r = c.create_rectangle(i * bw, 0, (i + 1) * bw, bh, fill='#050b1c', outline='')
            c.create_text(i * bw + bw / 2, bh / 2, text=ui.GLYPH[name], font=(ui.ICON, -int(15 * s)), fill=ui.SUB)
            c.tag_bind(r, '<Enter>', lambda e, r=r, n=name: c.itemconfig(r, fill='#c42b1c' if n == 'close' else ui.PANEL_HI))
            c.tag_bind(r, '<Leave>', lambda e, r=r: c.itemconfig(r, fill='#050b1c'))
        c.bind('<Button-1>', lambda e: (self.iconify, self.toggle_max, self.quit_app)[min(2, e.x // bw)]())
        tk.Misc.lift(c)   # (a canvas's own lift() raises its items, not the widget)
        self.float_ctl = c

    def resume_page(self, job):
        def restart():
            shutil.rmtree(APP / 'GameBuild', ignore_errors=True)
            self.run_build(job)

        def forget():
            STATE.unlink(missing_ok=True)
            self.game_files()

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (cy, chh), (fy, fh) = layout(ctx, top, [(76, 34, 0), (220, 40, 1), (82, 30, 0)])
            self.heading(ctx, x, hy, T('Unvollständiger Build gefunden.', 'Incomplete build found.'),
                         T('Der letzte Build wurde nicht beendet.', 'The last build did not finish.'), icon='refresh', w=w)
            ctx.panel(x, cy, w, chh, r=16, fill=ui.PANEL, alpha=0.85, border=ui.LINE)
            for i, (icon, title, text) in enumerate((
                    ('play', T('Fortsetzen', 'Resume'), T('Startet ihn mit denselben Einstellungen neu; schon fertige Teile nutzt '
                                                          'der Build wieder, wo das sicher ist.', 'Starts it again with the same '
                                                          'settings; the build reuses finished parts where that is safe.')),
                    ('refresh', T('Neu starten', 'Restart'), T('Verwirft die Zwischendateien und baut von vorn.',
                                                               'Throws the intermediate files away and builds from the start.')),
                    ('close', T('Verwerfen', 'Discard'), T('Zurück zur Auswahl der Spieldatei.', 'Back to choosing the game file.')))):
                ry = cy + 30 * s + i * (chh - 60 * s) / 3
                ctx.icon(x + 50 * s, ry + 20 * s, icon, 24, ui.ACCENT_HI)
                ctx.text(x + 90 * s, ry + 4 * s, title, 21, 'semibold', ui.TEXT)
                ctx.text(x + 90 * s, ry + 34 * s, text, 18, 'regular', ui.SUB, width=w - 130 * s)
            bw = 297 * s
            ctx.button(x + w - bw, fy, bw, fh, T('Fortsetzen', 'Resume'), lambda: self.run_build(job), kind='primary',
                       icon='play', size=28, weight='bold', r=16)
            ctx.button(x, fy + 14 * s, 220 * s, fh - 28 * s, T('Neu starten', 'Restart'), restart, icon='refresh')
            ctx.button(x + 240 * s, fy + 14 * s, 200 * s, fh - 28 * s, T('Verwerfen', 'Discard'), forget, icon='close')
        self.show('build', body)

    def update_page(self):
        """a newer Ocarina Reborn is installed than the one that built the game: rebuild from the game files the folder
        keeps (no .nup; make_game.py --update compiles only what changed)"""
        job = dict(update=True, dest=self.cfg['game_dir'], language=self.cfg.get('language', 'de'),
                   workers=self.cfg.get('workers', 'auto'))
        game = Path(self.cfg['game_dir'])
        saves = sm.has_saves(game)

        def change():
            d = filedialog.askdirectory(title=T('Backup-Ordner wählen', 'Choose the backup folder'), initialdir=str(backup_root()))
            if d:
                self.cfg['backup_dir'] = d
                save_settings(self.cfg)
                self.stage.render()

        def with_backup():
            if sm.has_saves(game):
                try:
                    dst = sm.backup(game, backup_root(), 'Before-Update', 'before-update', INFO.get('version', ''))
                    log(f'saves backed up to {dst}')
                except (OSError, sm.SaveError) as e:
                    return messagebox.showerror('Ocarina Reborn', T('Das Backup ist fehlgeschlagen, das Update wurde abgebrochen:\n',
                                                                    'The backup failed, the update was cancelled:\n') + str(e))
            self.run_build(job)

        def later():
            self.update_later = True
            self.ready()

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (dv, _), (ay, ah), (fy, fh) = layout(ctx, top, [(76, 34, 0), (0, 27, 0.15), (300, 30, 1), (82, 30, 0)])
            self.heading(ctx, x, hy, T('Update verfügbar', 'Update available'),
                         T('Eine neue Version von Ocarina Reborn ist installiert. Das Spiel wird mit deinen schon vorhandenen '
                           'Spieldaten neu gebaut, die .nup wird nicht gebraucht.', 'A new version of Ocarina Reborn is installed. '
                           'The game is rebuilt from the game data it already has; the .nup is not needed.'), icon='sync', w=w)
            ctx.hline(x, dv, w, ui.LINE, 0.55)
            half = (w - 24 * s) / 2 if saves else w
            ctx.panel(x, ay, half, ah, r=16, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE)
            ctx.icon_box(x + 28 * s, ay + 28 * s, 64 * s, 'layers', 28)
            ctx.text(x + 116 * s, ay + 34 * s, T('Was passiert', 'What happens'), 22, 'semibold')
            ctx.text(x + 116 * s, ay + 70 * s, T(
                'Nur Geändertes wird neu kompiliert. Danach bereitet der erste Start die Shader vor. Dein Spielordner und '
                'deine Einstellungen bleiben erhalten.', 'Only what changed is compiled again. The first start then prepares '
                'the shaders. Your game folder and your settings stay as they are.'), 19, 'regular', '#c3d0ea',
                width=half - 150 * s)
            if saves:
                bx = x + half + 24 * s
                ctx.panel(bx, ay, half, ah, r=16, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE)
                ctx.icon_box(bx + 28 * s, ay + 28 * s, 64 * s, 'save', 28)
                ctx.text(bx + 116 * s, ay + 34 * s, T('Deine Spielstände', 'Your save data'), 22, 'semibold')
                ctx.text(bx + 116 * s, ay + 70 * s, T('Sie bleiben beim Update erhalten. Ein Backup vorher ist trotzdem sicherer.',
                                                      'It stays as it is during the update. Making a backup first is still safer.'),
                         19, 'regular', '#c3d0ea', width=half - 150 * s)
                ctx.text(bx + 116 * s, ay + ah - 110 * s, T('Backup-Ordner', 'Backup location'), 16, 'semibold', ui.SUB)
                ctx.text(bx + 116 * s, ay + ah - 84 * s, str(backup_root()), 18, 'regular', ui.TEXT, width=half - 150 * s)
                ctx.button(bx + 116 * s, ay + ah - 52 * s, 210 * s, 36 * s, T('Ordner ändern', 'Change location'), change,
                           kind='pill', size=17, icon='folder')
            bw = 380 * s if saves else 297 * s
            ctx.button(x + w - bw, fy, bw, fh, T('Sichern und aktualisieren', 'Back up and update') if saves else
                       T('Aktualisieren', 'Update'), with_backup, kind='primary', icon='sync', size=26 if saves else 30,
                       weight='bold', r=16)
            lx = x
            if saves:
                tw = ctx.text_width(T('Ohne Backup aktualisieren', 'Update without backup'), 19, 'semibold') + 50 * s
                ctx.button(x + w - bw - 20 * s - tw, fy + 14 * s, tw, fh - 28 * s, T('Ohne Backup aktualisieren',
                           'Update without backup'), lambda: self.run_build(job))
            ctx.button(lx, fy + 14 * s, 170 * s, fh - 28 * s, T('Später', 'Later'), later, icon='clock')
        self.show('files', body)

    # ---- play
    def ready(self):
        devs = audio_devices()
        self.audio_devs = devs

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (dv, _), (cy, chh), (dv2, _), (fy, fh) = layout(
                ctx, top, [(76, 34, 0), (0, 27, 0.15), (420, 30, 1), (0, 32, 0.15), (82, 7, 0)])
            self.heading(ctx, x, hy, T('Ocarina Reborn ist bereit.', 'Ocarina Reborn is ready.'),
                         T('Beim ersten Start werden die Shader vorbereitet (einige Minuten). Danach geht es schneller.',
                           'The first start prepares the shaders (several minutes). Later starts are faster.'), icon='play', w=w)
            px = x + w
            if self.news:   # (what the newest release brought, from the site's GitHub)
                label = T(f'Neu in {self.news[0]}', f'New in {self.news[0]}')
                nw = ctx.text_width(label, 17, 'semibold') + 64 * s
                px -= nw
                ctx.button(px, hy + 18 * s, nw, 40 * s, label, self.show_news, kind='pill', icon='info', size=17)
                px -= 12 * s
            warn = self.facts and advisor.pc_warnings(self.facts, self.active_gpu, UI_LANG[0] == 'de')
            if self.diag or warn or self.facts:
                bad = warn or any(k == 'warn' for k, _ in self.diag)
                label = T('Leistung: Hinweise', 'Performance: tips') if bad else T('Letzte Sitzung', 'Last session')
                nw = ctx.text_width(label, 17, 'semibold') + 64 * s
                px -= nw
                ctx.button(px, hy + 18 * s, nw, 40 * s, label, self.show_diagnosis, kind='pill',
                           icon='warning' if bad else 'check', size=17, color=ui.GOLD if bad else None)
            ctx.hline(x, dv, w, ui.LINE, 0.55)
            gap = 24 * s
            lw = (w - gap) * 0.56
            rw = w - gap - lw
            # left: what the game starts with
            ctx.panel(x, cy, lw, chh, r=16, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE)
            ctx.text(x + 30 * s, cy + 26 * s, T('SPIELSTART', 'GAME START'), 17, 'semibold', ui.SUB)
            fields = ((('globe', T('Spielsprache (Text)', 'Game language (text)'), 'language', [n for _, n in LANGS],
                        dict(LANGS).get(self.cfg['language'], 'Deutsch')),
                       ('speaker', T('Audioausgabe', 'Audio output'), 'audio', [T('Windows-Standard', 'Windows default')] + devs,
                        devs[int(self.cfg['audio'])] if self.cfg.get('audio', 'default') != 'default' and
                        int(self.cfg['audio']) < len(devs) else T('Windows-Standard', 'Windows default')),
                       ('settings', T('Launcher-Sprache', 'Launcher language'), 'ui', ['Deutsch', 'English'],
                        'Deutsch' if UI_LANG[0] == 'de' else 'English')))
            room = chh - 70 * s
            step = room / 3
            for i, (icon, title, key, values, cur) in enumerate(fields):
                fy0 = cy + 64 * s + i * step
                ctx.icon(x + 44 * s, fy0 + 12 * s, icon, 22, ui.TEXT)
                ctx.text(x + 72 * s, fy0 + 12 * s, title, 19, 'regular', ui.TEXT, anchor='w')
                ctx.dropdown(x + 30 * s, fy0 + 32 * s, lw - 60 * s, min(52 * s, step - 44 * s), values, cur,
                             lambda v, k=key: self.set_option(k, v), size=20)
            # right: the game's own pages
            rx = x + lw + gap
            ctx.panel(rx, cy, rw, chh, r=16, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE)
            ctx.text(rx + 30 * s, cy + 26 * s, T('SPIEL', 'GAME'), 17, 'semibold', ui.SUB)
            tiles = (('save', T('Spielstände', 'Save data'), T('Backups, Wiederherstellen, Import', 'Backups, restore, import'),
                      self.saves_page),
                     ('cube', 'Mods', T('An/aus, aus ZIP oder Ordner hinzufügen', 'On/off, add from a ZIP or folder'),
                      self.mods_page),
                     ('settings', T('Einstellungen', 'Settings'), T('Grafik, Steuerung, Audio, Schwierigkeit, Cheats', 'Graphics, controls, audio, difficulty, cheats'),
                      self.settings_page),
                     ('wrench', 'Reborn Auto', T('Messen, Vorschlag, Vergleich', 'Measure, suggest, compare') +
                      (T('  ·  zweiter Lauf offen', '  ·  second run pending')
                       if (self.cfg.get('reborn_auto') or {}).get('step') == 'compare' else ''), self.reborn_auto),
                     ('layers', T('Shader vorbereiten', 'Prepare shaders'), T('Weniger Ruckler, z. B. nach Treiber-Update',
                                                                              'Less stutter, e.g. after a driver update'),
                      self.prepare_shaders),
                     ('refresh', T('Spiel neu bauen', 'Rebuild game'), T('Aus deiner NUP-Datei, neu', 'From your NUP file, again'),
                      self.game_files))
            th = (chh - 80 * s) / len(tiles)
            for i, (icon, title, sub, cmd) in enumerate(tiles):
                ty = cy + 62 * s + i * th
                tx, tw_, tl = rx + 20 * s, rw - 40 * s, th - 12 * s

                def look(c, on, tx=tx, ty=ty, tw_=tw_, tl=tl):
                    c.panel(tx, ty, tw_, tl, r=12, fill=ui.PANEL_HI if on else ui.CELL, alpha=0.9,
                            border=ui.LINE_HI if on else ui.LINE, balpha=1.0, glow=ui.GLOW if on else None, gr=10, ga=0.15)
                look(ctx, False)
                isz = min(56 * s, tl - 16 * s)
                ctx.icon_box(tx + 14 * s, ty + tl / 2 - isz / 2, isz, icon, 24, ui.ACCENT_HI, r=10, fill=ui.PANEL)
                if tl >= 62 * s:   # (room for two lines)
                    ctx.text(tx + 30 * s + isz, ty + tl / 2 - 2 * s, title, 21, 'semibold', ui.TEXT, anchor='sw')
                    ctx.text(tx + 30 * s + isz, ty + tl / 2 + 2 * s, sub, 17, 'regular', ui.SUB, anchor='nw')
                else:   # (six tiles in a small window: the title, smaller, and the line under it as its hover help)
                    ctx.text(tx + 30 * s + isz, ty + tl / 2, title, 19, 'semibold', ui.TEXT, anchor='w')
                ctx.icon(tx + tw_ - 30 * s, ty + tl / 2, 'right', 16, ui.SUB)
                ctx.hot(tx, ty, tw_, tl, cmd, hover=look)
            # bottom: the support tools, quiet; Play, bright
            ctx.hline(x, dv2, w, ui.LINE, 0.5)
            mid = fy + fh / 2
            ctx.text(x + 4 * s, mid, T('DIAGNOSE', 'DIAGNOSTICS'), 15, 'semibold', ui.MUTED, anchor='w')
            tx = x + 4 * s + ctx.text_width(T('DIAGNOSE', 'DIAGNOSTICS'), 15, 'semibold') + 20 * s
            for icon, text, cmd in (('logs', T('Logs öffnen', 'Open logs'), lambda: os.startfile(DIRS['Logs'])),
                                    ('wrench', T('Diagnose-Tools', 'Diagnostic tools'), self.diagnostic_tools),
                                    ('bug', T('Debug-Paket erstellen', 'Create debug package'), self.debug_package)):
                bw = ctx.text_width(text, 17) + 60 * s
                ctx.button(tx, mid - 21 * s, bw, 42 * s, text, cmd, kind='quiet', icon=icon, size=17, weight='regular')
                tx += bw + 8 * s
            ctx.text(x + 4 * s, mid + 34 * s, self.cfg['game_dir'], 15, 'regular', ui.MUTED, anchor='w')
            bw = 297 * s
            ctx.button(x + w - bw, fy, bw, fh, T('Spielen', 'Play'), self.play, kind='primary', icon='play', size=30,
                       weight='bold', r=16)
        self.show('play', body)

    def saves_page(self):
        """the player's save data: backups (make, restore, where they go), import from an emulator or another install, and the
        folders themselves. Every restore and import backs the live save up first (save_manager.py)"""
        game = Path(self.cfg['game_dir'])
        self.saves_sel = None
        self.saves_status = ('', ui.GOLD)
        if sm.game_running():
            self.saves_status = (T('Das Spiel läuft gerade. Wiederherstellen und Importieren geht erst, wenn es geschlossen ist.',
                                   'The game is running. Restoring and importing work once it is closed.'), RED)

        def status(text, col=ui.GOLD, redraw=True):
            self.saves_status = (text, col)
            if redraw:
                self.stage.render()
            else:
                self.stage.set_text('status', text, col)
                self.update_idletasks()

        def make_backup():
            if not sm.has_saves(game):
                return status(T('Es gibt noch keine Spielstände zum Sichern.', 'There is no save data to back up yet.'), RED)
            status(T('Backup wird erstellt …', 'Making the backup …'), ui.SUB, redraw=False)
            try:
                dst = sm.backup(game, backup_root(), 'Manual', 'manual', INFO.get('version', ''))
                log(f'manual backup: {dst}')
                status(T('Backup erstellt und geprüft: ', 'Backup made and verified: ') + str(dst))
            except (OSError, sm.SaveError) as e:
                status(str(e), RED)

        def restore():
            if not self.saves_sel:
                return status(T('Wähle zuerst ein Backup aus der Liste.', 'Pick a backup from the list first.'), RED)
            p = self.saves_sel
            if not messagebox.askyesno('Ocarina Reborn', T(
                    f'Diesen Spielstand wiederherstellen?\n\n{p.name}\n\nDein aktueller Stand wird vorher automatisch gesichert.',
                    f'Restore this save?\n\n{p.name}\n\nYour current save is backed up automatically first.')):
                return
            status(T('Wird wiederhergestellt …', 'Restoring …'), ui.SUB, redraw=False)
            try:
                safety = sm.restore(game, p, backup_root(), INFO.get('version', ''))
                log(f'restored {p}, safety backup {safety}')
                status(T('Wiederhergestellt. Dein vorheriger Stand liegt als Backup unter ',
                         'Restored. Your previous save is backed up as ') + str(safety))
            except (OSError, sm.SaveError) as e:
                status(T('Nicht wiederhergestellt, dein Spielstand ist unverändert: ',
                         'Not restored, your save is unchanged: ') + str(e), RED)

        def do_import(source, label):
            status(T('Wird importiert …', 'Importing …'), ui.SUB, redraw=False)
            try:
                info, safety = sm.import_save(game, source, backup_root(), INFO.get('version', ''))
                log(f'imported {label}: {len(info["slots"])} slots from {source}')
                status(T(f'{len(info["slots"])} Speicherplätze importiert. Dein vorheriger Stand liegt als Backup unter ',
                         f'Imported {len(info["slots"])} save slots. Your previous save is backed up as ') + str(safety))
            except (OSError, sm.SaveError) as e:
                status(T('Nicht importiert, dein Spielstand ist unverändert: ',
                         'Not imported, your save is unchanged: ') + str(e), RED)

        def import_auto():
            status(T('Es wird gesucht …', 'Looking …'), ui.SUB, redraw=False)
            found = sm.auto_detect()
            if not found:
                return status(T('Keine Spielstände dieses Spiels in den üblichen Emulator-Ordnern gefunden. Nimm „Ordner“.',
                                'No save data of this game found in the usual emulator folders. Use "Folder".'), RED)
            label, folder = found[0]
            if not messagebox.askyesno('Ocarina Reborn', T(f'Spielstand aus {label} importieren?\n\n{folder}',
                                                           f'Import the save from {label}?\n\n{folder}')):
                return status('', ui.SUB)
            do_import(folder, label)

        def import_folder():
            d = filedialog.askdirectory(title=T('Spielstand-Ordner wählen', 'Choose the save folder'))
            if d:
                do_import(d, 'folder')

        def import_file():
            f = filedialog.askopenfilename(title=T('Spielstand-Datei oder ZIP wählen', 'Choose a save file or ZIP'),
                                           filetypes=[(T('Spielstand oder ZIP', 'Save or ZIP'), '*.zip *.sav'), ('*', '*.*')])
            if f:
                do_import(f, 'file')

        def change_dir():
            d = filedialog.askdirectory(title=T('Backup-Ordner wählen', 'Choose the backup folder'), initialdir=str(backup_root()))
            if d:
                self.cfg['backup_dir'] = d
                save_settings(self.cfg)
                log(f'backup folder: {d}')
                self.stage.render()

        def open_saves():
            if sm.save_root(game).is_dir():
                os.startfile(sm.save_root(game))
            else:
                status(T('Es gibt noch keine Spielstände.', 'There is no save data yet.'), RED)

        def open_backups():
            backup_root().mkdir(parents=True, exist_ok=True)
            os.startfile(backup_root())

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (ly, _), (ty, th), (ay, _), (sy, _), (fy, fh) = layout(
                ctx, top, [(76, 34, 0), (36, 22, 0), (300, 14, 1), (48, 18, 0), (24, 12, 0), (60, 18, 0)])
            self.heading(ctx, x, hy, T('Spielstände', 'Save data'),
                         T('Backups deiner Spielstände, Wiederherstellen und Importieren. Vor jedem Wiederherstellen und '
                           'Importieren wird dein aktueller Stand automatisch gesichert.',
                           'Backups of your save data, restoring and importing. Your current save is backed up automatically '
                           'before every restore and import.'), icon='save', w=w)
            ctx.icon(x + 14 * s, ly + 18 * s, 'folder', 20, ui.SUB)
            ctx.text(x + 40 * s, ly + 18 * s, T('Backup-Ordner: ', 'Backup location: ') + str(backup_root()), 18, 'regular',
                     ui.SUB, anchor='w')
            bx = x + w
            for text, cmd in reversed(((T('Spielstand-Ordner', 'Save folder'), open_saves),
                                       (T('Backup-Ordner', 'Backup folder'), open_backups),
                                       (T('Ändern', 'Change'), change_dir))):
                bw = ctx.text_width(text, 17, 'semibold') + 36 * s
                bx -= bw
                ctx.button(bx, ly, bw, 36 * s, text, cmd, kind='pill', size=17)
                bx -= 10 * s
            # the list
            ctx.panel(x, ty, w, th, r=16, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE)
            cols = ((T('Zeitpunkt', 'When'), 0.0), (T('Art', 'Kind'), 0.30), (T('Grund', 'Reason'), 0.50),
                    (T('Dateien', 'Files'), 0.74), (T('Größe', 'Size'), 0.86))
            iw = w - 48 * s
            hh = 46 * s
            for name, fx in cols:
                ctx.text(x + 24 * s + fx * iw, ty + hh / 2, name, 16, 'semibold', ui.SUB, anchor='w')
            ctx.hline(x + 12 * s, ty + hh, w - 24 * s, ui.LINE, 0.6)
            backups = sm.list_backups(backup_root())
            rh = 42 * s
            fit = max(1, int((th - hh - 10 * s) // rh))
            if not backups:
                ctx.text(x + 24 * s, ty + hh + 30 * s, T('Noch keine Backups.', 'No backups yet.'), 19, 'regular', ui.SUB,
                         anchor='w')
            for i, bk in enumerate(backups[:fit]):
                ry = ty + hh + 5 * s + i * rh
                on = self.saves_sel == bk['path']
                if on:
                    ctx.panel(x + 10 * s, ry, w - 20 * s, rh - 4 * s, r=8, fill=ui.ACCENT, fill2=ui.ACCENT_LO, alpha=0.9,
                              border=ui.ACCENT_HI)
                vals = (bk['timestamp'].replace('T', '  '), bk['kind'], bk['reason'][:28], str(bk['files']),
                        f"{bk['size'] / 1048576:.1f} MB")
                for (_, fx), v in zip(cols, vals):
                    ctx.text(x + 24 * s + fx * iw, ry + rh / 2 - 2 * s, v, 17, 'regular', ui.TEXT if on else '#c3d0ea', anchor='w')

                def pick(p=bk['path']):
                    self.saves_sel = p
                    self.stage.render()

                def look(c, hov, ry=ry, on=on):
                    if hov and not on:
                        c.panel(x + 10 * s, ry, w - 20 * s, rh - 4 * s, r=8, fill=ui.PANEL_HI, alpha=0.8, border=ui.LINE)
                ctx.hot(x + 10 * s, ry, w - 20 * s, rh - 4 * s, pick, hover=look)
            if len(backups) > fit:
                ctx.text(x + w - 24 * s, ty + th - 18 * s, T(f'+ {len(backups) - fit} ältere', f'+ {len(backups) - fit} older'),
                         15, 'regular', ui.MUTED, anchor='e')
            # actions
            ax = x
            for text, icon, cmd, kind in ((T('Backup erstellen', 'Create backup'), 'save', make_backup, 'secondary'),
                                          (T('Wiederherstellen', 'Restore'), 'history', restore, 'secondary'),
                                          (T('Import: suchen', 'Import: auto detect'), 'import_', import_auto, 'secondary'),
                                          (T('Import: Ordner', 'Import: folder'), 'folder', import_folder, 'secondary'),
                                          (T('Import: Datei/ZIP', 'Import: file/ZIP'), 'file', import_file, 'secondary')):
                bw = ctx.text_width(text, 18, 'semibold') + 70 * s
                ctx.button(ax, ay, bw, 48 * s, text, cmd, kind=kind, icon=icon, size=18)
                ax += bw + 12 * s
            text, col = self.saves_status
            ctx.text(x + 4 * s, sy + 12 * s, text, 18, 'regular', col, anchor='w', key='status', width=w)
            ctx.hline(x, fy - 12 * s, w, ui.LINE, 0.5)
            ctx.button(x, fy + 6 * s, 170 * s, fh - 12 * s, T('Zurück', 'Back'), self.ready, icon='back', size=19)
        self.show('play', body)

    def mods_page(self, keep_status=False):
        """the mods (mods_manager.py, the engine's host/mods.c): the list, on and off, add from a folder or a .zip, the folder.
        A change applies at the next start of the game (the engine indexes the mods once, at its start)"""
        game = Path(self.cfg['game_dir'])
        root = mods_manager.mods_root(game)
        if not keep_status:
            self.mods_status = ('', ui.SUB)

        def status(text, col=ui.SUB):
            self.mods_status = (text, col)
            self.mods_page(True)

        def toggle(m):
            try:
                mods_manager.set_enabled(m['path'], not m['enabled'])
                log(f"mods: {m['name']} {'off' if m['enabled'] else 'on'}")
                status(T('Gilt ab dem nächsten Spielstart.', 'Applies at the next start of the game.'), ui.GOLD)
            except OSError as e:
                status(str(e), RED)

        def add(source):
            if not source:
                return
            try:
                names = mods_manager.add_mod(source, root)
                log(f'mods: added {names} from {source}')
                status(T('Hinzugefügt: ', 'Added: ') + ', '.join(names) + T('. Gilt ab dem nächsten Spielstart.',
                                                                           '. Applies at the next start of the game.'), ui.GOLD)
            except (OSError, ValueError, zipfile.BadZipFile) as e:
                status(str(e), RED)

        def open_root():
            root.mkdir(parents=True, exist_ok=True)
            os.startfile(root)

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (ty, th), (ay, _), (sy, _), (fy, fh) = layout(
                ctx, top, [(76, 34, 0), (300, 22, 1), (48, 18, 0), (24, 12, 0), (60, 18, 0)])
            self.heading(ctx, x, hy, 'Mods',
                         T('RomFS-Mods im Emulator-Format (Ordner mit „romfs“). Aus- und Einschalten, Hinzufügen aus Ordner oder '
                           'ZIP. Gilt ab dem nächsten Spielstart. exefs-Patches werden nicht angewendet.',
                           'RomFS mods in the emulator layout (a folder with "romfs"). Turn them on and off, add from a folder or '
                           'a ZIP. Applies at the next start. exefs patches are not applied.'), icon='layers', w=w)
            ctx.panel(x, ty, w, th, r=16, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE)
            cols = (('', 0.0), ('Mod', 0.05), (T('Dateien', 'Files'), 0.62), (T('Größe', 'Size'), 0.74), ('', 0.86))
            iw = w - 48 * s
            hh = 46 * s
            for name, fx in cols:
                ctx.text(x + 24 * s + fx * iw, ty + hh / 2, name, 16, 'semibold', ui.SUB, anchor='w')
            ctx.hline(x + 12 * s, ty + hh, w - 24 * s, ui.LINE, 0.6)
            mods = mods_manager.list_mods(root)
            rh = 46 * s
            fit = max(1, int((th - hh - 10 * s) // rh))
            if not mods:
                ctx.text(x + 24 * s, ty + hh + 30 * s, T('Noch keine Mods. „Mod hinzufügen“ oder den Ordner öffnen.',
                                                         'No mods yet. "Add mod" or open the folder.'), 19, 'regular', ui.SUB, anchor='w')
            for i, m in enumerate(mods[:fit]):
                ry = ty + hh + 5 * s + i * rh
                d = 26 * s
                ctx.check(x + 24 * s, ry + (rh - d) / 2 - 2 * s, d, m['enabled'], lambda m=m: toggle(m))
                ctx.hot(x + 18 * s, ry, 40 * s, rh - 4 * s, lambda m=m: toggle(m))
                col = ui.TEXT if m['enabled'] else ui.MUTED
                ctx.text(x + 24 * s + 0.05 * iw, ry + rh / 2 - 2 * s, m['name'], 18, 'semibold' if m['enabled'] else 'regular',
                         col, anchor='w', width=0.55 * iw)
                ctx.text(x + 24 * s + 0.62 * iw, ry + rh / 2 - 2 * s, str(m['files']), 17, 'regular', col, anchor='w')
                ctx.text(x + 24 * s + 0.74 * iw, ry + rh / 2 - 2 * s, f"{m['bytes'] / 1048576:.1f} MB", 17, 'regular', col,
                         anchor='w')
                note = T('nur exefs: wirkt nicht', 'exefs only: no effect') if not m['romfs'] else (
                    T('aus', 'off') if not m['enabled'] else '')
                ctx.text(x + 24 * s + 0.86 * iw, ry + rh / 2 - 2 * s, note, 15, 'regular', ui.MUTED, anchor='w')
            if len(mods) > fit:
                ctx.text(x + w - 24 * s, ty + th - 18 * s, T(f'+ {len(mods) - fit} weitere (Ordner öffnen)',
                                                             f'+ {len(mods) - fit} more (open the folder)'), 15, 'regular', ui.MUTED,
                         anchor='e')
            ax = x
            for text, icon, cmd in ((T('Mod hinzufügen (ZIP)', 'Add mod (ZIP)'), 'file',
                                     lambda: add(filedialog.askopenfilename(title='Mod (.zip)', filetypes=[('ZIP', '*.zip')]))),
                                    (T('Mod hinzufügen (Ordner)', 'Add mod (folder)'), 'folder',
                                     lambda: add(filedialog.askdirectory(title=T('Mod-Ordner wählen', 'Choose the mod folder')))),
                                    (T('Mod-Ordner öffnen', 'Open mods folder'), 'folder_open', open_root)):
                bw = ctx.text_width(text, 18, 'semibold') + 70 * s
                ctx.button(ax, ay, bw, 48 * s, text, cmd, kind='secondary', icon=icon, size=18)
                ax += bw + 12 * s
            text, col = self.mods_status
            ctx.text(x + 4 * s, sy + 12 * s, text, 18, 'regular', col, anchor='w', key='status', width=w)
            ctx.hline(x, fy - 12 * s, w, ui.LINE, 0.5)
            ctx.button(x, fy + 6 * s, 170 * s, fh - 12 * s, T('Zurück', 'Back'), self.ready, icon='back', size=19)
        self.show('play', body)

    def prepare_classic_voice(self, age, tab):
        if self.busy:
            return
        pack = filedialog.askopenfilename(
            title=T('Eigene Stimmen-ZIP auswählen', 'Select your own voice ZIP'),
            filetypes=[('Voice ZIP', '*.zip')])
        if not pack:
            return
        game = Path(self.cfg['game_dir'])
        self.busy = True
        result = queue.Queue()

        def work():
            try:
                count = classic_voices.prepare(game, age, pack)
                result.put((count, None))
            except Exception as e:
                result.put((0, str(e)))

        def poll():
            try:
                count, error = result.get_nowait()
            except queue.Empty:
                return self.after(200, poll)
            self.busy = False
            if error:
                log('classic voices: preparation failed: ' + error)
                self.settings_status = (T('Vorbereitung fehlgeschlagen.', 'Preparation failed.'), RED)
                messagebox.showerror('Classic voices', error)
            else:
                self.pending_settings['classic_voice_' + age] = 1
                log(f'classic voices: ready {age}, {count} gameplay events')
                self.settings_status = (T('Klassische Stimme bereit. Zum Aktivieren speichern.',
                                          'Classic voice ready. Save to enable.'), ui.GOLD)
            self.settings_page(tab, True)

        def body(ctx, top):
            x, w = self.content(ctx)
            self.heading(ctx, x, top + 34 * ctx.s, T('Klassische Stimmen', 'Classic voices'),
                         T('Deine Stimmen-Datei wird vorbereitet. Beim ersten Mal kann das etwa eine Minute dauern …',
                           'Preparing your selected voice file. The first time can take about a minute …'), icon='settings', w=w)
        self.show('play', body)
        threading.Thread(target=work, daemon=True).start()
        poll()

    def settings_page(self, tab=0, keep_status=False):
        """the game's settings as a PC game has them: tabs (Display, Quality, Performance, Advanced, Difficulty), each row the
        in-game menu's own key in its options file (game_settings.py), a line on what the row under the cursor does and what it
        costs; Save writes only what changed, Reset gives the game its own defaults back"""
        game = Path(self.cfg['game_dir'])
        de = UI_LANG[0] == 'de'
        cur = game_settings.read(game)
        names = [d if de else e for d, e, _ in game_settings.SECTIONS] + [T('Schwierigkeit', 'Difficulty')] + ['Cheats']
        if not hasattr(self, 'pending_settings'):
            self.pending_settings = {}   # (choices made on other tabs, not saved yet: kept while the tabs change)
        if not keep_status:
            self.settings_status = ('', ui.GOLD)
        if self.pending_settings and not self.settings_status[0]:
            self.settings_status = (T('Nicht gespeichert', 'Not saved yet'), ui.SUB)
        costs = {'low': (T('GERINGE LEISTUNGSKOSTEN', 'LOW PERFORMANCE COST'), ui.GREEN),
                 'medium': (T('MITTLERE LEISTUNGSKOSTEN', 'MEDIUM PERFORMANCE COST'), GOLD),
                 'high': (T('HOHE LEISTUNGSKOSTEN', 'HIGH PERFORMANCE COST'), '#ff8a5c')}

        def explain(label, text, cost):
            self.stage.set_text('help_title', label + ('   •   ' + costs[cost][0] if cost else ''),
                                costs[cost][1] if cost else ui.TEXT)
            self.stage.set_text('help_text', text)

        def changed(key, v, was):
            if key in classic_voices.KEYS and v == 1:
                self.prepare_classic_voice(key.removeprefix('classic_voice_'), tab)
                return
            if v == was:
                self.pending_settings.pop(key, None)
            else:
                self.pending_settings[key] = v
            self.settings_status = (T('Nicht gespeichert', 'Not saved yet'), ui.SUB)
            self.settings_page(tab, True)   # (the rows built again: they show the choice just made, not the file's)

        def save():
            if self.busy:
                return
            changes = {k: v for k, v in self.pending_settings.items() if k not in LAUNCHER_KEYS + classic_voices.KEYS}
            for key in LAUNCHER_KEYS:
                if key in self.pending_settings:
                    self.cfg[key] = self.pending_settings[key]
            save_settings(self.cfg)
            try:
                # Validate every choice before changing either age. Folder state is
                # authoritative, so switches also reflect changes on the Mods page.
                for age in classic_voices.AGES:
                    key = 'classic_voice_' + age
                    if self.pending_settings.get(key) and not classic_voices.status(game, age)['installed']:
                        raise ValueError(T('Bitte die klassische Stimme erneut auswählen, damit sie vorbereitet wird.',
                                           'Please select the classic voice again to prepare it.'))
                for age in classic_voices.AGES:
                    key = 'classic_voice_' + age
                    if key in self.pending_settings:
                        classic_voices.set_enabled(game, age, self.pending_settings[key])
                if changes:
                    game_settings.write(game, changes)
                log(f'settings saved: {self.pending_settings}')
                self.pending_settings = {}
                self.settings_status = (T('Gespeichert. Gilt ab dem nächsten Spielstart.', 'Saved. Applies at the next start.'), ui.GOLD)
            except (OSError, ValueError) as e:
                self.settings_status = (str(e), RED)
            self.settings_page(tab, True)

        def reset():
            if not messagebox.askyesno('Ocarina Reborn', T(
                    'Alle Grafikeinstellungen auf die Standardwerte des Spiels zurücksetzen?\n'
                    'Steuerung, Audio, Spielstände und Schwierigkeit bleiben unverändert.',
                    'Reset every graphics setting to the game\'s defaults?\n'
                    'Controls, audio, saves and difficulty stay as they are.')):
                return
            try:
                game_settings.reset(game)
                self.pending_settings = {k: v for k, v in self.pending_settings.items() if k in LAUNCHER_KEYS + classic_voices.KEYS}
                log('graphics settings reset to the game\'s defaults')
                self.settings_status = ('', ui.GOLD)
                self.settings_page(tab, True)
            except OSError as e:
                self.settings_status = (str(e), RED)
                self.stage.render()

        def back():
            self.pending_settings = {}
            self.settings_status = ('', ui.GOLD)
            self.ready()

        def choose_tunic(hex_input=False):
            current = tunic_colors.hex_color(cur | self.pending_settings)
            if hex_input:
                selected = simpledialog.askstring(T('Tunika-Farbe', 'Tunic color'),
                    T('HEX-Farbe, z. B. #5080FF:', 'Hex color, e.g. #5080FF:'), initialvalue=current, parent=self)
            else:
                _, selected = colorchooser.askcolor(color=current, title=T('Tunika-Farbe', 'Tunic color'), parent=self)
            if selected is None:
                return
            try:
                values = tunic_colors.from_hex(selected)
            except ValueError:
                messagebox.showerror(T('Tunika-Farbe', 'Tunic color'),
                    T('Bitte sechs HEX-Zeichen eingeben, z. B. #5080FF.', 'Enter six hex digits, e.g. #5080FF.'), parent=self)
                return
            self.pending_settings.update(values)
            self.settings_status = (T('Nicht gespeichert', 'Not saved yet'), ui.SUB)
            self.settings_page(tab, True)

        def choose_amiibo(remove=False):
            if self.busy:
                return
            try:
                if remove:
                    amiibo.clear(game)
                    message = T('amiibo entfernt.', 'Amiibo removed.')
                else:
                    selected = filedialog.askopenfilename(parent=self,
                        title=T('Eigene amiibo-Datei auswählen', 'Select your amiibo file'),
                        filetypes=[('amiibo (.bin)', '*.bin')])
                    if not selected:
                        return
                    amiibo.select(game, selected)
                    message = T('Bereit für den nächsten amiibo-Scan im Spiel.', 'Ready for the next in-game amiibo scan.')
                self.settings_status = (message, ui.GOLD)
            except (OSError, ValueError) as e:
                self.settings_status = (str(e), RED)
            self.settings_page(tab, True)

        # the rows of this tab: (key, name, help, cost, labels, current label, pick)
        rows = []
        if tab < len(game_settings.SECTIONS):
            for key, lde, len_, choices, hde, hen, cost in game_settings.SECTIONS[tab][2]:
                raw = cur.get(key)
                gone = game_settings.UNAVAILABLE.get(key, {})
                if key == 'dlss' and self.dlss_ready():   # (DLSS built in: offered, not 'not available')
                    gone = {}
                    choices = choices + [(1, 'NVIDIA DLSS', 'NVIDIA DLSS'), (2, 'NVIDIA DLAA', 'NVIDIA DLAA')]
                if key == 'dlss' and self.facts and not advisor.has_fsr4(self.facts):
                    # (AMD FSR 4 runs only where AMD's driver offers it, Radeon RX 7000 / 9000: elsewhere the game falls back to
                    # its own upscaler, so it is not offered; a saved choice is shown as not available here)
                    choices = [c for c in choices if c[0] not in (4, 5)]
                    gone = dict(gone)
                    gone[4] = ('AMD FSR 4 (nicht auf dieser Grafikkarte)', 'AMD FSR 4 (not on this graphics card)')
                    gone[5] = ('AMD FSR 4 Native AA (nicht auf dieser Grafikkarte)', 'AMD FSR 4 Native AA (not on this graphics card)')
                if raw is not None and raw.isdigit() and int(raw) in gone:   # (saved, but this build cannot run it: said so)
                    choices = choices + [(int(raw),) + gone[int(raw)]]
                elif raw is not None and not any(str(v) == raw or e.split(' ')[0] == raw for v, _, e in choices):   # (a value the menu set that the list lacks)
                    choices = sorted(choices + [(int(raw) if raw.lstrip('-').isdigit() else raw, raw, raw)],
                                     key=lambda c: c[0] if isinstance(c[0], int) else 0)
                labels = [d if de else e for _, d, e in choices]
                was = game_settings.current(cur, key, choices)[0]
                if key in LAUNCHER_KEYS:   # (the launcher's own, not the options file's: mesh_shaders)
                    was = self.cfg.get(key, was)
                now = self.pending_settings.get(key, was)
                shown = next((l for (v, _, _), l in zip(choices, labels) if v == now), labels[0])
                rows.append((key, lde if de else len_, hde if de else hen, cost, labels, shown,
                             lambda lab, key=key, choices=choices, labels=labels, was=was:
                             changed(key, choices[labels.index(lab)][0], was)))
            if game_settings.SECTIONS[tab][1] == 'Memory':   # (Ocarina Reborn's low-end rows: the launcher's, handed over at Play)
                for key, lde, len_, labels_de, labels_en, hde, hen, cost in LOW_END_ROWS:
                    labels = labels_de if de else labels_en
                    now = self.pending_settings.get(key, self.cfg.get(key, LOW_END_DEFAULTS[key]))
                    rows.append((key, lde if de else len_, hde if de else hen, cost, labels, labels[min(now, len(labels) - 1)],
                                 lambda lab, key=key, labels=labels: changed(key, labels.index(lab),
                                                                             self.cfg.get(key, LOW_END_DEFAULTS[key]))))
            if game_settings.SECTIONS[tab][1] == 'Audio':
                for age, label in (('child', T('Junger Link: Stimme', 'Young Link: voice')),
                                   ('adult', T('Erwachsener Link: Stimme', 'Adult Link: voice'))):
                    key = 'classic_voice_' + age
                    try:
                        state = classic_voices.status(game, age)
                    except (OSError, ValueError) as e:
                        state = dict(installed=False, enabled=False)
                        self.settings_status = (str(e), RED)
                    labels = [T('Standard', 'Default'), T('Klassisch (N64)', 'Classic (N64)')]
                    was = int(state['enabled'])
                    now = min(self.pending_settings.get(key, was), len(labels) - 1)
                    rows.append((key, label,
                                 T('Eigene Stimmen-ZIP für Angriffe, Treffer und Bewegung importieren und speichern; '
                                   'spezielle Zwischensequenz-Stimmen bleiben erhalten.',
                                   'Import your own voice ZIP for attacks, damage and movement, then save; '
                                   'dedicated cutscene voices stay unchanged.'), '', labels, labels[now],
                                 lambda lab, key=key, labels=labels, was=was: changed(key, labels.index(lab), was)))
        elif tab > len(game_settings.SECTIONS):   # Cheats: the engine's own debug tools, on from the start (HOS_OOT_CHEATS)
            onoff = [T('Aus', 'Off'), T('An', 'On')]
            for key, lde, len_, hde, hen in (
                    ('cheats', 'Cheat-Werkzeuge (F1 → Debug)', 'Cheat tools (F1 → Debug)',
                     'Schaltet die Werkzeuge im Spielmenü frei: Flug ohne Kollision, freie Kamera, Position merken und '
                     'zurückkehren, Teleport, Alter wechseln, Inventar-Editor, Uhrzeit und Laufgeschwindigkeit.',
                     'Turns on the tools in the game menu: no-clip flight, a free camera, mark and return, teleport, switch '
                     'age, the inventory editor, the clock and movement speed.'),
                    ('protect_hearts', 'Herzen schützen', 'Protect hearts',
                     'Link verliert keine Herzen (Treffer werfen ihn trotzdem zurück). Nur mit Cheat-Werkzeugen an.',
                     'Link loses no hearts (hits still knock him back). Only with the cheat tools on.')):
                rows.append((key, lde if de else len_, hde if de else hen, '', onoff,
                             onoff[1 if self.pending_settings.get(key, self.cfg.get(key, 0)) else 0],
                             lambda lab, key=key, onoff=onoff: changed(key, onoff.index(lab), self.cfg.get(key, 0))))
        else:   # Difficulty: the launcher's own, applied to the game's files at Play (enemy_health.py)
            for key, lde, len_, hde, hen in (('monster_health', 'Monster-Leben', 'Monster health', 'Wie viel Leben normale Gegner haben.',
                                              'How much life normal enemies have.'),
                                             ('boss_health', 'Boss-Leben', 'Boss health', 'Wie viel Leben die Bosse haben.',
                                              'How much life the bosses have.'),
                                             ('enemy_damage', 'Schaden von Gegnern', 'Damage from enemies',
                                              'Wie viel Schaden Link von Gegnern und Bossen bekommt.',
                                              'How much damage Link takes from enemies and bosses.')):
                rows.append((key, lde if de else len_, hde if de else hen, '', ['x1', 'x2', 'x3', 'x4', 'x5'],
                             f'x{self.pending_settings.get(key, self.cfg.get(key, 1))}',
                             lambda lab, key=key: changed(key, int(lab[1:]), self.cfg.get(key, 1))))
            onoff = [T('Aus', 'Off'), T('An', 'On')]   # (Hardcore: hos_oot_life_change, OCARINA_ONE_HIT)
            rows.append(('one_hit', T('Ein-Treffer-Modus (Hardcore)', 'One-hit mode (hardcore)'),
                         T('Jeder Treffer leert alle Herzen. Gilt ab dem nächsten Start.',
                           'Every hit empties all hearts. Applies at the next start.'),
                         '', onoff, onoff[1 if self.pending_settings.get('one_hit', self.cfg.get('one_hit', 0)) else 0],
                         lambda lab, onoff=onoff: changed('one_hit', onoff.index(lab), self.cfg.get('one_hit', 0))))

        def body(ctx, top):
            s = ctx.s
            x, w = self.content(ctx)
            (hy, _), (tby, _), (gy, gh), (hpy, hph), (fy, fh) = layout(
                ctx, top, [(76, 30, 0), (44, 24, 0), (330, 18, 1), (84, 16, 0.15), (60, 18, 0)])
            amiibo_tab = tab < len(game_settings.SECTIONS) and game_settings.SECTIONS[tab][1] == 'amiibo'
            self.heading(ctx, x, hy, T('Einstellungen', 'Settings'),
                         T('Wähle eine Figur für den nächsten amiibo-Scan. Kein Neustart nötig.',
                           'Choose a figure for the next amiibo scan. No restart needed.') if amiibo_tab else
                         T('Dieselben Einstellungen wie im Spielmenü (F1). Sie gelten ab dem nächsten Spielstart.',
                           'The same settings as the in-game menu (F1). They apply at the next start of the game.'),
                         icon='settings', w=w)
            widths = [ctx.text_width(n.upper(), 16, 'semibold') + 40 * s for n in names]
            if sum(widths) + (len(names) - 1) * 10 * s > w:
                # Keep every category reachable when the full tab row would leave the window.
                ctx.dropdown(x, tby, min(400 * s, w), 44 * s, names, names[tab],
                             lambda name: self.settings_page(names.index(name)), size=18)
                ctx.text(x + 420 * s, tby + 22 * s, T('Einstellungsbereich wählen', 'Choose settings category'),
                         17, 'regular', ui.SUB, anchor='w')
            else:
                tx = x
                for i, (n, tw) in enumerate(zip(names, widths)):
                    ctx.button(tx, tby, tw, 44 * s, n.upper(), lambda i=i: self.settings_page(i),
                               kind='primary' if i == tab else 'secondary', size=16, r=22)
                    tx += tw + 10 * s
            ctx.panel(x, gy, w, gh, r=16, fill=ui.PANEL, fill2='#0d1d40', alpha=0.85, border=ui.LINE)
            head = 0
            if tab == 1:   # (the presets: a line of their own at the panel's top, on Quality only; at its foot they covered the last row)
                gpu = advisor.main_gpu(self.facts)[0] if self.facts else ''
                bx = x + 24 * s
                ctx.text(bx, gy + 36 * s, T('Presets:', 'Presets:'), 16, 'semibold', ui.SUB, anchor='w')
                bx += ctx.text_width(T('Presets:', 'Presets:'), 16, 'semibold') + 14 * s
                for key, label in (('recommended', T('Empfohlen', 'Recommended') + (f' · {gpu}' if gpu else '')),
                                   ('performance', T('Leistung', 'Performance')),
                                   ('quality', T('Qualität', 'Quality'))):
                    bw_ = ctx.text_width(label, 15, 'semibold') + 34 * s
                    ctx.button(bx, gy + 18 * s, bw_, 36 * s, label, lambda k=key: self.apply_preset(k),
                               kind='primary' if key == 'recommended' else 'pill', size=15, r=18)
                    bx += bw_ + 10 * s
                head = 54 * s
            # Room at the panel's foot for DLSS setup and the audio/difficulty notes.
            foot = (tab == 1 and self.has_nvidia() and not self.dlss_ready()) or tab == len(game_settings.SECTIONS) or \
                (tab < len(game_settings.SECTIONS) and game_settings.SECTIONS[tab][1] == 'Audio')
            cols = 2
            per = (len(rows) + cols - 1) // cols
            cw = (w - 40 * s) / cols
            rh = min(64 * s, (gh - 30 * s - head - (70 * s if foot else 0)) / max(1, per))
            for i, (key, name, helptext, cost, labels, shown, pick) in enumerate(rows):
                c, r = divmod(i, per)
                rx, ry = x + 24 * s + c * cw, gy + 16 * s + head + r * rh
                dw = min(330 * s, cw * 0.5)
                info = (name, helptext, cost)
                if cost:
                    ctx.panel(rx + 6 * s, ry + rh / 2 - 5 * s, 10 * s, 10 * s, r=5, fill=costs[cost][1], alpha=1, border=None)
                ctx.text(rx + 28 * s, ry + rh / 2, name, 19, 'regular', ui.TEXT, anchor='w', width=cw - dw - 50 * s)
                ctx.hot(rx, ry, cw - 10 * s, rh, None, cursor='', enter=lambda info=info: explain(*info))
                h = ctx.dropdown(rx + cw - dw - 20 * s, ry + (rh - min(48 * s, rh - 10 * s)) / 2, dw,
                                 min(48 * s, rh - 10 * s), labels, shown, pick, size=18)
                h.enter = lambda info=info: explain(*info)
            if tab < len(game_settings.SECTIONS) and game_settings.SECTIONS[tab][1] == 'amiibo':
                model = amiibo.selected_id(game)
                py = gy + 30 * s
                ctx.text(x + 30 * s, py, T('Eigene amiibo-Datei', 'Your amiibo file'), 26, 'semibold', ui.TEXT)
                ctx.text(x + 30 * s, py + 48 * s,
                         T('Ausgewählte Figur: ', 'Selected model: ') + model if model else
                         T('Keine Figur ausgewählt', 'No amiibo selected'), 18, 'regular', ui.SUB)
                ctx.button(x + 30 * s, py + 90 * s, 270 * s, 46 * s,
                           T('.bin auswählen', 'Choose .bin'), choose_amiibo, kind='primary', size=20)
                ctx.button(x + 320 * s, py + 90 * s, 170 * s, 46 * s,
                           T('Entfernen', 'Remove'), lambda: choose_amiibo(True), size=18)
                ctx.text(x + 30 * s, py + 160 * s,
                         T('1. Eigene amiibo-Datei auswählen (532, 540 oder 572 Bytes).\n'
                           '2. Im Spiel die amiibo-Funktion aktivieren und einen Scan starten.\n'
                           'Auch während des Spiels unter F1 → Gameplay → Load amiibo (.bin).\n'
                           'Die Auswahl gilt sofort. Die normalen Belohnungsgrenzen bleiben bestehen.\n'
                           'Nur Lesen: keine Spielstände auf amiibos schreiben. Keine Figuren enthalten.',
                           '1. Choose your own amiibo file (532, 540 or 572 bytes).\n'
                           '2. Enable the game\'s amiibo feature and start a scan.\n'
                           'Change files in game: F1 → Gameplay → Load amiibo (.bin).\n'
                           'Selection applies immediately. Normal reward limits still apply.\n'
                           'Read-only: no saving data to tags. Amiibo files are not included.'),
                         17, 'regular', ui.SUB, width=w - 60 * s)
            if tab < len(game_settings.SECTIONS) and game_settings.SECTIONS[tab][1] == 'Tunic':
                color = tunic_colors.hex_color(cur | self.pending_settings)
                py = gy + 106 * s
                ctx.panel(x + 30 * s, py, 100 * s, 100 * s, r=16, fill=color, alpha=1, border=ui.LINE)
                ctx.text(x + 150 * s, py + 12 * s, color, 26, 'semibold', ui.TEXT)
                ctx.text(x + 150 * s, py + 50 * s, 'RGB  ' + ' / '.join(map(str, tunic_colors.rgb(cur | self.pending_settings))),
                         18, 'regular', ui.SUB)
                ctx.button(x + 30 * s, py + 124 * s, 240 * s, 46 * s, T('Farbe auswählen', 'Choose color'),
                           choose_tunic, kind='primary', size=20)
                ctx.button(x + 288 * s, py + 124 * s, 170 * s, 46 * s, T('HEX eingeben', 'Enter HEX'),
                           lambda: choose_tunic(True), size=18)
                ctx.text(x + 30 * s, py + 175 * s,
                         T('Für Kinder-Link und die erwachsenen Tuniken. Auch unter F1 → Gameplay.\n'
                           'Speichern und Spiel neu starten. Die Vorschau zeigt die gewählte Farbe ohne Beleuchtung.',
                           'For young Link and adult tunics. Also under F1 → Gameplay.\n'
                           'Save and restart the game. The preview shows the selected color without lighting.'),
                         17, 'regular', ui.SUB, width=w - 60 * s)
            if tab == len(game_settings.SECTIONS):
                ctx.text(x + 30 * s, gy + gh - 30 * s, T('Gilt ab dem nächsten Spielstart. F1 → Debug → Enemy damage startet mit diesem Wert '
                                                         'und kann ihn im Spiel ändern.', 'Applies at the next start. F1 → Debug → Enemy '
                                                         'damage starts at this value and can change it in game.'), 17, 'regular', ui.SUB, anchor='w')
            if tab == 1 and self.has_nvidia() and not self.dlss_ready():
                label = T('NVIDIA DLSS einrichten', 'Set up NVIDIA DLSS')
                bw_ = ctx.text_width(label, 17, 'semibold') + 70 * s
                ctx.button(x + w - bw_ - 20 * s, gy + gh - 60 * s, bw_, 44 * s, label, self.setup_dlss, kind='primary',
                           icon='download', size=17, r=12)
            if tab < len(game_settings.SECTIONS) and game_settings.SECTIONS[tab][1] == 'Audio':
                ctx.text(x + 30 * s, gy + gh - 38 * s,
                         T('Eigene Stimmen-ZIP importieren, speichern und das Spiel neu starten. Keine Aufnahmen enthalten.',
                           'Import your own voice ZIP, save and restart the game. No recordings are included.'),
                         17, 'regular', ui.SUB, anchor='w', width=w - 60 * s)
            ctx.panel(x, hpy, w, hph, r=14, fill=ui.CELL, alpha=0.9, border=ui.LINE)
            ctx.icon(x + 34 * s, hpy + hph / 2, 'info', 24, ui.ACCENT_HI)
            ctx.text(x + 66 * s, hpy + 14 * s, '', 17, 'semibold', ui.TEXT, key='help_title')
            ctx.text(x + 66 * s, hpy + 40 * s,
                     T('Die Originaldatei bleibt unverändert. Wenn gerade gescannt wird, den Scan nach einem Wechsel neu starten.',
                       'Your original file stays unchanged. If a scan is in progress, restart it after switching figures.') if amiibo_tab else
                     T('Fahre über eine Einstellung, um zu sehen, was sie macht.',
                                                 'Point at a setting to see what it does.'), 17, 'regular', ui.SUB,
                     key='help_text', width=w - 100 * s)
            ctx.button(x, fy, 170 * s, fh, T('Zurück', 'Back'), back, icon='back', size=19)
            if amiibo_tab:
                text, col = self.settings_status
                ctx.text(x + 200 * s, fy + fh / 2, text, 18, 'regular', col, anchor='w',
                         key='status', width=w - 220 * s)
                return
            rw = ctx.text_width(T('Grafik zurücksetzen', 'Reset graphics'), 19, 'semibold') + 70 * s
            ctx.button(x + 186 * s, fy, rw, fh, T('Grafik zurücksetzen', 'Reset graphics'), reset, icon='refresh', size=19)
            text, col = self.settings_status
            bw = 260 * s
            ctx.text(x + w - bw - 24 * s, fy + fh / 2, text, 18, 'regular', col, anchor='e', key='status')
            ctx.button(x + w - bw, fy, bw, fh, T('Speichern', 'Save'), save, kind='primary', icon='save', size=24,
                       weight='bold', r=14)
        self.show('play', body)
        self.page_tab = tab

    def set_option(self, key, value):
        if key == 'language':
            self.cfg['language'] = next((c for c, n in LANGS if n == value), 'en-US')
        elif key == 'audio':
            self.cfg['audio'] = str(self.audio_devs.index(value)) if value in self.audio_devs else 'default'
        elif key == 'ui':
            self.cfg['ui_language'] = 'de' if value == 'Deutsch' else 'en'
            UI_LANG[0] = self.cfg['ui_language']
        save_settings(self.cfg)
        self.ready()

    def play(self):
        """the enemy and boss health first (enemy_health.py, only when the choice changed), then the game"""
        game = Path(self.cfg['game_dir'])
        mon, boss = int(self.cfg.get('monster_health', 1)), int(self.cfg.get('boss_health', 1))
        try:
            same = json.loads((game / enemy_health.STATE).read_text()) == {'monsters': mon, 'bosses': boss}
        except (OSError, ValueError):
            same = mon == 1 and boss == 1
        if same:
            return self.start_game()
        win = tk.Toplevel(self, bg=BG)
        win.title('Ocarina Reborn')
        win.geometry('420x110')
        tk.Label(win, text=T(f'Gegner-Leben wird angepasst (Monster x{mon}, Bosse x{boss}) …',
                             f'Adjusting enemy health (monsters x{mon}, bosses x{boss}) …'), fg=TEXT, bg=BG,
                 font=('Segoe UI', 11)).pack(pady=(20, 8))
        bar = ttk.Progressbar(win, length=360, maximum=100, style='Blue.Horizontal.TProgressbar')
        bar.pack()
        q = queue.Queue()

        def work():
            try:
                n = enemy_health.apply(game, mon, boss, progress=lambda f: q.put(f))
                log(f'enemy health: monsters x{mon}, bosses x{boss}, {n} packs changed')
                q.put('ok')
            except Exception as e:   # (a damaged or unusual pack: the game starts as it is, and the log says why)
                log(f'enemy health not applied: {type(e).__name__}: {e}')
                q.put('fail')
        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                while True:
                    m = q.get_nowait()
                    if m in ('ok', 'fail'):
                        win.destroy()
                        if m == 'fail':
                            messagebox.showwarning('Ocarina Reborn', T('Das Gegner-Leben konnte nicht angepasst werden; das Spiel startet normal.',
                                                                      'Enemy health could not be adjusted; the game starts as it is.'))
                        return self.start_game()
                    bar['value'] = m * 100
            except queue.Empty:
                pass
            self.after(150, poll)
        poll()

    def game_env(self):
        """the game's environment, as Play starts it (the shader preparation too: same GPU, same switches)"""
        env = dict(os.environ, OCARINA_TESTER=tester_id(), OCARINA_BUILD=INFO['build_id'],
                   OCARINA_SHADER_DUMPS=str(DIRS['ShaderDumps']), OCARINA_CRASH_DUMPS=str(DIRS['CrashDumps']),
                   HOOKSHOT_NO_UPDATE_CHECK='1', RX_VK_DUMP_FAILED=str(DIRS['ShaderDumps']),
                   HOS_LANGUAGE=self.cfg.get('language', 'en-US'),
                   HOS_DISCORD='0')   # (Discord would name Hookshot's own Discord application)   # the game's text, chosen on the ready page
        if (INSTALL / 'amd-fsr4' / 'amd_fidelityfx_loader_vk.dll').is_file():
            env['RX_VK_FSR_DIR'] = str(INSTALL / 'amd-fsr4')   # (AMD FSR 4's DLLs, shipped with the install)
        env['OCARINA_ENEMY_DAMAGE'] = str(int(self.cfg.get('enemy_damage', 1)))   # (Difficulty: the damage Link takes)
        mesh = {1: 'native', 2: 'compute'}.get(int(self.cfg.get('mesh_shaders', 0) or 0))   # (Advanced: Mesh shaders, v2.2.0's switch)
        if mesh:
            env.setdefault('RX_VK_MESH_SHADERS', mesh)
        if self.cfg.get('one_hit'):   # (Difficulty: One-hit mode)
            env['OCARINA_ONE_HIT'] = '1'
        for k, v in low_end_env(self.cfg).items():   # (Memory tab: the low-end rows; a variable set by hand wins)
            env.setdefault(k, v)
        # (a card with 8 GB or less: video memory compaction on unless the player chose the row. A 1.0.1 session on an RTX 4060
        # Laptop (8 GB) reached 7.09 of 7.02 GB and stalled up to 1.7 s on area loads; the engine's own measurement for
        # RX_VK_COMPACT on a tight card: 11-12 frames over 33 ms on a Hyrule Field walk against 34-49, 1% low 37 against 26-29 fps)
        if 'vram_compact' not in self.cfg and 'RX_VK_COMPACT' not in os.environ:
            gpus = [(n, gb) for n, gb in ((self.facts or {}).get('gpus') or []) if gb]
            mine = next((g for g in gpus if self.active_gpu and g[0] in str(self.active_gpu)), None) or max(gpus, key=lambda g: g[1], default=None)
            if mine and mine[1] <= 8.5:
                env['RX_VK_COMPACT'] = '1'
                log(f'video memory compaction on for {mine[0]} ({mine[1]:.0f} GB; Memory tab: Compact video memory to choose)')
        log('low-end: ' + ', '.join(f'{k}={v}' for k, v in low_end_env(self.cfg).items()))
        if self.cfg.get('cheats'):   # (Cheats: the debug tools on from the start, and heart protection with them)
            env['HOS_OOT_CHEATS'] = '1'
            env['HOS_OOT_PROTECT_HEARTS'] = '1' if self.cfg.get('protect_hearts') else '0'
        if self.cfg.get('audio', 'default') != 'default':
            env['HOS_AUDIO_DEVICE'] = self.cfg['audio']   # a waveOut device number (audio_devices)
        return env

    # ---- Reborn Auto: a measured run, a reviewable suggestion, a second run of the same scenes, a verdict -----------------
    # (state in settings.json "reborn_auto": step 'baseline' (the first run is next), 'compare' (the changed settings are in,
    # the second run is next); the baseline summary, the changes and the backup of the options file go with it)
    def reborn_auto(self):
        if self.busy or not game_exe(Path(self.cfg['game_dir'])).is_file():
            return messagebox.showinfo('Reborn Auto', T('Erst das Spiel einrichten.', 'Set up the game first.'))
        state = self.cfg.get('reborn_auto') or {}
        if state.get('step') == 'compare':
            if not messagebox.askyesno('Reborn Auto', T(
                    'Die neuen Einstellungen sind aktiv. Spiel jetzt dieselbe Strecke wie beim ersten Lauf, mindestens 2 Minuten, '
                    'und beende dann das Spiel. Danach siehst du, ob es besser geworden ist.\n\nJetzt starten?',
                    'The new settings are in. Now play the same route as in the first run, at least 2 minutes, then quit the game. '
                    'Then you see whether it got better.\n\nStart now?')):
                if messagebox.askyesno('Reborn Auto', T('Reborn Auto abbrechen und die alten Einstellungen zurückholen?',
                                                        'Cancel Reborn Auto and restore the previous settings?')):
                    self.reborn_auto_restore(state)
                return
            return self.play()
        if not messagebox.askyesno('Reborn Auto', T(
                'Reborn Auto misst, was bei dir bremst, und schlägt passende Einstellungen vor.\n\n'
                '1. Spiel 2–5 Minuten an einer Stelle, die du gut wiederholen kannst (z. B. Kokiri-Dorf → Wald), dann Spiel beenden.\n'
                '2. Du siehst den Vorschlag und entscheidest selbst.\n'
                '3. Spiel dieselbe Strecke noch einmal: Reborn Auto vergleicht beide Läufe.\n\n'
                'Frame Generation bitte aus lassen. Keine FPS-Garantie: gemessen wird nur, was wirklich passiert.\n\nJetzt starten?',
                'Reborn Auto measures what holds your PC back and suggests settings that fit.\n\n'
                '1. Play 2-5 minutes somewhere you can repeat (e.g. Kokiri village → forest), then quit the game.\n'
                '2. You see the suggestion and decide.\n'
                '3. Play the same route again: Reborn Auto compares both runs.\n\n'
                'Please keep frame generation off. No fps promise: only what really happens is measured.\n\nStart now?')):
            return
        self.cfg['reborn_auto'] = dict(step='baseline', at=datetime.datetime.now().isoformat(timespec='seconds'))
        save_settings(self.cfg)
        log('reborn auto: first run')
        self.play()

    def reborn_auto_restore(self, state):
        game = Path(self.cfg['game_dir'])
        try:
            if state.get('backup') and Path(state['backup']).is_file():
                shutil.copy2(state['backup'], game_settings.ini_file(game))
                log(f"reborn auto: previous settings restored from {state['backup']}")
        except OSError as e:
            messagebox.showerror('Reborn Auto', str(e))
        self.cfg['reborn_auto'] = None
        save_settings(self.cfg)

    def reborn_auto_after(self, summary):
        """after a game run while Reborn Auto is on: the suggestion (after the first run) or the verdict (after the second)"""
        state = self.cfg.get('reborn_auto') or {}
        de = UI_LANG[0] == 'de'
        game = Path(self.cfg['game_dir'])
        if not summary or summary.get('seconds', 0) < performance.AUTO_MIN_SECONDS:
            if state.get('step') == 'baseline':   # (a first run too short: Reborn Auto starts over when clicked again)
                self.cfg['reborn_auto'] = None
                save_settings(self.cfg)
            return messagebox.showinfo('Reborn Auto', T(
                f'Zu wenig gemessen (mindestens {performance.AUTO_MIN_SECONDS} s Spielen ohne offenes Menü). '
                'Klick noch einmal auf Reborn Auto und spiel etwas länger.',
                f'Too little measured (at least {performance.AUTO_MIN_SECONDS} s of play without the menu open). '
                'Click Reborn Auto again and play a little longer.'))
        if state.get('step') == 'baseline':
            record = self.cfg.get('last_performance') or {}
            current = game_settings.read(game)
            changes, reasons = performance.suggest(summary, current, record.get('settings'), de)
            low_end = {}
            if (summary.get('vram_pressure_seconds', 0) >= 15 or summary.get('host_memory_events', 0)) and int(self.cfg.get('ram_guard', 1)) < 2:
                low_end['ram_guard'] = 2
                reasons.append(T('Der Speicher war länger knapp: RAM-Schutz auf Stark.',
                                 'Memory was short for a while: RAM guard to Strong.'))
            text = '\n'.join('•  ' + line for _, line in performance.describe(summary, de)[:3])
            if not changes and not low_end:
                self.cfg['reborn_auto'] = None
                save_settings(self.cfg)
                return messagebox.showinfo('Reborn Auto', text + '\n\n' + '\n'.join(reasons) + '\n\n' + T(
                    'Nichts Eindeutiges zu verbessern: deine Einstellungen passen zu dem, was gemessen wurde.',
                    'Nothing clear to improve: your settings fit what was measured.'))
            labels = {key: (d if de else e, {str(v): cd if de else ce for v, cd, ce in choices})
                      for key, d, e, choices in game_settings.ROWS}
            values = performance.signature(current)
            preview = []
            for key, value in changes.items():
                name, choices = labels.get(key, (key, {}))
                old = values.get(key, current.get(key, '0'))
                preview.append(f'{name}: {choices.get(str(old), str(old))} → {choices.get(str(value), str(value))}')
            for key, value in low_end.items():
                row = next(r for r in LOW_END_ROWS if r[0] == key)
                labels_ = row[3] if de else row[4]
                preview.append(f"{row[1] if de else row[2]}: {labels_[int(self.cfg.get(key, LOW_END_DEFAULTS[key]))]} → {labels_[value]}")
            if not messagebox.askyesno('Reborn Auto', text + '\n\n' + '\n'.join(reasons) + '\n\n' +
                                       T('Vorschlag:', 'Suggestion:') + '\n' + '\n'.join(preview) + '\n\n' +
                                       T('Übernehmen und mit einem zweiten Lauf prüfen?', 'Apply and check with a second run?')):
                self.cfg['reborn_auto'] = None
                save_settings(self.cfg)
                return
            backup = DIRS['Reports'] / ('settings-before-reborn-auto-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.ini')
            try:
                if game_settings.ini_file(game).is_file():
                    shutil.copy2(game_settings.ini_file(game), backup)
                if changes:
                    game_settings.write(game, changes)
            except OSError as e:
                return messagebox.showerror('Reborn Auto', str(e))
            self.cfg['reborn_auto'] = dict(step='compare', baseline=summary, changes=changes, low_end=low_end,
                                           low_end_before={k: self.cfg.get(k, LOW_END_DEFAULTS[k]) for k in low_end},
                                           backup=str(backup))
            self.cfg.update(low_end)
            save_settings(self.cfg)
            log(f'reborn auto: applied {changes} {low_end}, backup {backup}')
            return self.reborn_auto()   # (the second run, asked for)
        if state.get('step') == 'compare':
            verdict, lines = performance.compare(state.get('baseline'), summary, de)
            report = dict(at=datetime.datetime.now().isoformat(timespec='seconds'), verdict=verdict, baseline=state.get('baseline'),
                          after=summary, changes=state.get('changes'), low_end=state.get('low_end'))
            try:
                (DIRS['Reports'] / ('reborn-auto-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')).write_text(
                    json.dumps(report, indent=2), encoding='utf-8')
            except OSError:
                pass
            log(f'reborn auto: verdict {verdict}')
            head = {'better': T('Besser geworden. Die neuen Einstellungen bleiben.', 'It got better. The new settings stay.'),
                    'same': T('Kein messbarer Unterschied.', 'No measurable difference.'),
                    'worse': T('Schlechter geworden.', 'It got worse.')}.get(verdict, T('Kein Ergebnis.', 'No result.'))
            body = head + '\n\n' + '\n'.join('•  ' + l for l in lines)
            if verdict in ('same', 'worse', None):
                if messagebox.askyesno('Reborn Auto', body + '\n\n' + T('Alte Einstellungen zurückholen?', 'Restore the previous settings?')):
                    self.cfg.update(state.get('low_end_before') or {})
                    return self.reborn_auto_restore(state)
            else:
                messagebox.showinfo('Reborn Auto', body)
            self.cfg['reborn_auto'] = None
            save_settings(self.cfg)

    # ---- Prepare shaders: the engine's own --prepare-shaders, again, without a rebuild -------------------------------------
    def prepare_shaders(self):
        """after a driver update or a cleared cache: the game's shaders and pipelines built now, with a progress bar, instead
        of stutter the first time each is drawn (ocarina_reborn.exe --prepare-shaders, as the build's last step runs it)"""
        game = Path(self.cfg['game_dir'])
        if self.busy or not game_exe(game).is_file():
            return messagebox.showinfo('Ocarina Reborn', T('Erst das Spiel einrichten.', 'Set up the game first.'))
        if not messagebox.askyesno('Ocarina Reborn', T(
                'Shader und Pipelines jetzt vorbereiten? Das dauert je nach Grafikkarte einige Minuten und verhindert Ruckler, '
                'wenn das Spiel etwas zum ersten Mal zeichnet. Sinnvoll nach einem Treiber-Update.',
                'Prepare the shaders and pipelines now? Depending on the graphics card it takes a few minutes and prevents '
                'stutter the first time the game draws something. Worth it after a driver update.')):
            return
        win = tk.Toplevel(self, bg=BG)
        win.title('Ocarina Reborn')
        win.geometry('460x130')
        label = tk.Label(win, text=T('Shader werden vorbereitet …', 'Preparing shaders …'), fg=TEXT, bg=BG, font=('Segoe UI', 11))
        label.pack(pady=(20, 8))
        bar = ttk.Progressbar(win, length=400, maximum=1000, style='Blue.Horizontal.TProgressbar')
        bar.pack()
        q = queue.Queue()
        env = self.game_env()
        try:
            p = subprocess.Popen([str(game_exe(game)), '--prepare-shaders'], cwd=str(game), env=env, stdout=subprocess.PIPE,
                                 stderr=subprocess.STDOUT, text=True, errors='replace',
                                 creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0))
        except OSError as e:
            win.destroy()
            return messagebox.showerror('Ocarina Reborn', str(e))
        log('prepare shaders: started')
        self.busy = True

        def read():
            for line in p.stdout:
                if line.startswith('@@progress '):
                    try:
                        q.put(float(line.split()[1]))
                    except (IndexError, ValueError):
                        pass
            q.put(('done', p.wait()))
        threading.Thread(target=read, daemon=True).start()

        def cancel():
            if p.poll() is None:
                p.terminate()
        win.protocol('WM_DELETE_WINDOW', cancel)

        def poll():
            try:
                while True:
                    m = q.get_nowait()
                    if isinstance(m, tuple):
                        code = m[1]
                        self.busy = False
                        win.destroy()
                        log(f'prepare shaders: exit code {code}')
                        if code == 0:
                            return messagebox.showinfo('Ocarina Reborn', T('Shader vorbereitet.', 'Shaders prepared.'))
                        return messagebox.showwarning('Ocarina Reborn', T(
                            'Die Vorbereitung wurde nicht fertig (Code {c}). Das Spiel baut fehlende Shader beim Spielen.',
                            'The preparation did not finish (code {c}). The game builds missing shaders while it plays.').format(c=code))
                    bar['value'] = m * 1000
                    label['text'] = T('Shader werden vorbereitet …', 'Preparing shaders …') + f'  {m * 100:.0f} %'
            except queue.Empty:
                pass
            self.after(200, poll)
        poll()

    def start_game(self):
        game = Path(self.cfg['game_dir'])
        try:
            classic_voices.validate_active(game)
        except (OSError, ValueError) as e:
            messagebox.showerror('Classic voices', str(e))
            return
        env = self.game_env()
        measured_settings = None
        diagnostic_settings = None
        measured_hardware = performance.hardware_signature(self.facts)
        try:
            opts = game_settings.read(game)
            measured_settings = performance.signature(opts)
            keys = ('output_res', 'resolution', 'dlss', 'frame_generation', 'vsync', 'frame_rate_cap', 'hdr', 'texture_detail',
                    'texture_filtering', 'anisotropic_filtering', 'soft_shadows', 'texture_memory', 'shader_cache',
                    'shader_threads', 'pipeline_precompile', 'mesh_shaders', 'texture_saving',
                    'view_distance', 'grass', 'shadow_distance')
            log('game settings: ' + ', '.join(f'{k}={opts.get(k, game_settings.DEFAULTS.get(k, "game default"))}' for k in keys))
            diagnostic_settings = {k: opts.get(k, game_settings.DEFAULTS.get(k, 'game default')) for k in keys}
        except Exception as e:   # (the options file unreadable: the game starts anyway)
            log(f'game settings not read: {e}')
        log(f'display (primary): {display_info()}')
        log('game start')
        run = None
        try:
            run = diagnostics.start(DIRS['CrashDumps'], game, INFO, diagnostic_settings, measured_hardware, env)
        except Exception as e:
            log(f'run diagnostics could not start: {e}')
        try:
            p = subprocess.Popen([str(game_exe(game))], cwd=str(game), env=env)
        except OSError as e:
            log(f'game could not start: {e}')
            if run:
                try:
                    run['record']['launch_error'] = str(e)
                    diagnostics.finish(run, -1, game)
                except Exception as diag_error:
                    log(f'run diagnostics could not finish: {diag_error}')
            messagebox.showerror('Ocarina Reborn', str(e))
            return
        self.music.stop()
        self.withdraw()

        def wait():
            code = p.wait()
            log(f'game exit code {code}')
            if run:
                try:
                    diagnostics.finish(run, code, game)
                except Exception as e:
                    log(f'run diagnostics could not finish: {e}')
            session = session_from_game_log(game)
            for line in session:
                log('  ' + line)
            auto_summary = None
            try:
                gpu = next((l.split(': ', 1)[1] for l in session if l.startswith('Active GPU (Vulkan): ')), None)
                opts = game_settings.read(game)
                summary = auto_summary = performance.summarize(session)
                self.cfg['last_performance'] = None
                if summary:
                    record = dict(summary=summary, settings=measured_settings, hardware=measured_hardware,
                                  run_id=run['record']['run_id'] if run else None,
                                  build=INFO.get('stamp'), game=str(game.resolve()),
                                  at=datetime.datetime.now().isoformat(timespec='seconds'))
                    if performance.signature(opts) != measured_settings:
                        record['settings'] = None  # In-game changes invalidate a single-settings recommendation.
                    self.cfg['last_performance'] = record
                    report_file = DIRS['Reports'] / ('performance-' + datetime.datetime.now().strftime('%Y%m%d-%H%M%S') + '.json')
                    report_file.write_text(json.dumps(record, indent=2), encoding='utf-8')
                diag = advisor.diagnose(session, opts, UI_LANG[0] == 'de')
                if diag:
                    self.diag = diag
                    self.active_gpu = gpu
                    self.cfg.update(last_diagnosis=diag, active_gpu=gpu)
                    save_settings(self.cfg)
                    for kind, text in diag:
                        log(f'diagnosis: {kind}: {text}')
                else:
                    self.diag = []
                    self.cfg['last_diagnosis'] = []
                save_settings(self.cfg)
            except Exception as e:
                log(f'diagnosis failed: {e}')
            if code not in (0, None):
                self.crash_info(code)
            self.after(0, lambda: (self.deiconify(), None if getattr(self, 'muted', True) else self.music.play()))
            if (self.cfg.get('reborn_auto') or {}).get('step'):   # (Reborn Auto: its next step, on the window's thread)
                self.after(700, lambda s=auto_summary: self.reborn_auto_after(s))
        threading.Thread(target=wait, daemon=True).start()

    def crash_info(self, code):
        tail = ''
        try:
            game = Path(self.cfg['game_dir'])
            runtime_log = next((game / n for n in ('ocarina_reborn_log.txt', 'hookshot_log.txt')
                                if (game / n).is_file()), game / 'ocarina_reborn_log.txt')
            tail = ''.join(diagnostics.tail(runtime_log, limit=256 * 1024).splitlines(True)[-150:])
        except OSError:
            pass
        (DIRS['CrashDumps'] / f'crash-info-{datetime.datetime.now():%Y%m%d-%H%M%S}.txt').write_text(
            f'{INFO["name"]} {INFO["version"]} build {INFO["build_id"]} commit {INFO["commit"]}\n'
            f'tester {tester_id()}\nexit code {code} ({code & 0xffffffff:#x})\n\nlast runtime messages:\n{tail}',
            encoding='utf-8')
        # Windows refused memory (error 1455: RAM + page file at the limit): the game's crash, but the fix is on the PC
        if 'failed (error 1455)' in tail or 'Windows is out of memory' in tail:
            log('crash cause: Windows ran out of memory (commit limit: RAM + page file)')
            self.after(500, lambda: messagebox.showwarning('Ocarina Reborn', T(
                'Das Spiel wurde beendet, weil Windows kein Speicher mehr hatte (RAM und Auslagerungsdatei voll).\n\n'
                'Schließe andere Programme (Browser, Discord, Aufnahme-Tools) und stelle unter Windows > System > Info > '
                'Erweiterte Systemeinstellungen > Leistung > Erweitert > Virtueller Arbeitsspeicher '
                '"Größe automatisch verwalten" ein (oder mindestens 32 GB als Maximum).',
                'The game closed because Windows ran out of memory (RAM plus the page file).\n\n'
                'Close other programs (browser, Discord, recording tools) and in Windows > System > About > Advanced '
                'system settings > Performance > Advanced > Virtual memory choose "Automatically manage paging file size" '
                '(or at least 32 GB as the maximum).')))

    def diagnostic_tools(self):
        win = tk.Toplevel(self, bg=BG)
        win.title(T('Diagnose', 'Diagnostics'))
        win.geometry('620x390')
        text = T(
            'Strg+F8 im Spiel markiert eine Problemstelle. Auch F1 → Bug report setzt einen Marker.\n\n'
            'Ruckler und längere Phasen ohne neue Bilder werden automatisch erfasst. Danach das Spiel schließen und ein Debug-Paket erstellen. '
            'Bitte Raum, Boss oder Okarina-Lied und die Schritte zum Problem angeben.\n\n'
            'Die optionale Windows-Aufzeichnung dauert 30 Sekunden und kann zusätzliche Last erzeugen. Sie enthält auch Aktivitäten anderer Programme und Dateipfade. '
            'Sie wird separat gespeichert und nicht automatisch ins Debug-Paket aufgenommen.',
            'Ctrl+F8 in game marks a problem. F1 → Bug report also adds a marker.\n\n'
            'Stutters and extended periods without new frames are recorded automatically. Afterwards, close the game and create a Debug Package. '
            'Please describe the room, boss or ocarina song and the steps that triggered the problem.\n\n'
            'The optional Windows trace lasts 30 seconds and may add overhead. It also contains other programs’ activity and file paths. '
            'It is saved separately and is not automatically included in the Debug Package.')
        tk.Label(win, text=text, wraplength=570, justify='left', fg=TEXT, bg=BG, font=('Segoe UI', 10)).pack(padx=20, pady=18)
        status = tk.StringVar(value='')
        tk.Label(win, textvariable=status, wraplength=570, fg=TEXT, bg=BG).pack(padx=20, pady=4)
        actions = tk.Frame(win, bg=BG); actions.pack(pady=8)
        ttk.Button(actions, text=T('Shader-Dumps öffnen', 'Open shader dumps'), command=lambda: os.startfile(DIRS['ShaderDumps'])).pack(side='left', padx=5)

        def capture():
            if getattr(self, '_diagnostic_trace_running', False):
                return
            executable, error = trace_capture.available()
            if error:
                return messagebox.showinfo('Windows trace', error, parent=win)
            if not messagebox.askyesno('Windows trace', T(
                    '30 Sekunden Systemaktivität aufzeichnen? Die Datei kann Programmnamen und Dateipfade enthalten. '
                    'Wechsle nach dem Start innerhalb von 5 Sekunden ins laufende Spiel und wiederhole das Problem.',
                    'Record 30 seconds of system activity? The file can contain program names and file paths. '
                    'After starting, switch to the running game within 5 seconds and reproduce the problem.'), parent=win):
                return
            self._diagnostic_trace_running = True
            capture_button.configure(state='disabled')
            messages = queue.Queue()

            def work():
                try:
                    path = trace_capture.record(executable, DIRS['Reports'], messages.put)
                    messages.put(('done', str(path)))
                except Exception as exc:
                    messages.put(('error', str(exc)))
            threading.Thread(target=work, daemon=False).start()

            def poll():
                try:
                    while True:
                        item = messages.get_nowait()
                        if isinstance(item, tuple):
                            self._diagnostic_trace_running = False
                            if win.winfo_exists():
                                capture_button.configure(state='normal'); status.set(item[1])
                            return
                        if win.winfo_exists():
                            status.set(item)
                except queue.Empty:
                    self.after(200, poll)
            poll()

        capture_button = ttk.Button(actions, text=T('Windows-Aufzeichnung (30 s)', 'Windows trace (30 s)'), command=capture)
        capture_button.pack(side='left', padx=5)
        ttk.Button(win, text=T('Debug-Paket erstellen', 'Create Debug Package'), command=self.debug_package).pack(pady=8)
        win.update_idletasks()
        win.geometry(f'{max(620, win.winfo_reqwidth())}x{max(390, win.winfo_reqheight())}')

    def debug_package(self):
        if getattr(self, '_debug_export_running', False):
            return
        game = Path(self.cfg['game_dir'])
        note = simpledialog.askstring(T('Problembeschreibung (optional)', 'Problem details (optional)'), T(
            'Was ist passiert? Raum/Boss/Lied, Schritte und ungefährer Zeitpunkt. Leer lassen ist möglich.',
            'What happened? Room/boss/song, steps and approximate time. You can leave this blank.'), parent=self)
        if note is None:
            return
        out = Path.home() / 'Desktop' / f'OcarinaReborn-Debug-{tester_id()}-{datetime.datetime.now():%Y%m%d-%H%M%S}.zip'
        if not out.parent.is_dir():
            out = DIRS['Reports'] / out.name
        self._debug_export_running = True
        done = queue.Queue()

        def work():
            try:
                settings = game_settings.read(game)
                debug_export.create(out, game, DIRS, INFO, system_info() + [f'tester: {tester_id()}'], settings, note,
                                    [(Path.home(), '%USERPROFILE%'), (game, '%GAME_DIR%'), (APP, '%APP_DIR%')])
                done.put(None)
            except Exception as exc:
                done.put(str(exc))
        threading.Thread(target=work, daemon=True).start()

        def poll():
            try:
                error = done.get_nowait()
            except queue.Empty:
                return self.after(150, poll)
            self._debug_export_running = False
            if error:
                return messagebox.showerror('Debug Package', error)
            log(f'debug package {out.name}')
            messagebox.showinfo('Ocarina Reborn', T('Debug-Paket erstellt:', 'Debug package created:') + f'\n\n{out}\n\n' + T('Schicke diese Datei dem Entwickler.', 'Send this file to the developer.'))
            os.startfile(out.parent)
        poll()


if __name__ == '__main__':
    try:   # sharp at 125 % / 150 % / 200 % Windows scaling: the launcher draws at the screen's own pixels (Tk scales its fonts)
        import ctypes
        ctypes.windll.shcore.SetProcessDpiAwareness(2)   # (per screen: the page is drawn for the window's pixels)
    except (AttributeError, OSError):
        pass
    # a crash leaves its place in the log: Python's own errors in the Tk callbacks, and a hard crash (faulthandler) with
    # every thread's stack, in Logs\crash-trace-<time>.txt (the debug package takes Logs and CrashDumps)
    import faulthandler
    import traceback
    try:   # (pythonw has no stderr: Python's own fatal messages go to CrashDumps\stderr-<time>.txt)
        for old in list(DIRS['CrashDumps'].glob('stderr-*.txt')) + list(DIRS['CrashDumps'].glob('crash-trace-*.txt')):
            try:   # (the empty ones of earlier starts that ended well: they only crowd the debug package)
                if not old.stat().st_size:
                    old.unlink()
            except OSError:
                pass
        _err = open(DIRS['CrashDumps'] / f'stderr-{NOW}.txt', 'w', encoding='utf-8', buffering=1)
        os.dup2(_err.fileno(), 2)
        sys.stderr = _err
    except OSError:
        pass
    try:
        _trace = open(DIRS['CrashDumps'] / f'crash-trace-{NOW}.txt', 'w', encoding='utf-8')
        faulthandler.enable(_trace, all_threads=True)
    except OSError:
        _trace = None
    tk.Tk.report_callback_exception = lambda self, *exc: log('ERROR in the launcher: ' + ''.join(traceback.format_exception(*exc)))
    try:
        App().mainloop()
    finally:
        if _trace:
            faulthandler.disable()
            _trace.close()
            try:   # (nothing happened: no empty file left behind)
                if not (DIRS['CrashDumps'] / f'crash-trace-{NOW}.txt').stat().st_size:
                    (DIRS['CrashDumps'] / f'crash-trace-{NOW}.txt').unlink()
            except OSError:
                pass
