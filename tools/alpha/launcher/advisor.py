"""What the launcher tells the player about performance, from facts only:
  - pc_facts()        the graphics cards (name, video memory from the driver's registry entry), power source and power plan
  - recommend(facts)  settings for this PC, and the Performance and Quality presets (the in-game menu's own option keys)
  - pc_warnings()     laptop on battery, the power saver plan, the game on the integrated GPU while a dedicated one exists
  - diagnose(lines)   the last session's [perf] lines (the engine's, every 5 s) in plain words: what held it back, what helps
Nothing here guesses a number: what is not measured is not said."""
import re
import subprocess
import os
import json
import performance

NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
INTEGRATED = ('intel(r) uhd', 'intel(r) iris', 'intel(r) hd', 'intel(r) arc(tm) graphics', 'amd radeon(tm) graphics',
              'radeon(tm) graphics', 'radeon vega', 'microsoft basic', 'virtual desktop', 'parsec', 'meta virtual')
VIRTUAL = ('virtual desktop', 'parsec', 'meta virtual', 'spacedesk', 'virtual display')

# (the in-game menu's option values: dlss 0 the game's own, 1 DLSS, 2 DLAA, 3 FSR 3.1; resolution 1 100%, 3 67%, 5 58%, 4 50%;
# anisotropic_filtering 4 = 16x; texture_detail 0 Standard, 1 High, 2 Ultra)
# (every graphics tab: Quality, Performance, Memory, Shaders and the window filter. quality_preset 0 = Custom, so the game's own
# preset row does not set the scaling rows back; frame_generation 1 = Auto; texture_memory is set per card, below)
COMMON = {'quality_preset': 0, 'anisotropic_filtering': 4, 'texture_filtering': 1, 'soft_shadows': 1, 'upscaling': 2,
          'frame_pacing': 1, 'vsync': 0, 'pipeline_precompile': 1, 'shader_cache': 1, 'shader_threads': 0,
          'view_distance': 1, 'grass': 2, 'shadow_distance': 1}
PRESETS = {
    'quality': dict(COMMON, resolution=1, dlss=0, sharpness=50, texture_detail=2, frame_generation=0),
    'balanced': dict(COMMON, resolution=3, dlss=3, sharpness=50, texture_detail=1, frame_generation=0),
    'performance': dict(COMMON, resolution=4, dlss=3, sharpness=50, texture_detail=0, frame_generation=0,
                        view_distance=0, grass=1, shadow_distance=0, frame_rate_cap=0,
                        anisotropic_filtering=2, soft_shadows=0, output_res='1920x1080'),
}


def _ps(cmd, timeout=20):
    try:
        return subprocess.run(['powershell', '-NoProfile', '-Command', cmd], capture_output=True, text=True, timeout=timeout,
                              creationflags=NO_WINDOW).stdout
    except (OSError, subprocess.SubprocessError):
        return ''


def gpus():
    """[(name, video memory in GB or None)] from the display drivers' registry entries (qwMemorySize: not capped at 4 GB)"""
    out = _ps("Get-ItemProperty 'HKLM:\\SYSTEM\\CurrentControlSet\\Control\\Class\\{4d36e968-e325-11ce-bfc1-08002be10318}\\0*' "
              "-ErrorAction SilentlyContinue | ForEach-Object { $_.DriverDesc + '|' + $_.'HardwareInformation.qwMemorySize' }")
    found = []
    for line in out.splitlines():
        if '|' not in line or not line.split('|')[0].strip():
            continue
        name, mem = line.split('|', 1)
        try:
            gb = round(int(mem.strip()) / 2**30, 1) if mem.strip() else None
        except ValueError:
            gb = None
        if name.strip() not in [n for n, _ in found]:
            found.append((name.strip(), gb))
    return found


def is_integrated(name):
    n = name.lower()
    plain = ' '.join(re.sub(r'\(tm\)|\(r\)|[™®]', '', n).split())
    return plain in ('amd radeon graphics', 'radeon graphics') or any(k in n for k in INTEGRATED)


