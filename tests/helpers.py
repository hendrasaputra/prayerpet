"""Shared test helpers: an isolated HOME so tests never touch real settings or secrets."""
import importlib
import os
import shutil
import sys
import tempfile
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if ROOT not in sys.path:
    sys.path.insert(0, ROOT)


class IsolatedHome(unittest.TestCase):
    """Runs each test with HOME pointing at a fresh temporary folder."""

    def setUp(self):
        self._old_home = os.environ.get("HOME")
        self.home = tempfile.mkdtemp(prefix="prayerpet-test-")
        os.environ["HOME"] = self.home
        shutil.copy(os.path.join(ROOT, "prayerpet.toml"), os.path.join(self.home, "prayerpet.toml"))
        # these modules resolve ~ at import time
        from prayerpet import bot, inbox
        importlib.reload(inbox)
        importlib.reload(bot)

    def tearDown(self):
        if self._old_home is not None:
            os.environ["HOME"] = self._old_home
        if self.home.startswith(tempfile.gettempdir()):
            shutil.rmtree(self.home, ignore_errors=True)
