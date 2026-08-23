from __future__ import annotations

import ast
import base64
import os
import re
import subprocess
from collections import defaultdict
from pathlib import Path, PurePosixPath

from prism.models import (
    PullRequestContext,
    RepositoryBlock,
    RepositoryBlockEdge,
    RepositoryBlockFile,
    RepositoryChangeStatus,
    RepositoryMap,
    RepositoryMapEdge,
    RepositoryMapNode,
    RepositoryNodeKind,
)


_SOURCE_EXTENSIONS = {
    ".c": "C",
    ".cc": "C++",
    ".cpp": "C++",
    ".cs": "C#",
    ".go": "Go",
    ".h": "C/C++ header",
    ".hpp": "C++ header",
    ".java": "Java",
    ".js": "JavaScript",
    ".jsx": "JavaScript",
    ".kt": "Kotlin",
    ".kts": "Kotlin",
    ".mjs": "JavaScript",
    ".php": "PHP",
    ".proto": "Protocol Buffers",
    ".py": "Python",
    ".pyi": "Python",
    ".rb": "Ruby",
    ".rs": "Rust",
    ".scala": "Scala",
    ".sh": "Shell",
    ".sql": "SQL",
    ".svelte": "Svelte",
    ".swift": "Swift",
    ".ts": "TypeScript",
    ".tsx": "TypeScript",
    ".vue": "Vue",
}
_CONFIG_NAMES = {
    "Cargo.toml",
    "Dockerfile",
    "Gemfile",
    "Makefile",
    "package.json",
    "pom.xml",
    "pyproject.toml",
    "requirements.txt",
}
_IGNORED_PARTS = {
    ".git",
    ".idea",
    ".next",
    ".venv",
    ".vscode",
    "build",
    "coverage",
    "dist",
    "node_modules",
    "target",
    "vendor",
}
_SHA_PATTERN = re.compile(r"^[0-9a-fA-F]{7,64}$")
_IMPORT_PATTERN = re.compile(
    r"(?:from\s+|import\s+(?:[^'\"\n]*?\s+from\s+)?|require\s*\(\s*)"
    r"['\"]([^'\"]+)['\"]"
)
_GO_IMPORT_PATTERN = re.compile(r'^\s*"([^\"]+)"\s*$', re.MULTILINE)
_SYMBOL_PATTERN = re.compile(
    r"^\s*(?:export\s+)?(?:async\s+)?(?:class|function|interface|type|enum|struct|trait)\s+"
    r"([A-Za-z_$][\w$]*)",
    re.MULTILINE,
)


class RepositoryMapError(RuntimeError):
    pass


