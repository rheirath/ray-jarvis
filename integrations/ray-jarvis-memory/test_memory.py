import concurrent.futures
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from memory_server import Memory, handle
from jarvis.core.process_utils import NO_WINDOW_CREATIONFLAGS


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.vault = Path(self.temp.name)
        self.note = self.vault / '03-Projects/Ray-Jarvis/README.md'
        self.note.parent.mkdir(parents=True)
        self.note.write_text('# Ray Jarvis\nOriginal requirements.\n')
        self.memory = Memory(self.vault)

    def tearDown(self):
        self.temp.cleanup()

    def test_restart_preserves_context(self):
        self.memory.save('Memory verified.', 'Connect desktop.')
        requests = [dict(jsonrpc='2.0', id=1, method='initialize'), dict(jsonrpc='2.0', id=2, method='tools/call', params={'name': 'project_context'})]
        process = subprocess.run([sys.executable, str(Path(__file__).with_name('memory_server.py')), '--vault', str(self.vault)], input='\n'.join(map(json.dumps, requests))+'\n', capture_output=True, text=True, encoding='utf-8', creationflags=NO_WINDOW_CREATIONFLAGS, check=True)
        replies = [json.loads(line) for line in process.stdout.splitlines()]
        self.assertEqual(replies[0]['result']['serverInfo']['name'], 'ray-jarvis-memory')
        self.assertIn('Memory verified.', replies[1]['result']['content'][0]['text'])
        self.assertIn('Original requirements.', self.memory.context())

    def test_concurrent_append_preserves_all_updates(self):
        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as pool:
            list(pool.map(lambda n: Memory(self.vault).save(f'Update {n}.', 'Continue.'), range(20)))
        self.assertEqual(self.memory.context().count('## Progress'), 20)

    def test_symlink_is_rejected(self):
        outside = self.vault / 'outside.md'
        outside.write_text('Untouched')
        self.note.unlink()
        self.note.symlink_to(outside)
        with self.assertRaises(ValueError):
            self.memory.save('Change', 'Continue')
        self.assertEqual(outside.read_text(), 'Untouched')

    def test_extra_path_cannot_change_target(self):
        response = handle({'id': 1, 'method': 'tools/call', 'params': {'name': 'save_progress', 'arguments': {'summary': 'Test', 'next_step': 'Next', 'path': '../../outside'}}}, self.memory)
        self.assertTrue(response['result']['isError'])
        self.assertNotIn('Test', self.memory.context())

    def test_invalid_text_rejected(self):
        for value in ('', 'x'*8001, None):
            with self.assertRaises(ValueError):
                self.memory.save(value, 'Next')

    def test_notifications_have_no_response(self):
        self.assertIsNone(handle({'method': 'notifications/initialized'}, self.memory))


if __name__ == '__main__':
    unittest.main()
