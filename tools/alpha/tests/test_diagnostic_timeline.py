import importlib.util
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
import zipfile

ALPHA = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ALPHA / 'launcher'))
import debug_package
import diagnostics
import crash_symbols
import trace_capture
import mods_manager


class ExportTests(unittest.TestCase):
    def test_latest_timeline_precedes_log_backlog_without_duplicates(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folders={k:root/k for k in ('Logs','CrashDumps','Reports','PrepareLogs','ShaderDumps')}
            for p in folders.values():p.mkdir()
            for i in range(10):
                (folders['Logs']/f'{i}.log').write_text('log')
            (folders['CrashDumps']/'run-latest-timeline.jsonl').write_text('{}\n')
            names=[name for _,name in debug_package.candidates(root,folders)]
            self.assertEqual(names[0],'crash/run-latest-timeline.jsonl')
            self.assertEqual(len(names),len(set(names)))

    def test_timeline_summary_handles_repeated_and_incomplete_evidence(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'timeline.jsonl'
            sample={'type':'sample','seq':1,'worst_ms':180,'previous_writer_work_ms':0.7}
            rows=[sample,sample,{'type':'continuation'},[],{'type':'sample','seq':2,'worst_ms':'unknown'}]
            p.write_text('\n'.join(json.dumps(r) for r in rows)+'\n{"partial":')
            result=diagnostics.timeline_summary(p)
            self.assertEqual(result['samples'],2)
            self.assertEqual(result['largest_recorded_frame_ms'],180)
            self.assertEqual(result['malformed_lines'],2)
            self.assertEqual(result['largest_writer_work_ms'],0.7)
            self.assertTrue(result['size_limit_reached'])
            self.assertFalse(result['graceful_recorder_end'])
            self.assertIn('not whole-session',result['coverage'])

    def test_fast_mod_inventory_does_not_walk_assets(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp)/'enabled/romfs').mkdir(parents=True)
            with mock.patch.object(mods_manager.os,'walk',side_effect=AssertionError('must not walk assets')):
                result=mods_manager.list_mods(tmp,count_files=False)
            self.assertEqual(len(result),1)
            self.assertTrue(result[0]['enabled'])

    def test_tiny_remaining_budget_and_outside_paths(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folders={k:root/k for k in ('Logs','CrashDumps','Reports','PrepareLogs','ShaderDumps')}
            for p in folders.values():p.mkdir()
            outside=root/'private.log';outside.write_text('not in Logs')
            self.assertEqual(debug_package.recent([outside,root/'missing'],folders['Logs'],10),[])
            (folders['Logs']/'sample.log').write_text('x'*300)
            with mock.patch.object(debug_package,'TOTAL_LIMIT',64):
                result=debug_package.create(root/'out.zip',root,folders,{},[],{})
            self.assertEqual(result['source_bytes_read'],0)
            self.assertTrue(result['omitted'])

    def test_reports_timeline_redaction_and_no_sensitive_payloads(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp); game=root/'Game';game.mkdir()
            folders={k:root/k for k in ('Logs','CrashDumps','Reports','PrepareLogs','ShaderDumps')}
            for p in folders.values():p.mkdir()
            (folders['Reports']/'performance-new.json').write_text(json.dumps({'game':str(game),'fps':42}))
            (folders['CrashDumps']/'run-new-timeline.jsonl').write_text('{"schema":1,"type":"sample"}\n')
            for name in ('save.bin','prod.keys','private.wav','recording.etl','game.exe'):
                (game/name).write_text('SECRET_GAME_DATA')
            (folders['CrashDumps']/'binary-identities-cache.json').write_text('PRIVATE_PATH_CACHE')
            (folders['Reports']/'trace-secret.etl').write_text('PRIVATE_ETW')
            package=root/'result.zip'
            result=debug_package.create(package,game,folders,{},['system'],{},'Test issue',[(game,'%GAME_DIR%')])
            with zipfile.ZipFile(package) as archive:
                self.assertIn('reports/performance-new.json',archive.namelist())
                self.assertIn('crash/run-new-timeline.jsonl',archive.namelist())
                data=b'\n'.join(archive.read(n) for n in archive.namelist())
                for forbidden in (b'SECRET_GAME_DATA',b'PRIVATE_PATH_CACHE',b'PRIVATE_ETW',str(game).encode()):
                    self.assertNotIn(forbidden,data)
                self.assertEqual(json.loads(archive.read('reports/performance-new.json'))['game'],'%GAME_DIR%')
            self.assertFalse(result['omitted'])

    def test_size_budget_is_reported_and_json_is_not_cut_in_half(self):
        with tempfile.TemporaryDirectory() as tmp:
            root=Path(tmp);folders={k:root/k for k in ('Logs','CrashDumps','Reports','PrepareLogs','ShaderDumps')}
            for p in folders.values():p.mkdir()
            (folders['Logs']/'large.log').write_text('head\n'+'x'*10000+'\ntail')
            (folders['Reports']/'performance-big.json').write_text(json.dumps({'data':'y'*3000}))
            with mock.patch.object(debug_package,'FILE_LIMIT',1024),mock.patch.object(debug_package,'TOTAL_LIMIT',2048):
                result=debug_package.create(root/'out.zip',root,folders,{},[],{})
            self.assertLessEqual(result['source_bytes_read'],2048)
            self.assertTrue(any(f['truncated'] for f in result['files']))
            self.assertTrue(any(f['name'].endswith('performance-big.json') for f in result['omitted']))
            with zipfile.ZipFile(root/'out.zip') as z:
                log=z.read('launcher-logs/large.log');self.assertTrue(log.startswith(b'head'));self.assertTrue(log.endswith(b'tail'))

    def test_binary_identity_changes_when_same_size_binary_is_replaced(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'fake.exe';cache={};p.write_bytes(b'abcd')
            first=diagnostics.binary_identity(p,cache)
            p.write_bytes(b'efgh');os.utime(p,ns=(1,2))
            second=diagnostics.binary_identity(p,cache)
            self.assertNotEqual(first['sha256'],second['sha256'])

    def test_symbol_mismatch_is_never_used(self):
        with tempfile.TemporaryDirectory() as tmp:
            p=Path(tmp)/'symbols.json'
            index={'module':'game.exe','binary_sha256':'right','functions':[[4096,'host_function']]}
            p.write_text(json.dumps(index))
            record={'run_id':'run-test','binaries':[{'name':'game.exe','sha256':'wrong'}],'symbol_indexes':[p.name]}
            text=crash_symbols.resolve('game.exe+0x1008',tmp,record)
            self.assertIn('no matching',text);self.assertNotIn('host_function',text)
            record['binaries'][0]['sha256']='right'
            self.assertIn('host_function+0x8',crash_symbols.resolve('game.exe+0x1008',tmp,record))


class WindowsTraceTests(unittest.TestCase):
    def test_trace_owns_named_session_and_cleans_only_its_session(self):
        calls=[]
        def run(args,**kwargs):
            calls.append(args)
            return subprocess.CompletedProcess(args,0 if '-start' in args or '-cancel' in args else 1,'','stop failed')
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaises(RuntimeError):
                trace_capture.record('wpr.exe',tmp,run=run,sleep=lambda seconds:None)
            self.assertEqual([c[1] for c in calls],['-start','-stop','-cancel'])
            self.assertEqual(len({c[-1] for c in calls}),1)
            self.assertTrue(all(c[-2]=='-instancename' for c in calls))
            self.assertTrue(calls[0][-1].startswith('OcarinaReborn-'))
            self.assertNotIn('-filemode',calls[0])


@unittest.skipUnless(os.name=='nt','Windows recorder')
class NativeRecorderTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        compiler=shutil.which('clang')
        if not compiler:raise unittest.SkipTest('clang needed')
        cls.temp=tempfile.TemporaryDirectory();cls.root=Path(cls.temp.name);cls.exe=cls.root/'recorder.exe'
        subprocess.run([compiler,'-std=c11','-O2','-g','-Wall','-Wextra','-Werror',str(ALPHA/'tests/diagnostic_recorder_test.c'),'-lpsapi','-o',str(cls.exe)],check=True,capture_output=True)

    @classmethod
    def tearDownClass(cls):cls.temp.cleanup()

    def launch(self,mode):
        path=self.root/(mode+'.jsonl');env=dict(os.environ,OCR_TRACE_FILE=str(path),OCR_DIAGNOSTICS='1')
        result=subprocess.run([str(self.exe),mode],env=env,capture_output=True,text=True,timeout=25)
        self.assertEqual(result.returncode,0,result.stderr)
        return result,[json.loads(line) for line in path.read_text(encoding='utf-8').splitlines()]

    def test_low_draw_hitch_marker_stall_context_and_concurrent_io(self):
        _,rows=self.launch('scenario')
        reasons={r['reason'] for r in rows if r['type']=='incident'}
        self.assertTrue({'frame_over_100ms','user_marker','no_frame_progress'}<=reasons)
        samples={r['seq']:r for r in rows if r['type']=='sample'}
        self.assertTrue(any(r['worst_ms']==180 and r['draws']==0 for r in samples.values()))
        self.assertEqual(sum(r['read_bytes'] for r in samples.values()),4*5000*64)
        self.assertEqual(sum(r['decompressed_bytes'] for r in samples.values()),4*5000*128)
        self.assertTrue(any(r['type']=='thread_phase' and r['phase']=='guest_wait' for r in rows))
        self.assertTrue(any(r['thread_cpu'] for r in samples.values()))
        self.assertTrue(any(t['name']=='処理 CPU' for r in samples.values() for t in r['thread_cpu']))
        self.assertTrue(all(r['map']=='TestRoom' and r['loading']==1 for r in samples.values()))
        self.assertTrue(any(r['dropped_events']>0 for r in samples.values()))
        self.assertEqual(rows[-1]['type'],'end')

    def test_cap_rotates_and_keeps_recording(self):
        _,rows=self.launch('cap')
        self.assertEqual([r['type'] for r in rows],['continuation','clock_anchor','after_rotation','end'])
        previous=[json.loads(line) for line in (self.root/'cap.jsonl.previous.jsonl').read_text().splitlines()]
        self.assertEqual(previous[-1]['type'],'limit')
        self.assertTrue(any(r['type']=='clock_anchor' for r in previous))

    def test_exhausted_phase_slots_keep_aggregate_io_without_repeated_scanning(self):
        _,rows=self.launch('slots')
        self.assertEqual(rows[-1]['type'],'end')

    def test_recorder_overhead_and_real_pe_symbol_export(self):
        result,_=self.launch('bench')
        micros=float(result.stdout.split('=')[1].strip())
        self.assertLess(micros,50,'Recorder callback + IO span unexpectedly expensive')
        print(result.stdout.strip())
        spec=importlib.util.spec_from_file_location('diagnostic_symbols',ALPHA.parents[1]/'engine/nx2/diagnostic_symbols.py')
        module=importlib.util.module_from_spec(spec);spec.loader.exec_module(module)
        index=json.loads(module.export(self.exe).read_text())
        self.assertTrue(any(f[1]=='ocr_diag_frame' for f in index['functions']))
        self.assertEqual(index['binary_sha256'],diagnostics.binary_identity(self.exe,{})['sha256'])


if __name__=='__main__':unittest.main()
