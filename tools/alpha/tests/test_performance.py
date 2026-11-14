import ast
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'launcher'))
import advisor
import game_settings
import performance


def sample(*, frames=200, seconds=5, cpu=8, gpu=23, used=2, budget=4, known=True,
           menu=0, complete=1, fg=0, draws=1500, worst=40, wait=0, p95=28, p99=35, h50=0, h100=0):
    return (f'[perf] fps {frames / seconds:.1f} | frame {seconds * 1000 / frames:.1f} ms avg, {worst:.1f} ms worst | '
            f'CPU (renderer) {cpu:.1f} ms | GPU {gpu:.1f} ms | VRAM {"" if known else "? "}{used:.2f} / {budget:.2f} GB | '
            f'textures 100 (1000 MB) | draws {draws} (0.0 skipped, 0.0 not ready) | dispatches 10 | uploads 0.00 MB | '
            f'new pipelines 0, waits 0.00 ({wait:.1f} ms) | programs translated 0, failed 0 (all: 0) | '
            f'stats2 seconds {seconds:.3f} frames {frames} p95 {p95:.2f} p99 {p99:.2f} over50 {h50} over100 {h100} '
            f'menu {menu} complete {complete} fg {fg}')


class Measurements(unittest.TestCase):
    def test_auto_texture_memory_offers_relief_for_sustained_pressure(self):
        lines = [sample(cpu=14, gpu=14, used=6.6, budget=6.7)] * 6
        settings = {'texture_memory': 0, 'resolution': 1, 'quality_preset': 3,
                    'volume': 75, 'key_a': '69,0'}
        changes, _ = performance.suggest(performance.summarize(lines), settings,
                                         performance.signature(settings), de=False)
        self.assertEqual(changes, {'texture_memory': 1, 'quality_preset': 0})
        with tempfile.TemporaryDirectory() as d:
            game_settings.write(d, settings)
            game_settings.write(d, changes)
            saved = game_settings.read(d)
            self.assertEqual(saved['texture_memory'], '1')
            self.assertEqual((saved['resolution'], saved['volume'], saved['key_a']), ('1', '75', '69,0'))
        self.assertTrue(any(kind == 'warn' and '90%' in text
                            for kind, text in advisor.diagnose(lines, settings, de=False)))

    def test_auto_memory_does_not_react_to_unknown_brief_or_excluded_pressure(self):
        normal = sample(cpu=6, gpu=6)
        cases = ([sample(cpu=6, gpu=6, used=3.9)] * 2 + [normal] * 4,
                 [sample(cpu=6, gpu=6, used=8, known=False)] * 6,
                 [normal] * 6 + [sample(used=8, menu=1)] * 6,
                 [normal] * 6 + [sample(used=8, draws=1)] * 6)
        for lines in cases:
            s = performance.summarize(lines)
            changes, _ = performance.suggest(s, {}, performance.signature({}))
            self.assertNotIn('texture_memory', changes)
            self.assertFalse(any('90%' in text for _, text in performance.describe(s, False)))

    def test_cache_evidence_survives_launcher_session_filter(self):
        # Exercise the actual production collector without starting its GUI/import side effects.
        source = Path(__file__).resolve().parents[1] / 'launcher' / 'launcher.py'
        tree = ast.parse(source.read_text(encoding='utf-8'))
        nodes = [n for n in tree.body if
                 (isinstance(n, ast.FunctionDef) and n.name == 'session_from_game_log') or
                 (isinstance(n, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'SESSION_KEEP' for t in n.targets))]
        namespace = {'Path': Path, 'performance': performance}
        exec(compile(ast.Module(body=nodes, type_ignores=[]), str(source), 'exec'), namespace)
        cache = ['[hos host] vk: pipeline cache C:/game/mkw_vk_pipelines.bin (1229749 KB)',
                 '[hos host] vk: program cache C:/game/ocarina_reborn_programs.bin: 47866 program keys kept, 7582059 KB']
        with tempfile.TemporaryDirectory() as d:
            Path(d, 'ocarina_reborn_log.txt').write_text('\n'.join(cache + [sample()] * 6 +
                ['[hos Presentation Thread] vk: batched submit 42 failed (-2)']), encoding='utf-8')
            session = namespace['session_from_game_log'](d)
        summary = performance.summarize(session)
        self.assertEqual(summary['pipeline_cache_kb'], 1229749)
        self.assertEqual(summary['program_cache_keys'], 47866)
        self.assertEqual(summary['device_memory_errors'], 1)
        self.assertTrue(any('existing shader/pipeline caches' in text
                            for _, text in advisor.diagnose(session, de=False)))

    def test_absent_empty_or_failed_cache_does_not_claim_cache_exists(self):
        cache = ['vk: pipeline cache C:/game/mkw_vk_pipelines.bin (0 KB)',
                 'vk: program cache C:/game/ocarina_reborn_programs.bin: another Ocarina Reborn is using it: this one runs without it',
                 'vk: pipeline cache: 12 play files merged (33247 KB)',
                 'vk: program cache C:/game/cache.bin: invalid program keys kept, 7582059 KB']
        for lines in ([sample()] * 6, cache + [sample()] * 6):
            summary = performance.summarize(lines)
            self.assertEqual(summary['pipeline_cache_kb'], 0)
            self.assertEqual(summary['program_cache_keys'], 0)
            self.assertFalse(any('existing shader/pipeline caches' in text
                                 for _, text in performance.describe(summary, False)))

    def test_low_base_fps_framegen_advice_without_claiming_it_for_native_frames(self):
        for fg in (0, 8):
            desc = performance.describe(performance.summarize([sample(fg=fg)] * 6), False)
            self.assertEqual(any('Turn frame generation off' in text for _, text in desc), bool(fg))

    def test_virtual_driver_does_not_prove_application_is_active_or_shader_failure(self):
        facts = {'gpus': [('Meta Virtual Monitor', None), ('NVIDIA GeForce RTX 3060 Ti', 8)]}
        text = ' '.join(advisor.pc_warnings(facts, active_gpu='NVIDIA GeForce RTX 3060 Ti', de=False))
        self.assertIn('If its application', text)
        self.assertNotIn('is active', text)
        self.assertNotIn('preparing the shaders', text)

    def test_device_memory_errors_are_not_host_memory_or_device_loss(self):
        lines = [sample()] * 6 + ['[hos Presentation Thread] vk: submit 92402 failed (-2)']
        s = performance.summarize(lines)
        self.assertEqual(s['device_memory_errors'], 1)
        self.assertEqual(s['device_lost_errors'], 0)
        self.assertEqual(s['host_memory_events'], 0)
        self.assertIn('VK_ERROR_OUT_OF_DEVICE_MEMORY', advisor.diagnose(lines, de=False)[0][1])
        settings = {'texture_memory': 0, 'resolution': 4}
        self.assertEqual(performance.suggest(s, settings, performance.signature(settings))[0]['texture_memory'], 1)

    def test_gpu_errors_without_fps_samples_and_unknown_error(self):
        for prefix in ('submit', 'batched submit', 'segment submit'):
            self.assertIn('VK_ERROR_OUT_OF_DEVICE_MEMORY', advisor.diagnose([f'vk: {prefix} 42 failed (-2)'], de=False)[0][1])
        lost = advisor.diagnose(['vk: submit 7925 failed (-4)'], de=False)
        self.assertIn('VK_ERROR_DEVICE_LOST', lost[0][1])
        self.assertNotIn('ran out of', lost[0][1])
        self.assertEqual(advisor.diagnose(['vk: submit 42 failed (-13)'], de=False), [])

    def test_weighted_fps_and_hitch_counts(self):
        s = performance.summarize([sample(), sample(frames=100, seconds=10, worst=160, h50=4, h100=2)])
        self.assertEqual(s['fps'], 300 / 15)
        self.assertEqual((s['over50'], s['over100']), (4, 2))
        self.assertEqual(s['worst_ms'], 160)

    def test_menus_low_draws_and_overflow_do_not_qualify(self):
        self.assertIsNone(performance.summarize([sample(menu=1), sample(draws=4), sample(complete=0)]))

    def test_legacy_log_is_not_new_measurement(self):
        self.assertIsNone(performance.summarize([sample().split(' | stats2')[0]]))

    def test_corrupt_numeric_log_is_ignored(self):
        self.assertIsNone(performance.summarize([sample().replace('p95 28.00', 'p95 28..0')]))

    def test_missing_cpu_counter_does_not_guess_gpu_bottleneck(self):
        s = performance.summarize([sample(cpu=0)] * 6)
        settings = {'resolution': 1}
        self.assertFalse(performance.suggest(s, settings, performance.signature(settings))[0])

    def test_excluded_new_samples_do_not_fall_back_to_old_diagnostics(self):
        diag = advisor.diagnose([sample(menu=1)] * 6)
        self.assertIn('keine auswertbaren', diag[0][1])

    def test_corrupt_counts_and_percentiles_rejected(self):
        self.assertIsNone(performance.summarize([sample(h50=1, h100=2), sample(p95=40, p99=20)]))

    def test_unknown_vram_does_not_trigger_pressure(self):
        s = performance.summarize([sample(used=6, budget=4, known=False)] * 6)
        self.assertEqual(s['vram_pressure_seconds'], 0)

    def test_framegen_is_counted_as_game_frames_and_disabled_first(self):
        s = performance.summarize([sample(fg=2)] * 6)
        settings = {'resolution': 1, 'frame_generation': 2}
        changes, _ = performance.suggest(s, settings, performance.signature(settings))
        self.assertEqual(s['fps'], 40)
        self.assertEqual(changes, {'frame_generation': 0})

    def test_minimum_duration_and_stale_settings(self):
        settings = {'resolution': 1}
        old = performance.signature(settings)
        for summary, current in ((performance.summarize([sample()] * 5), settings),
                                 (performance.summarize([sample()] * 6), {'resolution': 4})):
            self.assertFalse(performance.suggest(summary, current, old)[0])

    def test_cpu_bound_reduces_scene_work_instead_of_resolution(self):
        settings = {'resolution': 1}
        sig = performance.signature(settings)
        gpu = performance.summarize([sample()] * 6)
        cpu = performance.summarize([sample(cpu=25, gpu=6)] * 6)
        self.assertEqual(performance.suggest(gpu, settings, sig)[0], {'resolution': 2})
        self.assertEqual(performance.suggest(cpu, settings, sig)[0], {'view_distance': 0, 'grass': 1})

    def test_cpu_drops_with_gpu_headroom_keep_dlaa_and_limit_frame_rate(self):
        # Tester: 5800X / RTX 4070 SUPER, DLAA, 120 fps cap; busy areas have ~19 ms renderer CPU vs ~12 ms GPU.
        s = performance.summarize([sample(frames=214, cpu=19, gpu=12.2)] * 6)
        settings = {'resolution': 1, 'dlss': 2, 'frame_rate_cap': 2, 'view_distance': 2,
                    'grass': 2, 'shadow_distance': 1, 'quality_preset': 4}
        changes, reasons = performance.suggest(s, settings, performance.signature(settings), de=False)
        self.assertEqual(changes, {'view_distance': 1, 'grass': 1, 'frame_rate_cap': 0, 'quality_preset': 0})
        self.assertTrue(any('renderer CPU' in reason for reason in reasons))
        self.assertTrue(any('renderer CPU' in text for _, text in performance.describe(s, False)))

    def test_cpu_recommendations_ignore_loads_missing_gpu_and_brief_dips(self):
        settings = {'resolution': 1, 'frame_rate_cap': 2}
        for lines in ([sample(cpu=25, gpu=6, worst=1000)] * 6,
                      [sample(cpu=25, gpu=6, wait=10)] * 6,
                      [sample(cpu=25, gpu=0)] * 6,
                      [sample(cpu=25, gpu=6)] + [sample(frames=300, cpu=7, gpu=6)] * 10):
            s = performance.summarize(lines)
            self.assertFalse(performance.suggest(s, settings, performance.signature(settings))[0])

    def test_scene_setting_change_invalidates_previous_measurement(self):
        s = performance.summarize([sample(cpu=25, gpu=6)] * 6)
        before = performance.signature({})
        for key, value in (('view_distance', 0), ('grass', 1), ('shadow_distance', 0)):
            self.assertFalse(performance.suggest(s, {key: value}, before)[0])

    def test_cpu_tuning_does_not_go_below_minimum_or_raise_existing_cap(self):
        s = performance.summarize([sample(cpu=25, gpu=6)] * 6)
        settings = {'view_distance': 0, 'grass': 0, 'frame_rate_cap': 0}
        self.assertFalse(performance.suggest(s, settings, performance.signature(settings))[0])

    def test_loading_and_compile_stalls_do_not_reduce_resolution(self):
        settings = {'resolution': 1}
        for line in (sample(worst=1000), sample(wait=10)):
            s = performance.summarize([line] * 6)
            self.assertFalse(performance.suggest(s, settings, performance.signature(settings))[0])

    def test_dynamic_and_native_aa_left_alone(self):
        s = performance.summarize([sample()] * 6)
        for settings in ({'resolution': 0}, {'resolution': 1, 'dlss': 2}, {'resolution': 1, 'dlss': 5}):
            self.assertFalse(performance.suggest(s, settings, performance.signature(settings))[0])

    def test_memory_pressure_and_custom_preset(self):
        s = performance.summarize([sample(gpu=6, used=3.8)] * 6)
        settings = {'texture_memory': 2, 'quality_preset': 3, 'texture_saving': 0}
        changes, _ = performance.suggest(s, settings, performance.signature(settings))
        self.assertEqual(changes, {'texture_memory': 1, 'quality_preset': 0})
        self.assertNotIn('texture_saving', changes)

    def test_percentile_description_states_window_scope(self):
        description = performance.describe(performance.summarize([sample()]), False)
        self.assertIn('Worst 5-second window', description[1][1])


