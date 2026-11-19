"""The user's workspace: a git repository holding workflows and resources.

Layout::

    workspace/
      workflows/*.yaml
      resources/assttyys/colors.yaml, resources/oas/..., resources/captures/...

``main`` is what runs. Every automatic change is committed on its own branch
``agent/<workflow>-<kind>-<timestamp>``; it is merged into ``main`` only after
validation (and, depending on the kind, the user's approval). Rollbacks are
``git revert`` of the merge so the history stays complete.
"""
from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from ..errors import AgentflowError
from ..workflow.schema import bundled_dir

GIT_ENV_ID = ["-c", "user.name=onmyoji-agentflow", "-c", "user.email=agent@onmyoji-agentflow.invalid",
              "-c", "commit.gpgsign=false", "-c", "core.autocrlf=false"]


class Workspace:
    def __init__(self, path: str | Path):
        self.path = Path(path)

    # ------------------------------------------------------------------ git
    def git(self, *args, check: bool = True) -> str:
        if shutil.which("git") is None:
            raise AgentflowError("需要安装 git（https://git-scm.com/）才能使用自动修复和回滚")
        res = subprocess.run(["git", *GIT_ENV_ID, *args], cwd=self.path, capture_output=True, text=True,
                             encoding="utf-8", errors="replace")
        if check and res.returncode != 0:
            raise AgentflowError(f"git {' '.join(args)} 失败: {res.stderr.strip() or res.stdout.strip()}")
        return res.stdout.strip()

    @property
    def initialized(self) -> bool:
        return (self.path / ".git").exists()

    def init(self, source: Path | None = None) -> None:
        """Create the workspace from the bundled workflows/resources (or ``source``)."""
        src = Path(source) if source else bundled_dir()
        self.path.mkdir(parents=True, exist_ok=True)
        for sub in ("workflows", "resources"):
            if (src / sub).exists() and not (self.path / sub).exists():
                shutil.copytree(src / sub, self.path / sub)
        (self.path / ".gitattributes").write_text("* -text\n", encoding="utf-8")
        if not self.initialized:
            self.git("init", "-q")
            self.git("checkout", "-q", "-B", "main")
        if (src / "workflows").is_dir():
            names = sorted(p.name for p in (src / "workflows").glob("*.yaml"))
            (self.path / self.KNOWN_FILE).write_text("\n".join(names) + "\n", encoding="utf-8")
        self.git("add", "-A")
        if self.git("status", "--porcelain"):
            self.git("commit", "-q", "-m", "初始化工作流与识别资源")

    def ensure(self) -> "Workspace":
        if not self.initialized:
            self.init()
        else:
            self.add_new_bundled()
        return self

    KNOWN_FILE = ".oaf-bundled-known"

    def add_new_bundled(self, source: Path | None = None) -> list[str]:
        """Copy workflows a newer version ships that this workspace has never seen.

        An upgraded install keeps its old workspace, so workflows added in a later release (home,
        daily_rewards, event_boss, ...) would otherwise be missing and ``oaf marathon`` would fail
        on them. Existing files are never touched, and a workflow the user deleted is not brought
        back: every bundled name ever offered is remembered in ``.oaf-bundled-known``.
        """
        src = Path(source) if source else bundled_dir()
        wf_src = src / "workflows"
        if not wf_src.is_dir():
            return []
        try:
            if self.current_branch() != "main":
                return []
        except AgentflowError:
            return []
        known_path = self.path / self.KNOWN_FILE
        known = set()
        if known_path.exists():
            known = {ln.strip() for ln in known_path.read_text(encoding="utf-8").splitlines() if ln.strip()}
        bundled = sorted(p.name for p in wf_src.glob("*.yaml"))
        added = []
        for name in bundled:
            dst = self.path / "workflows" / name
            if name in known or dst.exists():
                continue
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(wf_src / name, dst)
            added.append(name)
        if not added and known >= set(bundled):
            return []
        known_path.write_text("\n".join(sorted(known | set(bundled))) + "\n", encoding="utf-8")
        paths = [self.KNOWN_FILE, *[f"workflows/{name}" for name in added]]
        self.git("add", "--", *paths)
        if self.git("diff", "--cached", "--name-only", "--", *paths):
            msg = "补上新版内置工作流: " + ", ".join(n[:-5] for n in added) if added else "记录已提供的内置工作流"
            self.git("commit", "-q", "--only", "-m", msg, "--", *paths)
        return added

    def current_branch(self) -> str:
        return self.git("rev-parse", "--abbrev-ref", "HEAD")

    def head(self, ref: str = "HEAD") -> str:
        return self.git("rev-parse", ref)

    def workflow_path(self, name: str) -> Path:
        return self.path / "workflows" / f"{name}.yaml"

    def read(self, rel: str, ref: str = "main") -> str:
        return self.git("show", f"{ref}:{rel}")

    # ------------------------------------------------------------------ changes
    def require_clean(self) -> None:
        if self.git("status", "--porcelain", "--untracked-files=all"):
            raise AgentflowError("工作区有未提交的改动，请先提交或暂存后再尝试；未改动工作区文件")

    def propose(self, workflow: str, kind: str, files: dict[str, str | bytes | None], message: str,
                base: str = "main", prefix: str = "agent") -> tuple[str, str]:
        """Commit ``files`` (relative path -> content, ``None`` deletes) on a new branch from ``base``.

        Returns (branch, commit)."""
        self.require_clean()
        branch = f"{prefix}/{workflow}-{kind}-{time.strftime('%Y%m%d-%H%M%S')}-{int(time.time() * 1000) % 1000:03d}"
        self.git("checkout", "-q", "main")
        self.git("checkout", "-q", "-b", branch, base)
        try:
            for rel, content in files.items():
                p = self.path / rel
                if content is None:
                    if p.exists():
                        p.unlink()
                    continue
                p.parent.mkdir(parents=True, exist_ok=True)
                if isinstance(content, bytes):
                    p.write_bytes(content)
                else:
                    p.write_text(content, encoding="utf-8")
            self.git("add", "-A")
            self.git("commit", "-q", "--allow-empty", "-m", message)
            commit = self.head()
        except Exception:
            self.git("reset", "-q", "--hard", check=False)
            self.git("checkout", "-q", "-f", "main", check=False)
            self.git("branch", "-D", branch, check=False)
            raise
        finally:
            self.git("checkout", "-q", "-f", "main", check=False)
        return branch, commit

    def read_bytes(self, rel: str, ref: str = "main") -> bytes | None:
        """Raw bytes of ``rel`` at ``ref`` (``None`` when the file does not exist there)."""
        res = subprocess.run(["git", "cat-file", "blob", f"{ref}:{rel}"], cwd=self.path, capture_output=True)
        return res.stdout if res.returncode == 0 else None

    def list_files(self, prefix: str, ref: str = "main") -> list[str]:
        out = self.git("ls-tree", "-r", "--name-only", ref, "--", prefix, check=False)
        return [x for x in out.splitlines() if x]

    def file_at(self, branch: str, rel: str) -> str:
        return self.git("show", f"{branch}:{rel}")

    def checkout_tmp(self, branch: str, dest: Path) -> Path:
        """Materialise a branch into ``dest`` (a plain copy, for validation runs)."""
        if dest.exists():
            shutil.rmtree(dest)
        dest.mkdir(parents=True)
        archive = subprocess.run(["git", "archive", branch], cwd=self.path, capture_output=True, check=True).stdout
        import io
        import tarfile
        with tarfile.open(fileobj=io.BytesIO(archive)) as tar:
            tar.extractall(dest, filter="data") if hasattr(tarfile, "data_filter") else tar.extractall(dest)
        return dest

    def merge(self, branch: str, message: str) -> str:
        self.git("checkout", "-q", "main")
        self.git("merge", "-q", "--no-ff", "-m", message, branch)
        return self.head()

    def revert(self, merge_commit: str, message: str) -> str:
        self.git("checkout", "-q", "main")
        try:
            self.git("revert", "--no-edit", "-m", "1", merge_commit)
        except AgentflowError as e:
            self.git("revert", "--abort", check=False)
            raise AgentflowError(f"回滚 {merge_commit[:8]} 时和后来的改动冲突，没有回滚：{e}") from e
        self.git("commit", "--amend", "-q", "-m", message)
        return self.head()

    def delete_branch(self, branch: str) -> None:
        self.git("branch", "-D", branch, check=False)

    def log(self, n: int = 20) -> list[str]:
        out = self.git("log", f"-{n}", "--format=%h %ad %s", "--date=format:%m-%d %H:%M", "main")
        return out.splitlines() if out else []
