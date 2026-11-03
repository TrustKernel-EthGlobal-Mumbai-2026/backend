import contextlib
import io
import json
import sqlite3
import tempfile
import unittest
from pathlib import Path

from procedural_loop.recording import Recorder, inspect_recording, query


class RecordingTests(unittest.TestCase):
    def create(self, root):
        path = Path(root)/'record'
        with contextlib.redirect_stdout(io.StringIO()), Recorder(path,'test-loop') as recorder:
            recorder.emit('assessment.completed', {'status':'FAIL','quote':'synthetic Ω'}, as_of='2026-11-02T09:01:01Z')
            recorder.emit('refresh.requested', {'evidence_id':'price'})
        return path

    def test_query_preserves_witness_text_and_kind_filter(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.create(root)
            self.assertEqual(inspect_recording(path)['events'],2)
            self.assertEqual(query(path,'assessment.completed')[0]['payload']['quote'],'synthetic Ω')
            self.assertEqual(query(path,'absent'),[])

    def test_jsonl_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.create(root)
            text = (path/'trace.jsonl').read_text(encoding='utf-8').replace('synthetic Ω','altered Ω')
            (path/'trace.jsonl').write_text(text,encoding='utf-8')
            with self.assertRaisesRegex(ValueError,'TRACE_CHAIN'):
                inspect_recording(path)

    def test_index_tampering_is_detected(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.create(root)
            db = sqlite3.connect(path/'trace.sqlite')
            try:
                db.execute('DELETE FROM events WHERE seq=1')
                db.commit()
            finally:
                db.close()
            with self.assertRaisesRegex(ValueError,'INDEX_PARITY'):
                inspect_recording(path)

    def test_existing_directory_is_not_overwritten(self):
        with tempfile.TemporaryDirectory() as root:
            path = self.create(root)
            before = (path/'trace.jsonl').read_bytes()
            with self.assertRaises(FileExistsError):
                Recorder(path,'test-loop')
            self.assertEqual((path/'trace.jsonl').read_bytes(),before)


if __name__ == '__main__':
    unittest.main()
