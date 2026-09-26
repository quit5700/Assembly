# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from suite_core import collect, program_name

class CollectionTests(unittest.TestCase):
    def test_names(self):
        for original, expected in [('rufus-4.13', 'rufus'), ('WePE_64_V2.3', 'WePE'), ('影视剧整理-v8', '影视剧整理'), ('CON', '_CON'), ('工具 2024', '工具 2024'), ('7-Zip', '7-Zip'), ('IPTV Checker 2.5汉化版_1', 'IPTV Checker')]:
            self.assertEqual(program_name(original), expected)

    def test_dependencies_and_repeat(self):
        with tempfile.TemporaryDirectory(prefix='中文 空格') as tmp:
            root = Path(tmp)
            folder = root / 'v2rayN-windows-64'
            (folder / 'bin').mkdir(parents=True)
            (folder / 'v2rayN.exe').write_bytes(b'primary')
            (folder / 'bin' / 'helper.exe').write_bytes(b'helper')
            (root / '中文 工具-v2.cmd').write_bytes(b'script')
            old = [{'id': 'keep', 'exec_path': 'v2rayN-windows-64/v2rayN.exe', 'description': '保留简介', 'icon': 'custom.png'}]
            entries, errors = collect(root, old, True)
            self.assertFalse(errors)
            self.assertEqual(len(entries), 2)
            self.assertEqual(entries[0]['id'], 'keep')
            self.assertEqual(entries[0]['description'], '保留简介')
            self.assertTrue((root / 'v2rayN' / 'bin' / 'helper.exe').exists())
            repeated, errors = collect(root, entries, True)
            self.assertEqual(entries, repeated)
            self.assertFalse(errors)

    def test_folder_conflict_stays_stable(self):
        with tempfile.TemporaryDirectory(prefix='中文 冲突') as tmp:
            root = Path(tmp)
            for name in ('Tool', 'Tool-v2'):
                (root / name).mkdir()
                (root / name / 'Tool.exe').write_bytes(b'program')
            entries, errors = collect(root, [], True)
            self.assertFalse(errors)
            repeated, errors = collect(root, entries, True)
            self.assertEqual(entries, repeated)
            self.assertTrue((root / 'Tool_2' / 'Tool.exe').exists())

if __name__ == '__main__':
    unittest.main()
