"""The game's graphics settings in the launcher: the same keys the in-game menu saves (engine gpu/vk/vk_menu.cpp, its options
file beside the game), so they can be set before a start. Values are the menu's own indices; the game reads them at start.
Only settings the renderer really has: each key is a row of the F1 menu's Graphics tab (Ocarina Reborn's own five, from
Anisotropic filtering to VSync, are read by the renderer itself: hud/ocr_options.h)."""
from pathlib import Path

OFF_ON = [(0, 'Aus', 'Off'), (1, 'An', 'On')]
NV = ' (NVIDIA)'

# (section German, section English, [(ini key, German label, English label, choices, German help, English help, cost), ...])
# cost: '' none worth saying, 'low', 'medium', 'high' (the GPU's work, not measured frame rates)
SECTIONS = [
    ('Anzeige', 'Display', [
        ('fullscreen', 'Vollbild', 'Fullscreen', OFF_ON,
         'Das Spiel füllt den ganzen Bildschirm. Wie F11.', 'Fills the whole screen. The same as F11.', ''),
        ('output_res', 'Ausgabe-Auflösung', 'Output resolution',
         [(3, '1920x1080', '1920x1080'), (0, '2048x1152 (Spiel)', '2048x1152 (game\'s)'), (1, '2560x1440', '2560x1440'),
          (2, '3840x2160', '3840x2160'), (4, '5120x1440', '5120x1440'),
          ('1280x720', '1280x720', '1280x720'), ('1600x900', '1600x900', '1600x900')],
         'Die Größe des fertigen Bildes, HUD inklusive.', 'The size of the finished picture, HUD included.', 'high'),
        ('ultrawide', 'Ultrawide', 'Ultrawide', [(0, '16:9', '16:9'), (1, 'Form des Monitors', 'Monitor\'s shape')],
         'Kamera-Seitenverhältnis auf Bildschirmen, die nicht 16:9 sind.', 'The camera\'s shape on screens that are not 16:9.', ''),
        ('upscaling', 'Fenster-Skalierungsfilter', 'Window scaling filter',
         [(0, 'Aus', 'Off'), (1, 'Catmull-Rom', 'Catmull-Rom'), (2, 'Lanczos', 'Lanczos')],
         'Wie das Bild ans Fenster angepasst wird, wenn die Größen abweichen.', 'How the picture is fitted to the window when sizes differ.', 'low'),
        ('vsync', 'V-Sync', 'V-Sync', [(0, 'Auto', 'Auto'), (1, 'An', 'On'), (2, 'Aus', 'Off')],   # (Hookshot v2.2.0's V-Sync row)
         'Ob ein Bild auf den Bildschirm wartet. An: kein Tearing, etwas mehr Eingabeverzögerung. Auto passt sich an.',
         'Whether a frame waits for the display. On: no tearing, a little more input delay. Auto adapts.', ''),
        ('hdr', 'HDR', 'HDR', [(0, 'Aus', 'Off'), (1, 'Erweitert', 'Expanded'), (2, 'Nativ (Spiel)', 'Native (the game\'s)')],
         'HDR10 auf einem HDR-Bildschirm (Windows: HDR an).', 'HDR10 on an HDR display (Windows: HDR on).', ''),
        ('hdr_paper_white', 'HDR Papierweiß', 'HDR paper white', [(v, f'{v} nits', f'{v} nits') for v in range(80, 401, 20)],
         'Wie hell Weiß mit HDR ist. Etwa 200 für normale Räume.', 'How bright white is with HDR. Around 200 for a normal room.', ''),
        ('hdr_peak_brightness', 'HDR Spitzenhelligkeit', 'HDR peak brightness',
         [(v, f'{v} nits', f'{v} nits') for v in range(400, 4001, 200)],
         'Die hellsten Lichter mit HDR: die Spitzenhelligkeit deines Bildschirms.', 'The brightest highlights with HDR: your display\'s peak.', ''),
    ]),
    ('Qualität', 'Quality', [
        ('quality_preset', 'Qualitäts-Voreinstellung', 'Quality preset',
         [(0, 'Benutzerdefiniert', 'Custom'), (1, 'Minimum (4 GB)', 'Minimum (4GB)'), (2, 'Niedrig (6 GB)', 'Low (6GB)'),
          (3, 'Ausgewogen (8 GB)', 'Balanced (8GB)'), (4, 'Hoch (12 GB)', 'High (12GB)'), (5, 'Ultra (16 GB+)', 'Ultra (16GB+)')],
         'Stellt Skalierung, Frame Generation und Speichergrenzen für so viel Grafikspeicher ein.',
         'Sets scaling, frame generation and memory limits for a GPU with that much memory.', ''),
        # (DLSS and DLAA are not offered: they need NVIDIA's NGX SDK in the build, which Ocarina Reborn does not ship, so the game
        # hides them in its own menu too. A saved 1 or 2 is shown as such and runs as the game's own: UNAVAILABLE below)
        ('dlss', 'Upscaler', 'Upscaler',
         [(0, 'Spiel-eigener', 'Game\'s own'), (3, 'AMD FSR 3.1', 'AMD FSR 3.1'),
          (4, 'AMD FSR 4', 'AMD FSR 4'), (5, 'AMD FSR 4 Native AA', 'AMD FSR 4 Native AA')],
         'Was das 3D-Bild auf die Ausgabe-Auflösung hochrechnet. AMD FSR 3.1 läuft auf jeder Grafikkarte. AMD FSR 4 auf '
         'AMD-Karten, für die AMDs Treiber es anbietet (RX 9000, mit aktuellem Treiber auch RX 7000); sonst rechnet das '
         'Spiel mit seinem eigenen.',
         'What scales the 3D up to the output. AMD FSR 3.1 runs on any graphics card. AMD FSR 4 on AMD cards its driver '
         'offers it for (RX 9000; with a recent driver RX 7000 too); otherwise the game uses its own.', 'medium'),
        ('resolution', 'Render-Auflösung', 'Render resolution',
         [(0, 'Auto (dynamisch)', 'Auto (dynamic)'), (1, '100 %', '100%'), (2, '75 %', '75%'), (3, '67 % (Qualität)', '67% (Quality)'),
          (5, '58 % (Ausgewogen)', '58% (Balanced)'), (4, '50 % (Leistung)', '50% (Performance)'), (6, '33 %', '33%')],
         'Anteil der Ausgabe, in dem das 3D gezeichnet wird; der Upscaler füllt den Rest.',
         'The share of the output the 3D is drawn at; the upscaler fills in the rest.', 'high'),
        ('sharpness', 'Schärfe', 'Sharpness', [(v, f'{v} %', f'{v}%') for v in range(0, 101, 10)],
         'Schärft das fertige Bild. Zu viel zeigt helle Ränder.', 'Sharpens the finished picture. Too much shows halos.', 'low'),
        ('reborn_look', 'Reborn Look', 'Reborn look',   # (engine_v21.py apply_look: the colour grade in the window pass)
         [(0, 'Aus (Originalfarben)', 'Off (original colours)'), (1, 'Reborn', 'Reborn'), (2, 'Lebendig', 'Vivid'),
          (3, 'Warm', 'Warm'), (4, 'Kühl', 'Cool'), (5, 'Kino', 'Cinematic')],
         'Farbabstimmung von Ocarina Reborn für das fertige Bild: kräftigere Farben und Kontrast, warmer oder kühler Ton, '
         'leichte Vignette. Auch im Spiel unter F1 → Grafik, dort sofort sichtbar. Nicht mit HDR.',
         'Ocarina Reborn\'s colour grade for the finished picture: richer colour and contrast, a warm or cool tone, a soft '
         'vignette. Also in game under F1 → Graphics, visible at once. Not with HDR.', 'low'),
        ('bloom', 'Bloom', 'Bloom',   # (engine_v21.py apply_look: the glow in the window pass)
         [(0, 'Aus', 'Off'), (1, 'Leicht', 'Low'), (2, 'Mittel', 'Medium'), (3, 'Stark', 'High')],
         'Weiches Leuchten um helles Licht: Sonne, Feuer, Magie. Von Ocarina Reborn auf das fertige Bild gelegt. '
         'Auch unter F1 → Grafik, dort sofort sichtbar. Nicht mit HDR.',
         'A soft glow around bright light: the sun, fire, magic. Added by Ocarina Reborn on the finished picture. '
         'Also in F1 → Graphics, visible at once. Not with HDR.', 'low'),
        ('fxaa', 'FXAA (Kantenglättung)', 'FXAA (anti-aliasing)', OFF_ON,   # (engine_v21.py apply_look: in the window pass)
         'Glättet treppige Kanten im fertigen Bild. Kostet wenig; mit FSR unnötig, das glättet schon. '
         'Auch unter F1 → Grafik, dort sofort sichtbar.',
         'Smooths jagged edges on the finished picture. Light on performance; not needed with FSR, which smooths already. '
         'Also in F1 → Graphics, visible at once.', 'low'),
        ('view_distance', 'Sichtweite', 'View distance',   # (engine_v21.py apply_view: hud/ocr_view.c)
         [(0, 'Kurz', 'Short'), (1, 'Original', 'Original'), (2, 'Weit', 'Far'), (3, 'Sehr weit', 'Very far'), (4, 'Maximum', 'Max')],
         'Wie weit Bäume, Büsche und detaillierte Modelle reichen. Weiter kostet CPU und GPU. Auch unter F1 → Grafik.',
         'How far trees, bushes and detailed models reach. Further costs CPU and GPU time. Also in F1 → Graphics.', 'medium'),
        ('grass', 'Gras', 'Grass',
         [(0, 'Aus', 'Off'), (1, 'Weniger', 'Less'), (2, 'Original', 'Original'), (3, 'Mehr', 'More'), (4, 'Dicht', 'Dense')],
         'Wie viel Gras wächst. Aus oder Weniger hilft schwachen PCs. Auch unter F1 → Grafik.',
         'How much grass grows. Off or Less helps weaker PCs. Also in F1 → Graphics.', 'medium'),
        ('shadow_distance', 'Schattendistanz', 'Shadow distance',
         [(0, 'Kurz', 'Short'), (1, 'Original', 'Original'), (2, 'Weit', 'Far'), (3, 'Maximum', 'Max')],
         'Wie weit Landschaft und Figuren Schatten werfen. Weiter kostet GPU. Auch unter F1 → Grafik.',
         'How far scenery and characters cast shadows. Further costs GPU time. Also in F1 → Graphics.', 'medium'),
        ('anisotropic_filtering', 'Anisotrope Filterung', 'Anisotropic filtering',
         [(0, 'Wie im Spiel', "The game's"), (1, '2x', '2x'), (2, '4x', '4x'), (3, '8x', '8x'), (4, '16x', '16x')],
         'Schärfere Texturen in flachen Winkeln, z. B. Wege in die Ferne.', 'Sharper textures at steep angles, such as paths into the distance.', 'low'),
        ('texture_detail', 'Texturdetail', 'Texture detail',
         [(0, 'Standard', 'Standard'), (1, 'Hoch', 'High'), (2, 'Ultra', 'Ultra')],
         'Feinere Texturstufen in der Ferne. Ultra kann bei feinen Mustern flimmern.',
         'Finer texture levels further away. Ultra can shimmer on fine patterns.', 'low'),
        ('texture_filtering', 'Texturfilterung', 'Texture filtering', [(0, 'Wie im Spiel', 'The game\'s'), (1, 'Weich', 'Smooth')],
         'Weich: alle Texturen gefiltert, keine pixeligen Ränder bei Rauch, Nebel und Leuchten.',
         'Smooth: every texture filtered, no blocky halos in smoke, fog and glows.', ''),
        ('soft_shadows', 'Weiche Schatten', 'Soft shadows', OFF_ON,
         'Schattenkanten aus vier Proben geglättet statt harter Stufen.', 'Shadow edges blended over four samples instead of hard steps.', 'low'),
    ]),
    ('Leistung', 'Performance', [
        ('frame_generation', 'Frame Generation (FSR 3.1)', 'Frame generation (FSR 3.1)',
         [(0, 'Aus', 'Off'), (1, 'Auto', 'Auto')] + [(i, f'{i}x', f'{i}x') for i in range(2, 9)],
         'Erzeugt Zwischenbilder, erhöht aber nicht die echten Spiel-FPS. Hohe Faktoren können die Basisbildrate begrenzen '
         'und die Eingabeverzögerung erhöhen. Bei Rucklern zuerst Aus testen.',
         'Adds generated frames, not actual game frames. High multipliers can limit the base frame rate '
         'and increase input delay. Test Off first when investigating stutter.', 'medium'),
        ('frame_pacing', 'Frame Pacing', 'Frame pacing', OFF_ON,
         'Zeigt die Bilder in gleichmäßigen Abständen.', 'Shows the frames evenly spaced.', ''),
        ('frame_rate_cap', 'FPS-Limit', 'Frame rate cap',
         [(0, '60 (wie Konsole)', '60 (the console\'s)'), (1, '90', '90'), (2, '120', '120'), (3, '144', '144'),
          (4, '165', '165'), (5, '240', '240')],
         'Die meisten Bilder pro Sekunde, die das Spiel läuft.', 'The most frames a second the game runs at.', 'medium'),
        ('nvidia_reflex', 'NVIDIA Reflex', 'NVIDIA Reflex', [(0, 'Aus', 'Off'), (1, 'An', 'On'), (2, 'An + Boost', 'On + Boost')],
         'Weniger Eingabeverzögerung (nur NVIDIA, nicht mit Frame Generation).',
         'Less input delay (NVIDIA only, not with frame generation).', ''),
        ('amd_anti-lag_2', 'AMD Anti-Lag 2', 'AMD Anti-Lag 2', OFF_ON,
         'Weniger Eingabeverzögerung (nur AMD, nicht mit Frame Generation).',
         'Less input delay (AMD only, not with frame generation).', ''),
        ('handheld_profile', 'Handheld-Profil', 'Handheld profile', OFF_ON,
         'Spielt wie im Handheld-Modus der Konsole: weniger Last.', 'Runs as if the console were undocked: less work.', ''),
        ('fps_counter', 'FPS-Anzeige', 'FPS counter',   # (Hookshot v2.2.0's levels)
         [(0, 'Aus', 'Off'), (1, 'FPS', 'FPS'), (2, 'Frametime', 'Frame time'), (3, 'Graph', 'Graph'), (4, 'Aufschlüsselung', 'Breakdown')],
         'Bilder pro Sekunde im Spiel. Frametime, Graph und Aufschlüsselung zeigen mehr: die Zeit pro Bild und wohin sie geht.',
         'Frames per second in game. Frame time, Graph and Breakdown show more: the time a frame takes and where it goes.', ''),
    ]),
    ('Speicher', 'Memory', [
        ('texture_saving', 'Texturen verkleinern (Test)', 'Texture saving (test)',
         [(0, 'Aus', 'Off'), (1, '1024', '1024'), (2, '512', '512')],
         'Lädt große, grob komprimierte ASTC-Texturarrays mit weniger Detailstufen. Spart dort echten Bildspeicher; '
         'Terrain kann unschärfer werden. Experimentell, standardmäßig aus. Spiel neu starten. Aus stellt die bisherige Auswahl wieder her.',
         'Stores large, coarsely compressed ASTC texture arrays with fewer mip levels. Reduces their image memory; '
         'terrain may look softer. Experimental and off by default. Restart the game. Off restores the original policy.', 'medium'),
        ('texture_memory', 'Texturspeicher', 'Texture memory',
         [(0, 'Auto', 'Auto'), (1, '2 GB', '2 GB'), (2, '4 GB', '4 GB'), (3, '6 GB', '6 GB'), (4, '8 GB', '8 GB'),
          (5, '12 GB', '12 GB'), (6, '16 GB', '16 GB')],
         'Obergrenze für den Texturcache. Mehr kann Nachladen verringern. Treiberlimit und bei integrierter Grafik der gemeinsame RAM begrenzen den tatsächlich nutzbaren Cache.',
         'Upper limit for the texture cache. More can reduce reloads. The driver limit and shared RAM on integrated graphics can reduce the actual cache size.', 'medium'),
    ]),
    ('Shader', 'Shaders', [
        ('pipeline_precompile', 'Pipelines vorbauen', 'Pipeline precompile', OFF_ON,
         'Baut beim Start alle schon benutzten Pipelines vor: weniger Ruckler beim Spielen.',
         'Builds every pipeline the game used before at the start: less stutter while playing.', ''),
        ('shader_cache', 'Shader-Cache', 'Shader cache', OFF_ON,
         'Speichert fertige Shader auf der Festplatte. Aus: jeder Start kompiliert alles neu.',
         'Keeps compiled shaders on disk. Off: every start compiles everything again.', ''),
        ('shader_threads', 'Shader-Threads', 'Shader threads',
         [(0, 'Auto', 'Auto'), (1, '2', '2'), (2, '4', '4'), (3, '6', '6'), (4, '8', '8')],
         'CPU-Threads zum Shader-Kompilieren. Mehr ist schneller, kann aber das Spiel bremsen.',
         'CPU threads compiling shaders. More is faster but can slow the game down.', 'medium'),
    ]),
    # (the game's own Gameplay, Controls and Audio rows: the keys are the in-game menu's, so F1 shows the same choice)
    ('Spiel', 'Gameplay', [
        ('classic_counters', 'Klassische Zähler (N64)', 'Classic counters (N64)', OFF_ON,   # (engine_v21.py apply_counters)
         'Wie auf dem N64: keine Anzeige über Link beim Aufsammeln, Rubine immer sichtbar. Auch unter F1 → Gameplay.',
         'As on the N64: no count over Link when he picks something up, rupees always shown. Also in F1 → Gameplay.', ''),
        ('speedrun_timer', 'Speedrun-Timer', 'Speedrun timer', OFF_ON,   # (engine_v21.py apply_timer)
         'Echtzeit oben links, pausiert bei offenem F1-Menü. Im Spiel unter F1 → Spiel aus- und wieder einschalten setzt ihn auf null.',
         'Real time in the top left corner, paused while the F1 menu is open. Turning it off and on in F1 → Gameplay resets it.', ''),
        ('death_counter', 'Todeszähler', 'Death counter', OFF_ON,   # (engine_v21.py apply_timer)
         'Zeigt oben links, wie oft Links Herzen seit dem Spielstart auf null gefallen sind.',
         'Shows in the top left corner how often Link\'s hearts reached zero since the game started.', ''),
        ('text_speed', 'Textgeschwindigkeit', 'Text speed',
         [(0, 'Normal', 'Normal'), (1, '2x', '2x'), (2, '4x', '4x'), (3, 'Sofort', 'Instant')],
         'Wie schnell die Buchstaben von Dialogen und Meldungen erscheinen.', 'How fast the letters of dialogue and messages appear.', ''),
        ('text_size', 'Textgröße', 'Text size',
         [(0, 'Original', 'Original'), (1, '110%', '110%'), (2, '125%', '125%'), (3, '150%', '150%'), (4, '175%', '175%')],
         'Wie groß Dialoge, Navi und Schilder geschrieben werden.', 'How large dialogue, Navi and signs are drawn.', ''),
        ('game_speed', 'Spielzeit unter 60 FPS', 'Game speed below 60 fps',
         [(1, 'Echtzeit', 'Real time'), (0, 'Pro Bild (langsamer)', 'Per frame (slower)')],
         'Echtzeit: das Spiel bleibt gleich schnell, auch wenn die FPS fallen. Pro Bild: es wird mit den FPS langsamer, wie auf der Konsole.',
         'Real time: the game keeps its speed when the fps drop. Per frame: it slows down with the fps, as on the console.', ''),
    ]),
    ('amiibo', 'amiibo', []),
    ('Tunika', 'Tunic', [
        ('custom_tunic_color', 'Eigene Tunika-Farbe', 'Custom tunic color',
         [(0, 'Original', 'Original'), (1, 'Eigene Farbe', 'Custom color')],
         'Wähle unten eine beliebige Farbe. Speichern und das Spiel neu starten. Original stellt die ursprünglichen Farben wieder her.',
         'Choose any color below. Save and restart the game. Original restores the original colors.', ''),
    ]),
    ('Steuerung', 'Controls', [
        ('mouse_camera', 'Maus-Kamera', 'Mouse camera', [(0, 'Wie der Stick', 'As the stick'), (1, 'Nativ (wie PC-Spiele)', 'Native (as PC games)')],
         'Wie die Maus die Kamera dreht. Nativ dreht direkt, wie man es von PC-Spielen kennt.',
         'How the mouse turns the camera. Native turns it directly, as PC games do.', ''),
        ('mouse_sensitivity', 'Maus-Empfindlichkeit', 'Mouse sensitivity',
         [(v, f'{v / 100:.2f}', f'{v / 100:.2f}') for v in (25, 50, 75, 100, 125, 150, 200, 250, 300, 400, 500)],
         'Wie weit sich die Kamera bei einer Mausbewegung dreht.', 'How far the camera turns for a mouse movement.', ''),
        ('invert_mouse_vertical', 'Maus vertikal umkehren', 'Invert mouse vertical', OFF_ON,
         'Tauscht oben und unten für die Maus.', 'Swaps up and down for the mouse.', ''),
        ('disable_camera_centering', 'Kamera nicht nachführen', 'Disable camera centering', OFF_ON,
         'Die Kamera dreht sich nicht mehr von selbst in Laufrichtung. Passt gut zur nativen Maus-Kamera.',
         'The camera no longer turns toward where you walk by itself. Suits the native mouse camera.', ''),
        ('invert_camera_x', 'Kamera X umkehren', 'Invert camera X', OFF_ON,
         'Kehrt links/rechts am rechten Stick um.', 'Inverts left/right on the right stick.', ''),
        ('invert_camera_y', 'Kamera Y umkehren', 'Invert camera Y', OFF_ON,
         'Kehrt oben/unten am rechten Stick um.', 'Inverts up/down on the right stick.', ''),
        ('stick_dead_zone', 'Stick-Totzone', 'Stick dead zone',
         [(0, 'Standard (24%)', 'Default (24%)'), (1, '5%', '5%'), (2, '10%', '10%'), (3, '15%', '15%'), (4, '20%', '20%'), (5, '30%', '30%')],
         'Wie weit sich ein Stick bewegen muss, bevor das Spiel reagiert. Höher bei driftenden Sticks.',
         'How far a stick moves before the game sees it. Higher for a stick that drifts.', ''),
        ('rumble_strength', 'Vibration', 'Rumble strength',
         [(0, 'Aus', 'Off'), (25, '25%', '25%'), (50, '50%', '50%'), (75, '75%', '75%'), (100, '100%', '100%'), (125, '125%', '125%'), (150, '150%', '150%')],
         'Wie stark der Controller vibriert.', 'How strongly the controller rumbles.', ''),
        ('motion_controls', 'Bewegungssteuerung (Gyro)', 'Motion controls (gyro)', OFF_ON,
         'Zielen mit dem Gyroskop des Controllers (Bogen, Schleuder), wie auf der Switch. Mit Switch Pro, DualShock 4 und DualSense.',
         'Aim with the controller\'s gyroscope (bow, slingshot), as on the Switch. With Switch Pro, DualShock 4 and DualSense.', ''),
        ('button_prompts', 'Tastensymbole', 'Button prompts',
         [(0, 'Automatisch', 'Auto'), (1, 'Switch', 'Switch'), (2, 'Xbox', 'Xbox'), (3, 'PlayStation 4', 'PlayStation 4'),
          (4, 'PlayStation 5', 'PlayStation 5')],
         'Welche Tastensymbole das Spiel in Texten und Menüs zeigt.', 'Which button icons the game shows in its texts and menus.', ''),
    ]),
    ('Audio', 'Audio', [
        ('volume', 'Lautstärke', 'Volume', [(v, f'{v}%', f'{v}%') for v in range(0, 101, 10)],
         'Wie laut das Spiel spielt.', 'How loud the game plays.', ''),
        ('mute_in_background', 'Im Hintergrund stumm', 'Mute in background', OFF_ON,
         'Kein Ton, solange ein anderes Fenster im Vordergrund ist.', 'No sound while another window has the focus.', ''),
    ]),
    ('Erweitert', 'Advanced', [
        ('mesh_shaders', 'Mesh-Shader', 'Mesh shaders',
         [(0, 'Automatisch', 'Automatic'), (1, 'Nativ', 'Native'), (2, 'Compute', 'Compute')],
         'Wie Gras, Bäume und Laub gezeichnet werden. Automatisch wählt passend zur Grafikkarte (AMD RX 6000: Compute, gegen '
         'Treiber-Abstürze); Compute hilft bei Treiberproblemen.',
         'How grass, trees and foliage are drawn. Automatic picks what suits the GPU (AMD RX 6000: Compute, against driver '
         'crashes); Compute helps with driver problems.', ''),
        ('robust_buffers', 'Robuste Puffer', 'Robust buffers', [(0, 'Auto', 'Auto'), (1, 'Aus', 'Off'), (2, 'An', 'On')],
         'Geprüfte Puffer-Zugriffe: verhindert GPU-Abstürze bei fehlerhaften Lesezugriffen.',
         'Bounds-checked buffer reads: a bad read is dropped instead of stopping the GPU.', 'low'),
        ('descriptor_reuse', 'Descriptor-Wiederverwendung', 'Descriptor reuse', OFF_ON,
         'Weniger Arbeit pro Bild, während das Spiel Texturen nachlädt.', 'Less work each frame while the game streams textures.', ''),
        ('sampler_cache', 'Sampler-Cache', 'Sampler cache', OFF_ON,
         'Schnelleres Auflösen von Samplern beim Nachladen von Texturen.', 'Faster sampler lookups while the game streams textures.', ''),
    ]),
]
# (what the game uses while the file has no line for the key)
DEFAULTS = {'texture_saving': 0, 'texture_detail': 1, 'game_speed': 1, 'mouse_sensitivity': 100, 'rumble_strength': 100, 'motion_controls': 1, 'volume': 100, 'anisotropic_filtering': 4, 'soft_shadows': 1, 'pipeline_precompile': 1, 'shader_cache': 1, 'hdr_paper_white': 200, 'hdr_peak_brightness': 1000, 'sharpness': 50, 'frame_pacing': 1}
DEFAULTS.update(view_distance=1, grass=2, shadow_distance=1)  # engine's Original values when absent from the file

