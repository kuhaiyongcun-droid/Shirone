"""Verify real child stdout/exit forwarding, including Windows hidden processes."""
import contextlib
import io
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import writing


class WritingWrapperTests(unittest.TestCase):
    def test_json_output_survives_hidden_child(self):
        output = io.StringIO()
        with contextlib.redirect_stdout(output):
            status = writing.invoke([sys.executable, "-c", "import json; print(json.dumps({'passed':True}))"])
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(output.getvalue()), {"passed": True})

    def test_failure_keeps_diagnostic_and_exit_code(self):
        output, errors = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(output), contextlib.redirect_stderr(errors):
            status = writing.invoke([sys.executable, "-c", "import sys; print('expected failure',file=sys.stderr); sys.exit(7)"])
        self.assertEqual(status, 7)
        self.assertIn("expected failure", errors.getvalue())


if __name__ == "__main__":
    unittest.main()
