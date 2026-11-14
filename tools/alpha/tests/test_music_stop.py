"""Compile production voice calls around authored stop/restart scenarios. No game/device."""
import importlib.util
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile
import unittest

ALPHA = Path(__file__).resolve().parents[1]
ROOT = ALPHA.parents[1]
ENGINE = Path(os.environ.get('OCARINA_AUDIO_ENGINE', str(ROOT / 'engine')))
if not ENGINE.is_dir():
    ENGINE = ROOT / 'build/alpha/stage/engine'


def module(name, path):
    spec = importlib.util.spec_from_file_location(name, path)
    value = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(value)
    return value


def actual_code(source):
    # The extraction boundaries follow Hookshot's existing audio wave-buffer test.
    helper = module('audio_test_blocks', ENGINE / 'tests/test_audio_deadline.py')
    constants = []
    for name in ('FRAME', 'RATE', 'AU_MAGIC', 'MAX_VOICES', 'MAX_MIXES', 'MAX_SPLITTERS',
                 'MAX_SPLIT_DESTS', 'MAX_CH', 'MAX_BUF', 'MAX_WB', 'MAX_REL', 'MAX_EFFECTS'):
        values = re.findall(r'^#define ' + name + r'\s+[^\n]+', source, re.M)
        assert len(values) == 1, name
        constants.extend(values)
    code = ['\n'.join(constants), source[source.index('enum { K_VOICE'):source.index('static CRITICAL_SECTION lock;')], '''
static Voice voices[MAX_VOICES];
static Mix mixes[MAX_MIXES];
static Splitter splitters[MAX_SPLITTERS];
static uint64_t split_bq_epoch;
static int sink_mix = -1;
static void source_frame(Voice *v, const WB *w, int64_t s, float *out) { (void)v; (void)w; (void)s; memset(out, 0, MAX_CH * sizeof *out); out[0] = 0.5f; }
static void adpcm_seek(Voice *v, const WB *w) { (void)v; (void)w; }
static int16_t adpcm_sample(Voice *v, const WB *w, int64_t s) { (void)v; (void)w; (void)s; return 0; }
''']
    aux = source.index('typedef struct {', source.index('/* ---- Aux:'))
    code.append(source[aux:source.index('static int aux_ring_read(', aux)])
    code.append(helper.block(source, 'static void aux_reset('))
    code.extend(helper.block(source, marker) for marker in (
        'static void put_handle(', 'static int get_handle(', 'static int voice_index(', 'static Voice *voice_of(',
        'static WB read_wb(', 'static void release_wb(', 'static int next_source_frame(',
        'static void biquad_frame(', 'static void render_voice('))
    code.append(source[source.index('enum { OP_VOICE_RELEASE'):source.index('static int64_t last_update_ns;')])
    code.append('static int64_t last_update_ns;')
    for marker in ('static void audio_voice_diagnostic(', 'static void audio_status_diagnostic('):
        code.append(helper.block(source, marker))
    for name in ('apply', 'submit', 'apply_pending', 'commit'):
        if 'static void ' + name + '(' in source:
            code.append(helper.block(source, 'static void ' + name + '('))
    timeout = re.search(r'if \(ncmds && hos_now_ns\(\) - last_update_ns > 50000000\) [a-z_]+\(\);', source)
    assert timeout, 'Renderer fallback update must be covered'
    code.append('static int64_t last_update_ns;\n'
                'static int64_t hos_now_ns(void) { return 60000000; }\n'
                'static void timeout_update(void) { ' + timeout.group(0) + ' }')
    code.extend(helper.block(source, 'HLE(_ZN2nn5audio' + name + ')') for name in (
        '16AppendWaveBufferEPNS0_9VoiceTypeEPKNS0_10WaveBufferE', '21GetReleasedWaveBufferEPNS0_9VoiceTypeE',
        '18GetWaveBufferCountEPKNS0_9VoiceTypeE', '17SetVoicePlayStateEPNS0_9VoiceTypeENS1_9PlayStateE',
        '25GetVoicePlayedSampleCountEPKNS0_9VoiceTypeE'))
    return '\n\n'.join(code)