def power():
    """(on battery, has a battery, the power plan's name)"""
    on_battery = has_battery = False
    try:
        import ctypes

        class SPS(ctypes.Structure):
            _fields_ = [('ac', ctypes.c_ubyte), ('flag', ctypes.c_ubyte), ('pct', ctypes.c_ubyte), ('saver', ctypes.c_ubyte),
                        ('life', ctypes.c_ulong), ('full', ctypes.c_ulong)]
        s = SPS()
        if ctypes.windll.kernel32.GetSystemPowerStatus(ctypes.byref(s)):
            has_battery = s.flag != 128 and s.flag != 255
            on_battery = has_battery and s.ac == 0
    except (OSError, AttributeError):
        pass
    plan = ''
    try:
        out = subprocess.run(['powercfg', '/getactivescheme'], capture_output=True, text=True, timeout=10,
                             creationflags=NO_WINDOW).stdout
        m = re.search(r'\((.+)\)', out)
        plan = m.group(1) if m else ''
        if 'a1841308-3541-4fab-bc81-f71556f20b4a' in out.lower():
            plan = plan or 'Power saver'
            plan += ' [saver]'
    except (OSError, subprocess.SubprocessError):
        pass
    return on_battery, has_battery, plan


def pc_facts():
    g = gpus()
    on_battery, has_battery, plan = power()
    facts = {'gpus': g, 'on_battery': on_battery, 'laptop': has_battery, 'plan': plan,
             'cpu_threads': os.cpu_count() or 1, 'ram_gb': None}
    try:
        import ctypes
        class Memory(ctypes.Structure):
            _fields_ = [('length', ctypes.c_ulong), ('load', ctypes.c_ulong)] + [
                (name, ctypes.c_ulonglong) for name in ('total', 'available', 'page_total', 'page_available',
                                                       'virtual_total', 'virtual_available', 'extended')]
        mem = Memory()
        mem.length = ctypes.sizeof(mem)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(mem)):
            facts['ram_gb'] = round(mem.total / 2**30, 1)
    except (OSError, AttributeError):
        pass
    try:
        cpu = json.loads(_ps('Get-CimInstance Win32_Processor | Select-Object Name,NumberOfCores | ConvertTo-Json -Compress'))
        cpu = cpu if isinstance(cpu, list) else [cpu]
        facts['cpu_cores'] = sum(int(c['NumberOfCores']) for c in cpu)
        facts['cpu_name'] = ', '.join(c['Name'].strip() for c in cpu)
    except (ValueError, TypeError, KeyError):
        pass
    return facts


def main_gpu(facts):
    dedicated = [(n, m) for n, m in facts['gpus'] if not is_integrated(n)]
    return (dedicated or facts['gpus'] or [('', None)])[0]


def has_fsr4(facts):
    """AMD FSR 4 runs where AMD's driver offers it: Radeon RX 9000, and RX 7000 with a recent driver"""
    n = main_gpu(facts)[0].lower()
    return 'radeon' in n and bool(re.search(r'rx\s*[79]\d{3}', n))


def texture_memory_for(gb):
    """the Texture memory row's value for a card with gb of video memory: Auto takes more than an 8 GB card has room for
    next to the game's own images (logs: 7.1 of 7.0 GB, images moved to system memory, hitches). 1 2 GB, 2 4 GB, 3 6 GB"""
    if gb is None:
        return None
    if gb <= 4.5:
        return 1
    if gb <= 8.5:
        return 2
    if gb <= 12.5:
        return 3
    return 0