class Profiles(unittest.TestCase):
    def test_performance_overwrites_expensive_scene_settings_and_120fps_cap(self):
        facts = dict(gpus=[('NVIDIA GeForce RTX 4070 SUPER', 12)], cpu_threads=16, ram_gb=64)
        with tempfile.TemporaryDirectory() as d:
            game_settings.write(d, {'view_distance': 4, 'grass': 4, 'shadow_distance': 3,
                                    'frame_rate_cap': 2, 'volume': 75, 'key_a': '69,0'})
            profile = advisor.build_preset('performance', facts, dlss_ready=True)
            game_settings.write(d, {k: v for k, v in profile.items() if k != 'fps_target'})
            saved = game_settings.read(d)
            self.assertEqual([saved[k] for k in ('view_distance', 'grass', 'shadow_distance', 'frame_rate_cap')],
                             ['0', '1', '0', '0'])
            self.assertEqual((saved['volume'], saved['key_a']), ('75', '69,0'))
            game_settings.write(d, advisor.build_preset('quality', facts, dlss_ready=True))
            saved = game_settings.read(d)
            self.assertEqual([saved[k] for k in ('view_distance', 'grass', 'shadow_distance')], ['1', '2', '1'])

    def test_missing_scene_options_display_the_engines_original_defaults(self):
        for key, default in (('view_distance', 1), ('grass', 2), ('shadow_distance', 1)):
            choices = next(ch for k, _, _, ch in game_settings.ROWS if k == key)
            self.assertEqual(game_settings.current({}, key, choices)[0], default)
            self.assertEqual(performance.signature({})[key], str(default))

    def test_low_end_uses_cpu_ram_and_no_framegen(self):
        facts = dict(gpus=[('NVIDIA GeForce RTX 3060', 12)], cpu_cores=4, cpu_threads=8, ram_gb=16)
        key, profile, *_ = advisor.recommend(facts)
        self.assertEqual(key, 'performance')
        self.assertEqual(profile['frame_generation'], 0)
        self.assertEqual(profile['output_res'], '1920x1080')
        self.assertEqual(profile['shader_threads'], 1)
        self.assertNotIn('texture_saving', profile)

    def test_vram_alone_does_not_choose_quality(self):
        key, *_ = advisor.recommend(dict(gpus=[('NVIDIA GeForce RTX 3060', 12)], cpu_cores=8, ram_gb=32))
        self.assertEqual(key, 'balanced')

    def test_integrated_memory_and_resolution(self):
        facts = dict(gpus=[('AMD Radeon(TM) Graphics', 0.5)], cpu_threads=8, ram_gb=16)
        p = advisor.build_preset('performance', facts)
        self.assertEqual((p['output_res'], p['dlss'], p['frame_generation']), ('1280x720', 0, 0))

    def test_performance_does_not_enable_fsr4_by_vendor(self):
        p = advisor.build_preset('performance', dict(gpus=[('AMD Radeon RX 7900 XTX', 24)]))
        self.assertEqual(p['dlss'], 3)

    def test_low_memory_and_unknown_hardware(self):
        key, *_ = advisor.recommend(dict(gpus=[('AMD Radeon RX 7900 XTX', 24)], ram_gb=8, cpu_cores=8))
        self.assertEqual(key, 'performance')
        self.assertEqual(advisor.recommend(dict(gpus=[]))[0], 'performance')

    def test_experimental_option_roundtrip_and_reset(self):
        with tempfile.TemporaryDirectory() as d:
            game_settings.write(d, {'texture_saving': 2, 'volume': 75, 'output_res': '1280x720'})
            self.assertEqual(game_settings.read(d)['texture_saving'], '2')
            game_settings.reset(d)
            self.assertEqual(game_settings.read(d), {'volume': '75'})
        self.assertEqual(game_settings.DEFAULTS['texture_saving'], 0)

    def test_output_signature_accepts_legacy_and_size(self):
        self.assertEqual(performance.signature({'output_res': 3}), performance.signature({'output_res': '1920x1080'}))


