import sys
import unittest
from argparse import Namespace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from scripts.install import resolve_skill_choices  # noqa: E402


class InstallerChoiceTests(unittest.TestCase):
    @staticmethod
    def args(codex=None, claude=None, yes=True):
        return Namespace(codex=codex, claude=claude, yes=yes)

    def test_codex_flag_alone_does_not_install_claude(self):
        self.assertEqual(resolve_skill_choices(self.args(codex=True)), (True, False))

    def test_claude_flag_alone_does_not_install_codex(self):
        self.assertEqual(resolve_skill_choices(self.args(claude=True)), (False, True))

    def test_both_explicit_flags_install_both(self):
        self.assertEqual(resolve_skill_choices(self.args(codex=True, claude=True)), (True, True))

    def test_yes_without_skill_flags_keeps_both_defaults(self):
        self.assertEqual(resolve_skill_choices(self.args()), (True, True))