def build_preset(key, facts, dlss_ready=False):
    """a preset for this PC: the tier's settings, the texture memory for the card, and the maker's own parts (NVIDIA: Reflex
    and DLSS where it is set up; AMD: Anti-Lag 2 and FSR 4 on cards that run it)"""
    s = dict(PRESETS[key])
    name, gb = main_gpu(facts) if facts else ('', None)
    n = name.lower()
    tm = texture_memory_for(gb)
    # UMA's reserved/reported video memory is not a dedicated card's spare texture cache.
    s['texture_memory'] = 1 if is_integrated(name) else tm if tm is not None else 0
    if 'nvidia' in n:
        s['nvidia_reflex'] = 1
        if dlss_ready:
            s['dlss'] = 2 if key == 'quality' else 1   # (DLAA at full size, DLSS from a smaller 3D)
    elif 'amd' in n or 'radeon' in n:
        s['amd_anti-lag_2'] = 1
        if key != 'performance' and has_fsr4(facts):
            s['dlss'] = 5 if key == 'quality' else 4   # (FSR 4's native AA at full size, FSR 4 from a smaller 3D)
    if key == 'performance':
        threads = (facts or {}).get('cpu_threads') or 0
        ram = (facts or {}).get('ram_gb')
        if (threads and threads <= 8) or (ram is not None and ram < 16):
            s['shader_threads'] = 1  # Two requested; engine clamps to available CPU threads minus one.
        if is_integrated(name):
            s.update(output_res='1280x720', dlss=0, upscaling=1)
        else:
            # (8 GB cards on Performance still reached 7.55 of 8 GB with 4 GB of texture memory: RTX 4060 Laptop, 1.0.2,
            # 2026-11-12. Performance takes 2 GB there)
            if gb is not None and gb <= 8.5:
                s['texture_memory'] = 1
            # (an RX 6600 at 50% render scale still needed 12.5 ms GPU a frame, 44 fps: the FPS target lowers the render
            # scale further only while the card misses 60. A launcher setting, not the game's options file)
            s['fps_target'] = 3
    # Experimental texture reduction remains a separate, explicit player choice.
    return s


def recommend(facts, dlss_ready=False):
    """(the preset name for this PC, its settings, why) from the main graphics card's video memory and class"""
    name, gb = main_gpu(facts)
    n = name.lower()
    cores, ram = facts.get('cpu_cores'), facts.get('ram_gb')
    if (cores is not None and cores <= 4) or (ram is not None and ram < 16):
        key, why = 'performance', 'conservative starting point for CPU / system memory'
    elif not name or is_integrated(name):
        key, why = 'performance', 'integrated graphics'
    elif gb is not None and gb >= 12 and re.search(r'rtx\s*(40[789]0|50[789]0)|rx\s*(7[89]00|9070)', n):
        key, why = 'quality', f'{gb:g} GB video memory' if gb else 'a high-end card'
    elif gb is not None and gb >= 8:
        key, why = 'balanced', f'{gb:g} GB video memory'
    else:
        key, why = 'performance', f'{gb:g} GB video memory' if gb else 'a smaller card'
    if facts.get('laptop') and key == 'quality':
        key, why = 'balanced', why + ', laptop'
    s = build_preset(key, facts, dlss_ready)
    return key, s, name, why


def pc_warnings(facts, active_gpu=None, de=True):
    T = (lambda d, e: d) if de else (lambda d, e: e)
    w = []
    if facts.get('on_battery'):
        w.append(T('Der Laptop läuft im Akkubetrieb: Die Grafikkarte bremst sich dann stark. Schließ das Netzteil an.',
                   'The laptop runs on battery: the graphics card slows itself down a lot. Plug in the charger.'))
    if '[saver]' in facts.get('plan', ''):
        w.append(T('Windows steht auf „Energiesparmodus“. Stell in den Energieoptionen „Ausbalanciert“ oder „Höchstleistung“ ein.',
                   'Windows is on the "Power saver" plan. Choose "Balanced" or "High performance" in the power options.'))
    # (a laptop on the balanced plan: Windows holds its CPU back, and the renderer's CPU time went to 13-26 ms a frame in busy
    # scenes on an i7-14700HX, 40-48 fps; a tester's debug package, 2026-11-12. The plan's name is in Windows' language)
    plan = facts.get('plan', '').lower()
    if facts.get('laptop') and any(n in plan for n in ('balanced', 'ausbalanciert', 'equilibrado', 'équilibré', 'bilanciato',
                                                       'zrównoważony', 'gebalanceerd', 'сбалансир')):
        w.append(T('Laptop im Energieplan „Ausbalanciert“: Windows bremst dabei die CPU. Stell zum Spielen „Höchstleistung“ ein '
                   '(oder im Hersteller-Tool den Leistungsmodus) und schließ das Netzteil an.',
                   'Laptop on the "Balanced" power plan: Windows holds the CPU back. For playing, choose "High performance" '
                   '(or the maker\'s performance mode) and plug in the charger.'))
    # (16 GB of RAM: the game's commit reached ~30 GB on such a laptop and Windows paged most of it out, 5.6 GB in RAM: long
    # hitches. Same tester)
    if 0 < (facts.get('ram_gb') or 0) <= 16.5:
        w.append(T('Nur 16 GB RAM: Das Spiel braucht viel Speicher. Schließ andere Programme (Browser, Discord), stell in den '
                   'Einstellungen → Speicher den RAM-Schutz auf „Stark“ und „Größte Texturen“ auf 1024, und lass Windows die '
                   'Auslagerungsdatei automatisch verwalten.',
                   'Only 16 GB of RAM: the game needs a lot of memory. Close other programs (browser, Discord), set Settings → '
                   'Memory → RAM guard to "Strong" and "Largest textures" to 1024, and let Windows manage the page file '
                   'automatically.'))
    # Adapter enumeration proves the driver is installed, not that its application is running
    # or that shader preparation failed. Ask for a comparison only if it is in use.
    virtual = [n for n, _ in facts.get('gpus', []) if any(k in n.lower() for k in VIRTUAL)]
    if virtual:
        w.append(T(f'Virtueller Bildschirmtreiber „{virtual[0]}“ erkannt. Falls das zugehörige Programm '
                   f'(z. B. Virtual Desktop) läuft, teste zum Vergleich ohne dieses Programm.',
                   f'Virtual display driver "{virtual[0]}" detected. If its application '
                   f'(e.g. Virtual Desktop) is running, test with that application closed for comparison.'))
    dedicated = [n for n, _ in facts.get('gpus', []) if not is_integrated(n)]
    if active_gpu and is_integrated(active_gpu) and dedicated:
        w.append(T(f'Das Spiel lief auf „{active_gpu}“ statt auf „{dedicated[0]}“. Stell in Windows → Grafikeinstellungen '
                   f'Ocarina Reborn auf „Hohe Leistung“.',
                   f'The game ran on "{active_gpu}" instead of "{dedicated[0]}". In Windows → Graphics settings, set Ocarina '
                   f'Reborn to "High performance".'))
    return w