class LocalRepositoryMapper:
    """Build a bounded, read-only repository graph from a pull request's Git snapshots."""

    def __init__(
        self,
        cache_root: Path,
        github_token: str | None = None,
        *,
        timeout: float = 120,
        max_files: int = 450,
        max_file_bytes: int = 300_000,
    ) -> None:
        self.repositories_root = cache_root / "repositories"
        self.github_token = github_token
        self.timeout = timeout
        self.max_files = max_files
        self.max_file_bytes = max_file_bytes

    def build(self, pull_request: PullRequestContext) -> RepositoryMap:
        if not pull_request.base_sha or not _SHA_PATTERN.fullmatch(pull_request.base_sha):
            return self._error_map(pull_request, "GitHub did not provide a valid base commit SHA.")
        if not _SHA_PATTERN.fullmatch(pull_request.head_sha):
            return self._error_map(pull_request, "GitHub did not provide a valid head commit SHA.")

        try:
            git_dir = self._fetch(pull_request)
            return self._analyze(git_dir, pull_request)
        except (OSError, RepositoryMapError, subprocess.SubprocessError) as exc:
            return self._error_map(pull_request, f"Local repository map unavailable: {exc}")

    def _fetch(self, pull_request: PullRequestContext) -> Path:
        self.repositories_root.mkdir(parents=True, exist_ok=True)
        git_dir = self.repositories_root / _safe_cache_name(pull_request.reference.slug)
        remote_url = f"https://github.com/{pull_request.reference.slug}.git"

        if not (git_dir / "HEAD").exists():
            git_dir.mkdir(parents=True, exist_ok=True)
            self._git(["init", "--bare", str(git_dir)])
            self._git(["--git-dir", str(git_dir), "remote", "add", "origin", remote_url])
        else:
            self._git(["--git-dir", str(git_dir), "remote", "set-url", "origin", remote_url])

        base_ref = f"+{pull_request.base_sha}:refs/prism/base/{pull_request.reference.number}"
        head_ref = (
            f"+refs/pull/{pull_request.reference.number}/head:"
            f"refs/prism/head/{pull_request.reference.number}"
        )
        self._git(
            [
                "--git-dir",
                str(git_dir),
                "fetch",
                "--force",
                "--depth=1",
                "origin",
                base_ref,
                head_ref,
            ]
        )

        resolved_head = self._git_text(
            [
                "--git-dir",
                str(git_dir),
                "rev-parse",
                f"refs/prism/head/{pull_request.reference.number}",
            ]
        ).strip()
        if resolved_head != pull_request.head_sha:
            raise RepositoryMapError(
                "the fetched pull-request head does not match GitHub's reported commit"
            )
        return git_dir

    def _analyze(self, git_dir: Path, pull_request: PullRequestContext) -> RepositoryMap:
        base_paths = set(self._tree_paths(git_dir, pull_request.base_sha or ""))
        head_paths = set(self._tree_paths(git_dir, pull_request.head_sha))
        changed_by_path = {item.filename: item for item in pull_request.changed_files}

        candidate_paths = {
            path for path in head_paths | base_paths if _is_mappable_path(path)
        }
        ordered_paths = _prioritize_paths(candidate_paths, changed_by_path, self.max_files)
        truncated = len(candidate_paths) > len(ordered_paths)

        files: dict[str, _FileFacts] = {}
        for path in ordered_paths:
            changed = changed_by_path.get(path)
            commit = (
                pull_request.base_sha
                if changed and changed.status == "removed"
                else pull_request.head_sha
            )
            if not commit or path not in (base_paths if commit == pull_request.base_sha else head_paths):
                continue
            source = self._show_file(git_dir, commit, path)
            if source is None:
                continue
            language = _language(path)
            imports, symbols = _source_facts(path, source, language)
            files[path] = _FileFacts(
                path=path,
                language=language,
                imports=imports,
                symbols=symbols[:12],
            )
        truncated = truncated or len(files) < len(candidate_paths)

        file_ids = {path: _node_id("file", path) for path in files}
        import_edges: set[tuple[str, str]] = set()
        for path, facts in files.items():
            for imported in facts.imports:
                target = _resolve_import(path, imported, set(files))
                if target and target != path:
                    import_edges.add((file_ids[path], file_ids[target]))

        changed_statuses = {
            "added": RepositoryChangeStatus.ADDED,
            "removed": RepositoryChangeStatus.REMOVED,
            "renamed": RepositoryChangeStatus.RENAMED,
            "modified": RepositoryChangeStatus.MODIFIED,
            "changed": RepositoryChangeStatus.MODIFIED,
        }
        changed_ids: set[str] = set()
        status_by_path: dict[str, RepositoryChangeStatus] = {}
        for path in files:
            changed = changed_by_path.get(path)
            status = changed_statuses.get(
                changed.status if changed else "", RepositoryChangeStatus.UNCHANGED
            )
            status_by_path[path] = status
            if status not in {RepositoryChangeStatus.UNCHANGED, RepositoryChangeStatus.IMPACTED}:
                changed_ids.add(file_ids[path])

        neighbor_ids = {
            node_id
            for source, target in import_edges
            if source in changed_ids or target in changed_ids
            for node_id in (source, target)
        } - changed_ids
        for path, node_id in file_ids.items():
            if node_id in neighbor_ids and status_by_path[path] == RepositoryChangeStatus.UNCHANGED:
                status_by_path[path] = RepositoryChangeStatus.IMPACTED

        focus_paths = {
            path
            for path, node_id in file_ids.items()
            if node_id in changed_ids or node_id in neighbor_ids
        }
        directory_paths = _directory_paths(files)
        focus_directories = {
            directory
            for path in focus_paths
            for directory in _parents(path)
        }

        nodes: list[RepositoryMapNode] = []
        for directory in sorted(directory_paths, key=lambda item: (item.count("/"), item)):
            nodes.append(
                RepositoryMapNode(
                    id=_node_id("directory", directory),
                    label=PurePosixPath(directory).name,
                    path=directory,
                    kind=RepositoryNodeKind.DIRECTORY,
                    status=(
                        RepositoryChangeStatus.IMPACTED
                        if directory in focus_directories
                        else RepositoryChangeStatus.UNCHANGED
                    ),
                    focused=directory in focus_directories,
                )
            )

        for path, facts in sorted(files.items()):
            nodes.append(
                RepositoryMapNode(
                    id=file_ids[path],
                    label=PurePosixPath(path).name,
                    path=path,
                    kind=_node_kind(path),
                    status=status_by_path[path],
                    language=facts.language,
                    symbols=facts.symbols,
                    url=_blob_url(pull_request, path, status_by_path[path]),
                    focused=path in focus_paths,
                )
            )

        edges = [
            RepositoryMapEdge(source=source, target=target, kind="imports", label="imports")
            for source, target in sorted(import_edges)
        ]
        for path in sorted(files):
            parent = str(PurePosixPath(path).parent)
            if parent != "." and parent in directory_paths:
                edges.append(
                    RepositoryMapEdge(
                        source=_node_id("directory", parent),
                        target=file_ids[path],
                        kind="contains",
                        label="contains",
                    )
                )
        for directory in sorted(directory_paths):
            parent = str(PurePosixPath(directory).parent)
            if parent != "." and parent in directory_paths:
                edges.append(
                    RepositoryMapEdge(
                        source=_node_id("directory", parent),
                        target=_node_id("directory", directory),
                        kind="contains",
                        label="contains",
                    )
                )

        blocks, block_edges = _build_blocks(
            pull_request,
            files,
            status_by_path,
            file_ids,
            import_edges,
        )
        return RepositoryMap(
            repository=pull_request.reference.slug,
            base_sha=pull_request.base_sha,
            head_sha=pull_request.head_sha,
            overview=self._read_overview(git_dir, pull_request.head_sha),
            nodes=nodes,
            edges=edges,
            blocks=blocks,
            block_edges=block_edges,
            total_files=len(candidate_paths),
            analyzed_files=len(files),
            truncated=truncated,
        )

    def _tree_paths(self, git_dir: Path, commit: str) -> list[str]:
        output = self._git_text(
            ["--git-dir", str(git_dir), "ls-tree", "-r", "--name-only", "-z", commit]
        )
        return [path for path in output.split("\0") if path]

    def _show_file(self, git_dir: Path, commit: str, path: str) -> str | None:
        completed = self._git(
            ["--git-dir", str(git_dir), "show", f"{commit}:{path}"],
            text=False,
            check=False,
        )
        if completed.returncode != 0 or len(completed.stdout) > self.max_file_bytes:
            return None
        return completed.stdout.decode("utf-8", errors="replace")

    def _read_overview(self, git_dir: Path, commit: str) -> str:
        for name in ("README.md", "README.rst", "README.txt", "README"):
            source = self._show_file(git_dir, commit, name)
            if source:
                return _first_readme_paragraph(source)
        return ""

    def _git_text(self, arguments: list[str]) -> str:
        completed = self._git(arguments)
        return completed.stdout

    def _git(
        self,
        arguments: list[str],
        *,
        text: bool = True,
        check: bool = True,
    ) -> subprocess.CompletedProcess:
        try:
            completed = subprocess.run(
                ["git", *arguments],
                capture_output=True,
                text=text,
                timeout=self.timeout,
                check=False,
                env=self._git_environment(),
            )
        except subprocess.TimeoutExpired as exc:
            raise RepositoryMapError(f"git timed out after {self.timeout:g} seconds") from exc
        if check and completed.returncode != 0:
            stderr = completed.stderr if text else completed.stderr.decode(errors="replace")
            detail = re.sub(r"\s+", " ", stderr).strip()[-800:] or "unknown git error"
            raise RepositoryMapError(detail)
        return completed

    def _git_environment(self) -> dict[str, str]:
        environment = os.environ.copy()
        environment["GIT_TERMINAL_PROMPT"] = "0"
        environment["GIT_CONFIG_NOSYSTEM"] = "1"
        environment["GIT_CONFIG_GLOBAL"] = os.devnull
        if self.github_token:
            encoded = base64.b64encode(
                f"x-access-token:{self.github_token}".encode()
            ).decode("ascii")
            environment["GIT_CONFIG_COUNT"] = "1"
            environment["GIT_CONFIG_KEY_0"] = "http.https://github.com/.extraheader"
            environment["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {encoded}"
        return environment

    @staticmethod
    def _error_map(pull_request: PullRequestContext, message: str) -> RepositoryMap:
        return RepositoryMap(
            repository=pull_request.reference.slug,
            base_sha=pull_request.base_sha,
            head_sha=pull_request.head_sha,
            error=message,
        )


class _FileFacts:
    def __init__(
        self, path: str, language: str | None, imports: list[str], symbols: list[str]
    ) -> None:
        self.path = path
        self.language = language
        self.imports = imports
        self.symbols = symbols


def _build_blocks(
    pull_request: PullRequestContext,
    files: dict[str, _FileFacts],
    status_by_path: dict[str, RepositoryChangeStatus],
    file_ids: dict[str, str],
    import_edges: set[tuple[str, str]],
) -> tuple[list[RepositoryBlock], list[RepositoryBlockEdge]]:
    grouped_paths: dict[str, list[str]] = defaultdict(list)
    block_path_by_file: dict[str, str] = {}
    for path in files:
        block_path = _architecture_block_path(path)
        grouped_paths[block_path].append(path)
        block_path_by_file[path] = block_path

    block_ids = {
        block_path: _node_id("block", block_path) for block_path in grouped_paths
    }
    path_by_file_id = {node_id: path for path, node_id in file_ids.items()}
    relationship_counts: dict[tuple[str, str], int] = defaultdict(int)
    for source_id, target_id in import_edges:
        source_path = path_by_file_id[source_id]
        target_path = path_by_file_id[target_id]
        source_block = block_path_by_file[source_path]
        target_block = block_path_by_file[target_path]
        if source_block == target_block:
            continue
        pair = tuple(sorted((block_ids[source_block], block_ids[target_block])))
        relationship_counts[pair] += 1

    block_edges = [
        RepositoryBlockEdge(
            source=source,
            target=target,
            relationship_count=count,
            label=f"{count} detected import{'s' if count != 1 else ''}",
        )
        for (source, target), count in sorted(relationship_counts.items())
    ]

    status_by_block = {
        block_path: _aggregate_block_status(
            [status_by_path[path] for path in grouped_paths[block_path]]
        )
        for block_path in grouped_paths
    }
    changed_block_ids = {
        block_ids[path]
        for path, status in status_by_block.items()
        if status not in {
            RepositoryChangeStatus.UNCHANGED,
            RepositoryChangeStatus.IMPACTED,
        }
    }
    neighbor_block_ids = {
        block_id
        for edge in block_edges
        if edge.source in changed_block_ids or edge.target in changed_block_ids
        for block_id in (edge.source, edge.target)
    } - changed_block_ids
    for block_path, block_id in block_ids.items():
        if (
            block_id in neighbor_block_ids
            and status_by_block[block_path] == RepositoryChangeStatus.UNCHANGED
        ):
            status_by_block[block_path] = RepositoryChangeStatus.IMPACTED

    connected_by_block: dict[str, list[tuple[str, int]]] = defaultdict(list)
    block_path_by_id = {block_id: path for path, block_id in block_ids.items()}
    for edge in block_edges:
        connected_by_block[edge.source].append(
            (edge.target, edge.relationship_count)
        )
        connected_by_block[edge.target].append(
            (edge.source, edge.relationship_count)
        )

    blocks: list[RepositoryBlock] = []
    for block_path, paths in sorted(grouped_paths.items()):
        label = _block_label(block_path)
        status = status_by_block[block_path]
        block_id = block_ids[block_path]
        block_files = [
            RepositoryBlockFile(
                path=path,
                status=status_by_path[path],
                language=files[path].language,
                symbols=files[path].symbols,
                url=_blob_url(pull_request, path, status_by_path[path]),
            )
            for path in sorted(paths)
        ]
        description = _block_description(block_path, block_files)
        note_path = f"Blocks/{_note_filename(block_path)}.md"
        connections = [
            (
                _block_label(block_path_by_id[connected_id]),
                f"Blocks/{_note_filename(block_path_by_id[connected_id])}",
                count,
            )
            for connected_id, count in sorted(
                connected_by_block[block_id], key=lambda item: block_path_by_id[item[0]]
            )
        ]
        blocks.append(
            RepositoryBlock(
                id=block_id,
                label=label,
                path=block_path,
                status=status,
                description=description,
                note_path=note_path,
                note=_block_note(
                    pull_request,
                    label,
                    block_path,
                    status,
                    description,
                    block_files,
                    connections,
                ),
                files=block_files,
                focused=block_id in changed_block_ids or block_id in neighbor_block_ids,
            )
        )
    return blocks, block_edges


def _architecture_block_path(path: str) -> str:
    parts = PurePosixPath(path).parts
    if len(parts) == 1:
        return "repository-root"
    top_level = parts[0]
    source_containers = {"app", "apps", "lib", "modules", "packages", "services", "src"}
    if top_level in source_containers and len(parts) >= 3:
        return f"{top_level}/{parts[1]}"
    return top_level


def _aggregate_block_status(
    statuses: list[RepositoryChangeStatus],
) -> RepositoryChangeStatus:
    changed = [
        status
        for status in statuses
        if status not in {
            RepositoryChangeStatus.UNCHANGED,
            RepositoryChangeStatus.IMPACTED,
        }
    ]
    if not changed:
        return (
            RepositoryChangeStatus.IMPACTED
            if RepositoryChangeStatus.IMPACTED in statuses
            else RepositoryChangeStatus.UNCHANGED
        )
    if len(set(changed)) == 1 and all(status == changed[0] for status in statuses):
        return changed[0]
    return RepositoryChangeStatus.MODIFIED


def _block_description(
    block_path: str, files: list[RepositoryBlockFile]
) -> str:
    label = _block_label(block_path)
    lower = block_path.lower()
    file_word = "file" if len(files) == 1 else "files"
    if lower == "repository-root":
        return (
            f"Repository-wide configuration and entry-point metadata across {len(files)} {file_word}."
        )
    if lower in {"test", "tests", "spec", "specs"}:
        return f"Automated verification for repository behavior across {len(files)} test {file_word}."
    if lower in {"script", "scripts", "bin", "tools"}:
        return f"Runnable development, training, or maintenance workflows across {len(files)} {file_word}."
    if lower in {"doc", "docs", "documentation"}:
        return f"Documentation and examples for the repository across {len(files)} {file_word}."

    areas = []
    for file in files:
        stem = PurePosixPath(file.path).stem
        if stem.lower() not in {"__init__", "index", "main"}:
            areas.append(_humanize(stem))
    areas = list(dict.fromkeys(areas))[:5]
    languages = list(dict.fromkeys(file.language for file in files if file.language))[:3]
    details = f" Key areas include {', '.join(areas)}." if areas else ""
    language_text = f" {', '.join(languages)}." if languages else ""
    return (
        f"The {label} architecture block groups {len(files)} implementation {file_word}."
        f"{language_text}{details}"
    )


def _block_note(
    pull_request: PullRequestContext,
    label: str,
    block_path: str,
    status: RepositoryChangeStatus,
    description: str,
    files: list[RepositoryBlockFile],
    connections: list[tuple[str, str, int]],
) -> str:
    lines = [
        "---",
        f'repository: "{pull_request.reference.slug}"',
        f'pull_request: "{pull_request.reference.number}"',
        f'block: "{block_path}"',
        f'status: "{status.value}"',
        "tags: [prism, repository-map, architecture-block]",
        "---",
        "",
        f"# {label}",
        "",
        description,
        "",
        "## Change in this PR",
        "",
    ]
    changed_files = [
        file
        for file in files
        if file.status not in {
            RepositoryChangeStatus.UNCHANGED,
            RepositoryChangeStatus.IMPACTED,
        }
    ]
    if changed_files:
        lines.append(
            f"This block is **{status.value}** because {len(changed_files)} contained "
            f"file{'s were' if len(changed_files) != 1 else ' was'} changed."
        )
    elif status == RepositoryChangeStatus.IMPACTED:
        lines.append("No file changed directly; this block is connected to a changed block.")
    else:
        lines.append("No contained file changed in this pull request.")

    lines.extend(["", "## Files", ""])
    for file in files:
        suffix = f" — **{file.status.value}**" if file.status != RepositoryChangeStatus.UNCHANGED else ""
        symbol_text = f" — symbols: {', '.join(file.symbols[:6])}" if file.symbols else ""
        file_label = f"[{file.path}]({file.url})" if file.url else f"`{file.path}`"
        lines.append(f"- {file_label}{suffix}{symbol_text}")

    lines.extend(["", "## Connected blocks", ""])
    if connections:
        for connected_label, connected_note, count in connections:
            lines.append(
                f"- [[{connected_note}|{connected_label}]] — "
                f"{count} detected import{'s' if count != 1 else ''}"
            )
    else:
        lines.append("- No cross-block imports were detected.")
    lines.extend(["", f"Generated by PRism from `{pull_request.head_sha}`.", ""])
    return "\n".join(lines)


def _block_label(block_path: str) -> str:
    if block_path == "repository-root":
        return "Repository Root"
    return " / ".join(_humanize(part) for part in block_path.split("/"))


def _note_filename(block_path: str) -> str:
    safe = re.sub(r"[^A-Za-z0-9_.-]+", "-", block_path.replace("/", "--")).strip("-")
    return safe or "repository-root"


def _humanize(value: str) -> str:
    return re.sub(r"[_-]+", " ", value).strip().title() or value


def _source_facts(path: str, source: str, language: str | None) -> tuple[list[str], list[str]]:
    if language == "Python":
        return _python_facts(source)
    imports = _IMPORT_PATTERN.findall(source)
    if language == "Go":
        imports.extend(_GO_IMPORT_PATTERN.findall(source))
    return list(dict.fromkeys(imports)), list(dict.fromkeys(_SYMBOL_PATTERN.findall(source)))


def _python_facts(source: str) -> tuple[list[str], list[str]]:
    try:
        tree = ast.parse(source)
    except (SyntaxError, ValueError):
        return [], []
    imports: list[str] = []
    symbols: list[str] = []
    for item in tree.body:
        if isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.append(item.name)
        elif isinstance(item, ast.Import):
            imports.extend(alias.name for alias in item.names)
        elif isinstance(item, ast.ImportFrom):
            module = item.module or ""
            imports.append(f"{'.' * item.level}{module}")
            if not module:
                imports.extend(f"{'.' * item.level}{alias.name}" for alias in item.names)
    return list(dict.fromkeys(imports)), list(dict.fromkeys(symbols))


def _resolve_import(source_path: str, imported: str, available: set[str]) -> str | None:
    candidates: list[str] = []
    source_parent = PurePosixPath(source_path).parent
    if imported.startswith("."):
        if source_path.endswith((".js", ".jsx", ".ts", ".tsx", ".mjs", ".vue", ".svelte")):
            base = source_parent.joinpath(imported)
            candidates.extend(_path_candidates(str(base)))
        else:
            leading = len(imported) - len(imported.lstrip("."))
            parts = list(source_parent.parts)
            if leading > 1:
                parts = parts[: max(0, len(parts) - (leading - 1))]
            suffix = imported.lstrip(".").replace(".", "/")
            base = "/".join([*parts, suffix]).strip("/")
            candidates.extend(_path_candidates(base))
    else:
        normalized = imported.replace(".", "/")
        candidates.extend(_path_candidates(normalized))
        candidates.extend(
            path
            for path in available
            if path.removesuffix(PurePosixPath(path).suffix).endswith(f"/{normalized}")
        )

    for candidate in candidates:
        normalized = str(PurePosixPath(candidate))
        if normalized in available:
            return normalized
    return None


def _path_candidates(base: str) -> list[str]:
    base = base.removeprefix("./")
    suffix = PurePosixPath(base).suffix
    if suffix in _SOURCE_EXTENSIONS:
        return [base]
    candidates = [f"{base}{extension}" for extension in _SOURCE_EXTENSIONS]
    candidates.extend(f"{base}/index{extension}" for extension in _SOURCE_EXTENSIONS)
    candidates.extend(f"{base}/__init__{extension}" for extension in (".py", ".pyi"))
    return candidates


def _prioritize_paths(
    paths: set[str], changed_by_path: dict[str, object], limit: int
) -> list[str]:
    changed_roots = {
        PurePosixPath(path).parts[0]
        for path in changed_by_path
        if PurePosixPath(path).parts
    }

    def score(path: str) -> tuple[int, int, str]:
        parts = PurePosixPath(path).parts
        changed = path in changed_by_path
        same_area = bool(parts and parts[0] in changed_roots)
        test = _is_test_path(path)
        return (0 if changed else 1 if same_area else 2 if test else 3, len(parts), path)

    return sorted(paths, key=score)[:limit]


def _directory_paths(files: dict[str, _FileFacts]) -> set[str]:
    return {
        parent
        for path in files
        for parent in _parents(path)
    }


def _parents(path: str) -> list[str]:
    parents: list[str] = []
    current = PurePosixPath(path).parent
    while str(current) != ".":
        parents.append(str(current))
        current = current.parent
    return parents


def _is_mappable_path(path: str) -> bool:
    pure = PurePosixPath(path)
    if any(part in _IGNORED_PARTS or part.startswith(".") for part in pure.parts[:-1]):
        return False
    return pure.suffix.lower() in _SOURCE_EXTENSIONS or pure.name in _CONFIG_NAMES


def _node_kind(path: str) -> RepositoryNodeKind:
    name = PurePosixPath(path).name
    if _is_test_path(path):
        return RepositoryNodeKind.TEST
    if name in _CONFIG_NAMES:
        return RepositoryNodeKind.CONFIG
    if name.lower().startswith("readme"):
        return RepositoryNodeKind.DOCUMENTATION
    return RepositoryNodeKind.FILE


def _is_test_path(path: str) -> bool:
    lower = path.lower()
    name = PurePosixPath(lower).name
    return (
        any(part in {"test", "tests", "spec", "specs", "__tests__"} for part in PurePosixPath(lower).parts)
        or name.startswith("test_")
        or ".test." in name
        or ".spec." in name
    )


def _language(path: str) -> str | None:
    return _SOURCE_EXTENSIONS.get(PurePosixPath(path).suffix.lower())


def _blob_url(
    pull_request: PullRequestContext, path: str, status: RepositoryChangeStatus
) -> str:
    commit = pull_request.base_sha if status == RepositoryChangeStatus.REMOVED else pull_request.head_sha
    return f"https://github.com/{pull_request.reference.slug}/blob/{commit}/{path}"


def _first_readme_paragraph(source: str) -> str:
    paragraphs = re.split(r"\n\s*\n", source)
    for paragraph in paragraphs:
        cleaned = re.sub(r"<[^>]+>", " ", paragraph)
        cleaned = re.sub(r"!?\[[^\]]*\]\([^)]*\)", " ", cleaned)
        cleaned = re.sub(r"[`*_>#|~-]+", " ", cleaned)
        cleaned = re.sub(r"\s+", " ", cleaned).strip()
        if len(cleaned) >= 40 and not cleaned.lower().startswith(("build status", "license")):
            return cleaned[:700]
    return ""


def _safe_cache_name(value: str) -> str:
    return re.sub(r"[^A-Za-z0-9_.-]+", "__", value)


def _node_id(kind: str, path: str) -> str:
    encoded = base64.urlsafe_b64encode(path.encode("utf-8")).decode("ascii").rstrip("=")
    return f"{kind}:{encoded}"
