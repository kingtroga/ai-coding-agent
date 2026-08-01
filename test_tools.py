"""
Unit tests for tools.py. These do not require an API key -- they test the
sandboxed file operations the agent relies on, independent of the LLM loop.

Run with: python -m unittest test_tools.py -v
"""

import os
import shutil
import tempfile
import unittest

import tools


class ToolsTestCase(unittest.TestCase):
    def setUp(self):
        self.repo = tempfile.mkdtemp()
        os.makedirs(os.path.join(self.repo, "app", "models"))
        with open(os.path.join(self.repo, "app", "models", "note.model.js"), "w") as f:
            f.write("const mongoose = require('mongoose');\n")
        with open(os.path.join(self.repo, "package.json"), "w") as f:
            f.write('{"name": "demo"}\n')

    def tearDown(self):
        shutil.rmtree(self.repo, ignore_errors=True)

    def test_list_directory_shows_structure(self):
        out = tools.list_directory(self.repo)
        self.assertIn("app/", out)
        self.assertIn("note.model.js", out)
        self.assertIn("package.json", out)

    def test_read_file_returns_numbered_lines(self):
        out = tools.read_file(self.repo, "app/models/note.model.js")
        self.assertTrue(out.startswith("    1\t"))
        self.assertIn("mongoose", out)

    def test_read_file_missing_raises(self):
        with self.assertRaises(tools.ToolError):
            tools.read_file(self.repo, "does/not/exist.js")

    def test_write_file_creates_and_updates(self):
        msg1 = tools.write_file(self.repo, "app/routes/note.routes.js", "module.exports = {};\n")
        self.assertTrue(msg1.startswith("Created"))
        with open(os.path.join(self.repo, "app", "routes", "note.routes.js")) as f:
            self.assertIn("module.exports", f.read())

        msg2 = tools.write_file(self.repo, "app/routes/note.routes.js", "module.exports = { a: 1 };\n")
        self.assertTrue(msg2.startswith("Updated"))

    def test_search_code_finds_matches(self):
        out = tools.search_code(self.repo, "mongoose")
        self.assertIn("note.model.js", out)

    def test_search_code_no_matches(self):
        out = tools.search_code(self.repo, "nonexistent_symbol_xyz")
        self.assertIn("No matches", out)

    def test_path_traversal_is_blocked_on_read(self):
        with self.assertRaises(tools.ToolError):
            tools.read_file(self.repo, "../outside.txt")

    def test_path_traversal_is_blocked_on_write(self):
        with self.assertRaises(tools.ToolError):
            tools.write_file(self.repo, "../../outside.txt", "malicious")

    def test_run_command_executes_in_repo_root(self):
        out = tools.run_command(self.repo, "ls")
        self.assertIn("exit_code=0", out)
        self.assertIn("package.json", out)


if __name__ == "__main__":
    unittest.main()
