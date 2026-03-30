"""Tests for the identity module."""

import os
import subprocess

import pytest

from scripts.identity import get_tree_sha, next_cycle, run_dir, run_id


class TestGetTreeSha:
    def test_returns_40_char_hex(self, tmp_path, monkeypatch):
        monkeypatch.chdir(tmp_path)
        subprocess.run(["git", "init"], check=True, capture_output=True)
        subprocess.run(
            ["git", "config", "user.email", "test@test.com"],
            check=True,
            capture_output=True,
        )
        subprocess.run(
            ["git", "config", "user.name", "Test"],
            check=True,
            capture_output=True,
        )
        (tmp_path / "file.txt").write_text("hello")
        subprocess.run(["git", "add", "."], check=True, capture_output=True)

        sha = get_tree_sha(str(tmp_path))

        assert len(sha) == 40
        assert all(c in "0123456789abcdef" for c in sha)

    def test_same_content_gives_same_sha(self, tmp_path, monkeypatch):
        repo_a = tmp_path / "repo_a"
        repo_b = tmp_path / "repo_b"
        repo_a.mkdir()
        repo_b.mkdir()

        for repo in (repo_a, repo_b):
            monkeypatch.chdir(repo)
            subprocess.run(["git", "init"], check=True, capture_output=True)
            subprocess.run(
                ["git", "config", "user.email", "test@test.com"],
                check=True,
                capture_output=True,
            )
            subprocess.run(
                ["git", "config", "user.name", "Test"],
                check=True,
                capture_output=True,
            )
            (repo / "file.txt").write_text("same content")
            subprocess.run(["git", "add", "."], check=True, capture_output=True)

        sha_a = get_tree_sha(str(repo_a))
        sha_b = get_tree_sha(str(repo_b))

        assert sha_a == sha_b


class TestNextCycle:
    def test_first_cycle_is_1(self, tmp_path):
        result = next_cycle(str(tmp_path), "abc123")
        assert result == 1

    def test_increments_after_existing_dir(self, tmp_path):
        (tmp_path / "abc123-1").mkdir()
        result = next_cycle(str(tmp_path), "abc123")
        assert result == 2

    def test_increments_multiple(self, tmp_path):
        (tmp_path / "abc123-1").mkdir()
        (tmp_path / "abc123-2").mkdir()
        (tmp_path / "abc123-3").mkdir()
        result = next_cycle(str(tmp_path), "abc123")
        assert result == 4

    def test_ignores_other_sha_dirs(self, tmp_path):
        (tmp_path / "def456-1").mkdir()
        (tmp_path / "def456-2").mkdir()
        result = next_cycle(str(tmp_path), "abc123")
        assert result == 1

    def test_ignores_dirs_without_cycle_suffix(self, tmp_path):
        (tmp_path / "abc123").mkdir()
        (tmp_path / "abc123-extra").mkdir()
        result = next_cycle(str(tmp_path), "abc123")
        assert result == 1


class TestRunId:
    def test_format(self):
        assert run_id("abc123", 1) == "abc123-1"

    def test_format_higher_cycle(self):
        assert run_id("deadbeef", 42) == "deadbeef-42"


class TestRunDir:
    def test_format(self, tmp_path):
        result = run_dir(str(tmp_path), "abc123", 1)
        assert result == os.path.join(str(tmp_path), "abc123-1")

    def test_format_higher_cycle(self, tmp_path):
        result = run_dir(str(tmp_path), "deadbeef", 5)
        assert result == os.path.join(str(tmp_path), "deadbeef-5")