class MusicStopTests(unittest.TestCase):
    def test_upgrade_of_existing_fix_is_idempotent(self):
        patcher = module('audio_patch_upgrade', ALPHA / 'engine_audio.py')
        source = (ENGINE / 'host/nn_audio.c').read_text(encoding='utf-8')
        fixed = patcher.patch_group(source, patcher.MARKER, patcher.CHANGES)
        fixed = patcher.patch_group(fixed, patcher.TIMEOUT_MARKER, patcher.TIMEOUT_CHANGES)
        previous = fixed
        for old, new in reversed(patcher.TIMEOUT_CHANGES):
            previous = previous.replace(new, old, 1)
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'host/nn_audio.c'; path.parent.mkdir()
            path.write_text(previous, encoding='utf-8')
            patcher.apply(Path(temp))
            self.assertEqual(path.read_text(encoding='utf-8'), fixed)
            before = path.read_bytes(); patcher.apply(Path(temp))
            self.assertEqual(path.read_bytes(), before)

    def test_changed_anchor_leaves_engine_untouched(self):
        patcher = module('audio_patch_atomic', ALPHA / 'engine_audio.py')
        source = (ENGINE / 'host/nn_audio.c').read_text(encoding='utf-8')
        fixed = patcher.patch_group(source, patcher.MARKER, patcher.CHANGES)
        fixed = patcher.patch_group(fixed, patcher.TIMEOUT_MARKER, patcher.TIMEOUT_CHANGES)
        for old, new in reversed(patcher.TIMEOUT_CHANGES):
            fixed = fixed.replace(new, old, 1)
        changed = fixed.replace('last_update_ns > 50000000', 'last_update_ns > 100000000')
        with tempfile.TemporaryDirectory() as temp:
            path = Path(temp) / 'host/nn_audio.c'; path.parent.mkdir()
            path.write_text(changed, encoding='utf-8')
            before = path.read_bytes()
            with self.assertRaises(RuntimeError):
                patcher.apply(Path(temp))
            self.assertEqual(path.read_bytes(), before)

    def test_actual_voice_stop_and_playback_status(self):
        compiler = shutil.which('clang') or shutil.which('gcc')
        if not compiler:
            self.skipTest('C compiler needed for audio regression fixture')
        source_path = ENGINE / 'host/nn_audio.c'
        self.assertTrue(source_path.is_file(), 'Supply OCARINA_AUDIO_ENGINE pointing to staged or exported engine')
        with tempfile.TemporaryDirectory(prefix='reborn-music-stop-') as temp:
            folder = Path(temp); (folder / 'host').mkdir()
            shutil.copy2(source_path, folder / 'host/nn_audio.c')
            patcher = module('reborn_audio_patch', ALPHA / 'engine_audio.py')
            if not os.environ.get('OCARINA_AUDIO_TEST_BASELINE'):
                patcher.apply(folder)
                before = (folder / 'host/nn_audio.c').read_bytes()
                patcher.apply(folder)
                self.assertEqual(before, (folder / 'host/nn_audio.c').read_bytes())
            source = (folder / 'host/nn_audio.c').read_text(encoding='utf-8')
            (folder / 'actual_music_stop.inc').write_text(actual_code(source), encoding='utf-8')
            binary = folder / 'fixture.exe'
            commands = [[compiler, '-std=c11', '-O2', '-Wall', '-Wextra', '-Werror', '-Wno-unused-function',
                         '-I' + str(folder), str(ALPHA / 'tests/music_stop_test.c'), '-lm', '-o', str(binary)], [str(binary)]]
            flags = subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0
            for command in commands:
                result = subprocess.run(command, capture_output=True, text=True, timeout=45, creationflags=flags)
                self.assertEqual(result.returncode, 0, result.stdout + result.stderr)


if __name__ == '__main__':
    unittest.main()