def run_summary(seconds=120, fps=60.0, over50=2, over100=0, p99=40.0):
    return dict(schema=2, seconds=seconds, fps=fps, over50=over50, over100=over100, p99_worst_window=p99)


class RebornAuto(unittest.TestCase):
    def test_short_runs_give_no_verdict(self):
        verdict, lines = performance.compare(run_summary(seconds=30), run_summary(), de=False)
        self.assertIsNone(verdict)
        self.assertIn('60', lines[0])

    def test_missing_run_gives_no_verdict(self):
        self.assertIsNone(performance.compare(None, run_summary())[0])

    def test_fewer_hitches_and_more_fps_is_better(self):
        verdict, _ = performance.compare(run_summary(fps=45, over50=20, over100=6, p99=120),
                                         run_summary(fps=55, over50=4, over100=0, p99=60))
        self.assertEqual(verdict, 'better')

    def test_slower_with_more_hitches_is_worse(self):
        verdict, _ = performance.compare(run_summary(fps=58, over50=2), run_summary(fps=50, over50=12, p99=90))
        self.assertEqual(verdict, 'worse')

    def test_noise_is_the_same(self):
        verdict, _ = performance.compare(run_summary(fps=59.5, over50=3), run_summary(fps=60.0, over50=2))
        self.assertEqual(verdict, 'same')

    def test_hitches_compared_per_minute(self):
        # twice as long, twice the hitches: the same rate
        verdict, _ = performance.compare(run_summary(seconds=60, over50=10), run_summary(seconds=120, over50=20))
        self.assertEqual(verdict, 'same')


if __name__ == '__main__':
    unittest.main()
