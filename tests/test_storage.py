# -*- coding: utf-8 -*-
import copy
import json
import tempfile
import subprocess
import sys
import unittest
from pathlib import Path
from unittest.mock import patch
import 小程序集合 as suite

class StorageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='中文 空格 & 简介 ')
        self.addCleanup(self.tmp.cleanup)
        self.path = Path(self.tmp.name) / '数据.json'
        self.base = [{'id': '一', 'exec_path': '中文 工具/工具.exe', 'description': '', 'icon': ''}]
        self.path.write_text(json.dumps(self.base, ensure_ascii=False), encoding='utf-8')
        self.patches = [patch.object(suite, 'DB_FILE', self.path), patch.object(suite, 'BACKUP_DIR', Path(self.tmp.name) / '备份')]
        for p in self.patches:
            p.start()
            self.addCleanup(p.stop)
        suite.load_db()

    def read(self):
        return json.loads(self.path.read_text(encoding='utf-8'))

    def test_stale_scan_preserves_new_description(self):
        latest = copy.deepcopy(self.base)
        latest[0]['description'] = '后来保存的中文简介'
        self.path.write_text(json.dumps(latest, ensure_ascii=False), encoding='utf-8')
        stale = copy.deepcopy(self.base)
        stale[0]['exec_path'] = '更名目录/工具.exe'
        suite.save_db(stale)
        self.assertEqual(self.read()[0]['description'], '后来保存的中文简介')
        self.assertEqual(self.read()[0]['exec_path'], '更名目录/工具.exe')
        self.assertEqual(stale, self.read())

    def test_explicit_clear_is_saved(self):
        self.base[0]['description'] = '可主动清空'
        self.path.write_text(json.dumps(self.base, ensure_ascii=False), encoding='utf-8')
        edited = suite.load_db()
        edited[0]['description'] = ''
        suite.save_db(edited)
        self.assertEqual(self.read()[0]['description'], '')

    def test_same_field_conflict_does_not_overwrite(self):
        latest = copy.deepcopy(self.base)
        latest[0]['description'] = '其他窗口的简介'
        self.path.write_text(json.dumps(latest, ensure_ascii=False), encoding='utf-8')
        stale = copy.deepcopy(self.base)
        stale[0]['description'] = '旧窗口另一次修改'
        with self.assertRaises(RuntimeError):
            suite.save_db(stale)
        self.assertEqual(self.read(), latest)

    def test_corrupt_database_cannot_be_overwritten(self):
        self.path.write_text('{损坏', encoding='utf-8')
        with self.assertRaises((RuntimeError, ValueError)):
            suite.save_db(self.base)
        self.assertEqual(self.path.read_text(encoding='utf-8'), '{损坏')

    def test_new_and_deleted_entries_are_not_resurrected(self):
        latest = [{'id': '二', 'exec_path': '新增/二.exe', 'description': '新增简介'}]
        self.path.write_text(json.dumps(latest, ensure_ascii=False), encoding='utf-8')
        suite.save_db(copy.deepcopy(self.base))
        self.assertEqual(self.read(), latest)

    def test_backup_contains_previous_data(self):
        edited = copy.deepcopy(self.base)
        edited[0]['description'] = '新简介'
        suite.save_db(edited)
        backups = list(suite.BACKUP_DIR.glob('programs_*.json'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(json.loads(backups[0].read_text(encoding='utf-8')), self.base)

    def test_two_real_processes_preserve_independent_changes(self):
        code = """
import sys
from pathlib import Path
import 小程序集合 as suite
suite.DB_FILE = Path(sys.argv[1])
suite.BACKUP_DIR = suite.DB_FILE.parent / '备份'
data = suite.load_db()
print('ready', flush=True)
sys.stdin.readline()
data[0][sys.argv[2]] = sys.argv[3]
suite.save_db(data)
"""
        processes = []
        try:
            for field, value in [('description', '进程一中文简介'), ('icon', '中文 图标.png')]:
                processes.append(subprocess.Popen([sys.executable, '-X', 'utf8', '-c', code, str(self.path), field, value],
                    cwd=str(Path(suite.__file__).parent), stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, text=True, encoding='utf-8'))
            for process in processes:
                self.assertEqual(process.stdout.readline().strip(), 'ready')
            # 两个进程均已读入空简介，随后同时竞争保存锁。
            for process in processes:
                process.stdin.write('save\n')
                process.stdin.flush()
            for process in processes:
                out, error = process.communicate(timeout=20)
                self.assertEqual(process.returncode, 0, error)
            self.assertEqual(self.read()[0]['description'], '进程一中文简介')
            self.assertEqual(self.read()[0]['icon'], '中文 图标.png')
        finally:
            for process in processes:
                if process.poll() is None:
                    process.kill()
                    process.communicate()
