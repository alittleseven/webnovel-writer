"""Tests for guard_runtime_write redirect regex fix (P0-5)."""
import pytest
import sys
import os

from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'hooks'))
from guard_runtime_write import _looks_like_direct_projection_write


class TestRedirectDetection:
    def test_bash_simple_redirect_to_commits(self):
        """echo foo > .story-system/commits/ should be blocked."""
        cmd = 'echo test > .story-system/commits/chapter_001.commit.json'
        assert _looks_like_direct_projection_write(cmd) is True

    def test_powershell_set_content_to_index_db(self):
        cmd = "Set-Content .webnovel/index.db 'data'"
        assert _looks_like_direct_projection_write(cmd) is True

    def test_runtime_safe_command_allowed(self):
        cmd = 'python webnovel.py --project-root /tmp chapter-commit --chapter 1'
        assert _looks_like_direct_projection_write(cmd) is False

    def test_unrelated_command_allowed(self):
        cmd = 'echo hello > output.txt'
        assert _looks_like_direct_projection_write(cmd) is False

    def test_double_redirect_append(self):
        cmd = 'echo more >> .webnovel/memory_scratchpad.json'
        assert _looks_like_direct_projection_write(cmd) is True

    def test_chapter_commit_direct_call_blocked(self):
        cmd = 'python chapter_commit.py --chapter 1'
        assert _looks_like_direct_projection_write(cmd) is True





