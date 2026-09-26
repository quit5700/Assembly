# -*- coding: utf-8 -*-
import tempfile
import unittest
from pathlib import Path
from suite_core import collect, application_root

class InternalFolderTests(unittest.TestCase):
    def test_media_and_internal_exclusion(self):
        with tempfile.TemporaryDirectory(prefix='中文 程序集 ') as tmp:
            root = Path(tmp)
            media = root / 'MediaOrganizer'
            media.mkdir()
            (media / '影视剧整理-v8.exe').write_bytes(b'program')
            internal = root / '程序集文件'
            (internal / 'versions').mkdir(parents=True)
            (internal / 'versions' / '旧程序.exe').write_bytes(b'old')
            (internal / '内部脚本.py').write_text('pass', encoding='utf-8')
            (root / 'suite_storage.py').write_text('pass', encoding='utf-8')
            old = [{'id': 'keep', 'name': 'MediaOrganizer', 'exec_path': 'MediaOrganizer/影视剧整理-v8.exe', 'description': '中文简介'}]
            entries, errors = collect(root, old, True)
            self.assertFalse(errors)
            self.assertEqual(len(entries), 1)
            self.assertEqual(entries[0]['id'], 'keep')
            self.assertEqual(entries[0]['description'], '中文简介')
            self.assertTrue((root / '影视剧整理' / '影视剧整理-v8.exe').exists())
            self.assertEqual(entries[0]['name'], '影视剧整理')
            repeated, errors = collect(root, entries, True)
            self.assertFalse(errors)
            self.assertEqual(entries, repeated)
            self.assertTrue((internal / '内部脚本.py').exists())
            self.assertEqual(application_root(root / '小程序集合.exe', internal / '小程序集合.py'), root)
            self.assertEqual(application_root(root / '小程序集合.exe', internal / '小程序集合.py', True), root)