PERF = re.compile(r'\[perf\] fps ([\d.]+) \| frame ([\d.]+) ms avg, ([\d.]+) ms worst \| CPU \(renderer\) ([\d.]+) ms \| GPU '
                  r'([\d.]+) ms \| VRAM \?? ?([\d.]+) / ([\d.]+) GB')


def diagnose(lines, settings=None, de=True):
    """the session in plain words: [(kind, text)], kind 'ok', 'tip' or 'warn'; [] when it has no [perf] lines"""
    T = (lambda d, e: d) if de else (lambda d, e: e)
    lines = list(lines)
    summary = performance.summarize(lines)
    if summary:
        return performance.describe(summary, de)
    gpu_advice = performance.gpu_failure_advice(performance.gpu_failures(lines), de)
    if gpu_advice:
        if performance.memory_events(lines):
            gpu_advice.append(performance.memory_advice(de))
        return gpu_advice
    if performance.memory_events(lines):
        return [performance.memory_advice(de)]
    if any('stats2 seconds ' in line for line in lines):
        return [('tip', T('Noch keine auswertbaren Abschnitte. Spiele mindestens 30 Sekunden bei geschlossenem F1-Menü.',
                          'No usable windows yet. Play for at least 30 seconds with the F1 menu closed.'))]
    rows = []
    for l in lines:
        m = PERF.search(l)
        if m:
            rows.append([float(v) for v in m.groups()])
    rows = [r for r in rows if r[4] > 0.5 or r[3] > 0.5]   # (menus and loading screens: nothing drawn, nothing to judge)
    if len(rows) < 3:
        return []
    fps = sorted(r[0] for r in rows)
    median = fps[len(fps) // 2]
    low = [r for r in rows if r[0] < 55]
    share_low = len(low) / len(rows)
    out = []
    minutes = len(rows) * 5 / 60
    if share_low < 0.1:
        out.append(('ok', T(f'Flüssig: {median:.0f} FPS im Median über {minutes:.0f} Minuten Spielzeit.',
                            f'Smooth: {median:.0f} fps median over {minutes:.0f} minutes of play.')))
    else:
        cpu = sum(r[3] for r in low) / len(low)
        gpu = sum(r[4] for r in low) / len(low)
        worst = min(fps)
        out.append(('warn', T(f'{share_low:.0%} der Zeit unter 55 FPS (Median {median:.0f}, am tiefsten {worst:.0f}).',
                              f'{share_low:.0%} of the time under 55 fps (median {median:.0f}, lowest {worst:.0f}).')))
        up = (settings or {}).get('dlss')
        if abs(gpu - cpu) < 0.15 * max(gpu, cpu):
            out.append(('tip', T(f'Prozessor und Grafikkarte sind beide am Limit (CPU {cpu:.1f} ms, GPU {gpu:.1f} ms pro Bild). '
                                 f'Hilft: ein Upscaler für die Grafikkarte und Programme im Hintergrund schließen.',
                                 f'Processor and graphics card are both at their limit (CPU {cpu:.1f} ms, GPU {gpu:.1f} ms a '
                                 f'frame). Helps: an upscaler for the graphics card, and closing programs in the background.')))
        elif gpu >= cpu:
            out.append(('tip', T(f'Engpass: die Grafikkarte ({gpu:.1f} ms pro Bild, CPU {cpu:.1f} ms). Hilft: ein Upscaler '
                                 f'(NVIDIA DLSS oder AMD FSR 3.1, Qualität) oder eine niedrigere Render-Auflösung.',
                                 f'Bottleneck: the graphics card ({gpu:.1f} ms a frame, CPU {cpu:.1f} ms). Helps: an upscaler '
                                 f'(NVIDIA DLSS or AMD FSR 3.1, Quality) or a lower render resolution.')))
            if str(up) in ('1', '3', '4'):
                out[-1] = ('tip', out[-1][1] + T(' Du nutzt schon einen Upscaler: stell ihn eine Stufe schneller (Balanced).',
                                                 ' You already use an upscaler: set it one step faster (Balanced).'))
        else:
            out.append(('tip', T(f'Engpass: der Prozessor ({cpu:.1f} ms pro Bild für den Renderer, GPU {gpu:.1f} ms). Hilft: '
                                 f'Programme im Hintergrund schließen. Ein Upscaler hilft hier wenig.',
                                 f'Bottleneck: the processor ({cpu:.1f} ms a frame for the renderer, GPU {gpu:.1f} ms). Helps: '
                                 f'closing programs in the background. An upscaler helps little here.')))

    vram = max(rows, key=lambda r: r[5])
    if vram[6] > 0 and vram[5] / vram[6] > 0.9:
        out.append(('tip', T(f'Videospeicher fast voll ({vram[5]:.1f} von {vram[6]:.1f} GB): Texturspeicher '
                             f'eine Stufe senken.', f'Video memory nearly full ({vram[5]:.1f} of {vram[6]:.1f} GB): lower Texture '
                             f'memory one step.')))
    hitches = sum(1 for l in lines if 'over 100 ms' in l)
    if hitches >= 5:
        out.append(('tip', T(f'{hitches} kurze Hänger über 100 ms, meist beim Betreten neuer Bereiche (Laden). Beim zweiten Mal '
                             f'sind es weniger.', f'{hitches} short hitches over 100 ms, mostly when entering new areas '
                             f'(loading). There are fewer the second time.')))
    return out


def vendor_tips(facts, diag=None, de=True):
    """what the graphics card's own driver software adds, for this card's maker (AMD: Fluid Motion Frames, Radeon Super
    Resolution, Anti-Lag 2; NVIDIA: DLSS here, Reflex). Said only for the maker the PC has"""
    T = (lambda d, e: d) if de else (lambda d, e: e)
    name = main_gpu(facts)[0].lower() if facts else ''
    low = any(k == 'warn' for k, _ in (diag or []))
    tips = []
    if 'amd' in name or 'radeon' in name:
        if 'rx 9' in name or 'rx 7' in name:
            tips.append(T('AMD: Für die beste Bildqualität nimm als Upscaler AMD FSR 4 (Qualität-Tab).',
                          'AMD: for the best image, choose AMD FSR 4 as the upscaler (Quality tab).'))
        tips.append(T('AMD: Schalte im Leistung-Tab „AMD Anti-Lag 2“ ein, dann reagiert das Spiel schneller.',
                      'AMD: turn on "AMD Anti-Lag 2" in the Performance tab for a quicker response.'))
    elif 'nvidia' in name:
        tips.append(T('NVIDIA: Schalte im Leistung-Tab „NVIDIA Reflex“ ein, dann reagiert das Spiel schneller.',
                      'NVIDIA: turn on "NVIDIA Reflex" in the Performance tab for a quicker response.'))
    return tips
