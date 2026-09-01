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


class TestBypassCommandCoverage:
    """增量审阅 P3-17：cp/mv/tee/sed -i/dd/git checkout 等绕过命令同样拦截。"""

    def test_cp_overwrite_index_db(self):
        assert _looks_like_direct_projection_write("cp backup.db .webnovel/index.db") is True

    def test_mv_overwrite_index_db(self):
        assert _looks_like_direct_projection_write("mv x.db .webnovel/index.db") is True

    def test_tee_append_projection_log(self):
        assert _looks_like_direct_projection_write("echo x | tee .webnovel/projection_log.jsonl") is True

    def test_sed_inplace_scratchpad(self):
        assert _looks_like_direct_projection_write("sed -i 's/a/b/' .webnovel/memory_scratchpad.json") is True

    def test_dd_of_commits(self):
        assert _looks_like_direct_projection_write("dd if=x of=.story-system/commits/chapter_001.commit.json") is True

    def test_git_checkout_commits(self):
        assert _looks_like_direct_projection_write("git checkout HEAD -- .story-system/commits/") is True

    def test_read_only_grep_on_protected_still_allowed(self):
        assert _looks_like_direct_projection_write("grep foo .webnovel/index.db") is False