# (values an options file can hold that this build cannot run: shown as such when set, never offered)
UNAVAILABLE = {'dlss': {1: ('DLSS (nicht verfügbar)', 'DLSS (not available)'),
                        2: ('DLAA (nicht verfügbar)', 'DLAA (not available)')}}

# every row, flat, in the menu's order of sections (key, German, English, choices) as before
ROWS = [(k, d, e, ch) for _, _, rows in SECTIONS for (k, d, e, ch, *_) in rows]


def ini_file(game):
    for name in ('ocarina_reborn_options.ini', 'hookshot_options.ini'):   # (the engine's name; a folder built before)
        if (Path(game) / name).is_file():
            return Path(game) / name
    return Path(game) / 'ocarina_reborn_options.ini'


def read(game):
    vals = {}
    try:
        for line in ini_file(game).read_text(encoding='utf-8', errors='replace').splitlines():
            if '=' in line and not line.lstrip().startswith(('#', ';')):
                k, v = line.split('=', 1)
                vals[k.strip()] = v.strip()
    except OSError:
        pass
    return vals


def current(vals, key, choices):
    """the choice the file has for key (its default, else the first, when it has none or one not offered here)"""
    raw = vals.get(key, str(DEFAULTS.get(key, choices[0][0])))
    if 'x' in raw:   # (the game writes the output resolution as WxH: the choice with that label)
        hit = next((c for c in choices if c[2].split(' ')[0] == raw or c[1].split(' ')[0] == raw), None)
        if hit:
            return hit
    return next((c for c in choices if str(c[0]) == raw), next((c for c in choices if c[0] == DEFAULTS.get(key)), choices[0]))


def write(game, changes):
    """the changed keys set, every other line kept as it was"""
    f = ini_file(game)
    try:
        lines = f.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        lines = []
    left = dict(changes)
    out = []
    for line in lines:
        k = line.split('=', 1)[0].strip() if '=' in line else None
        if k in left:
            out.append(f'{k}={left.pop(k)}')
        else:
            out.append(line)
    out += [f'{k}={v}' for k, v in left.items()]
    f.write_text('\n'.join(out) + '\n', encoding='utf-8')


def reset(game):
    """the graphics rows' lines taken out of the options file: the game uses its own defaults for them again (every other line,
    the controls and audio among them, stays)"""
    f = ini_file(game)
    try:
        lines = f.read_text(encoding='utf-8', errors='replace').splitlines()
    except OSError:
        return
    keys = {k for _, en, rows in SECTIONS if en not in ('Gameplay', 'Controls', 'Audio', 'Tunic') for k, *_ in rows}   # (graphics only)
    kept = [l for l in lines if not ('=' in l and l.split('=', 1)[0].strip() in keys)]
    f.write_text('\n'.join(kept) + '\n', encoding='utf-8')
