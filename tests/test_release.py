import json
import os
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('cc'), 'native launcher test requires a C compiler')
class ReleaseTests(unittest.TestCase):
    def test_launcher_preserves_arguments_and_prefix_paths_with_spaces(self):
        repository = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='mdviewer release ') as directory:
            output = Path(directory)
            environment = os.environ.copy()
            environment['MDVIEWER_BUILD_DIR'] = str(output)
            subprocess.run([str(repository / 'scripts/build.sh')], env=environment,
                           check=True, capture_output=True, text=True)
            architecture = os.uname().machine
            package = output / f'mdviewer-linux-{architecture}'
            script = package / 'share/mdviewer/mdview.py'
            script.write_text('import json,sys; print(json.dumps(sys.argv[1:]))')
            arguments = ['notes with spaces.md', '--output', 'literal $(touch ignored); path']
            result = subprocess.run([str(package / 'bin/mdview'), *arguments],
                                    check=True, capture_output=True, text=True)
            self.assertEqual(json.loads(result.stdout), arguments)
            self.assertTrue((output / f'mdviewer-linux-{architecture}.tar.gz.sha256').is_file())
