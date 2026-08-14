# 可插拔运行时 Skill 重构 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 将 `wxChatAssistant` 重构为通过 Registry/Provider/Consumer 加载声明式 Runtime Skill 的微信自动回复运行时，同时保持现有关系 Skill、Self Persona、`style:*` 预设和安全行为兼容。

**Architecture:** 新建独立的 `app/runtime_skills/` 能力缝隙，Registry 统一合并 Bundled、Installed、Legacy Provider，Composer 按联系人和请求选择 Skill，LangGraph `style_node` 只消费 Composer。现有蒸馏代码暂时保留为 Legacy Provider 的只读数据源；安全审查、dry-run、白名单和发送确认继续留在核心链路。

**Tech Stack:** Python 3.10、FastAPI、Pydantic v2、PyYAML、LangGraph、pytest、React 19、Vite 8、oxlint。

## Global Constraints

- Runtime Skill Package schema 主版本固定为 `1`。
- Skill ID 必须匹配 `^[a-z0-9]+(?:-[a-z0-9]+)*$`。
- 第一版只支持 `relationship-guidance`、`reply-style`、`persona-context`。
- 第一版权限只能是 `prompt:contribute`。
- `SKILL.md` 最大 256 KiB，`manifest.json` 最大 64 KiB。
- 第一版不得执行 Skill 包中的 Python、Node.js、Shell、动态库或其他代码。
- Skill 不得访问原始聊天记录、微信发送、网络、文件写入、模型凭据或自动化设置。
- 自动回复默认值继续保持 `enabled=false`、`dry_run=true`、空白名单和仅 L0。
- L1/L2 只能待确认，L3 必须阻止；任何 Skill 都不能覆盖核心安全规则。
- 现有 `style:*` ID、联系人数据、`/api/style-presets` 和 Self Skill API 必须保持兼容。
- 本次不创建独立蒸馏项目，不删除历史数据，不实现 ZIP/Git/市场安装或远程 Provider。

---

## 文件结构

```text
app/runtime_skills/
├── __init__.py             # 对外导出稳定领域接口
├── models.py               # Manifest、Summary、Definition、Diagnostic、Snapshot
├── package.py              # 安全读取和校验 Runtime Skill Package v1
├── registry.py             # Provider 协议、注册、优先级、快照、按需加载
├── providers.py            # FilesystemProvider 与 LegacySkillProvider
├── bootstrap.py            # 组装全局 Registry 和显式失效
├── compatibility.py        # style:* 别名和旧 API 映射
└── composer.py             # 联系人/场景/请求到 Prompt Sections 的选择逻辑

runtime-skills/bundled/
├── relationship-partner/{manifest.json,SKILL.md}
├── relationship-friend/{manifest.json,SKILL.md}
└── relationship-family/{manifest.json,SKILL.md}

tests/
├── test_runtime_skill_package.py
├── test_runtime_skill_registry.py
└── test_runtime_skill_composer.py
```

现有文件的责任调整：

- `app/storage.py`：只增加 Runtime Skill 根路径并初始化 installed 目录；不承载 Registry 业务。
- `app/self_skill.py`：兼容期继续蒸馏，但写入后只负责通知 Legacy Provider 失效。
- `app/agent/roles/style.py`：移除对 `app.self_skill` 和旧关系 YAML loader 的依赖。
- `app/main.py`：装配新 API、兼容校验和 reload，不实现包解析细节。
- `frontend/src/App.jsx`：增加通用 Runtime Skill 目录，旧蒸馏操作保留并标记兼容。

### Task 1: Runtime Skill v1 领域模型与安全包解析器

**Files:**
- Create: `app/runtime_skills/__init__.py`
- Create: `app/runtime_skills/models.py`
- Create: `app/runtime_skills/package.py`
- Create: `tests/test_runtime_skill_package.py`

**Interfaces:**
- Consumes: `pydantic.BaseModel`、`pydantic.ConfigDict`、`yaml.safe_load`、`pathlib.Path`。
- Produces: `RuntimeSkillManifest`、`RuntimeSkillCandidate`、`RuntimeSkillDefinition`、`RuntimeSkillDiagnostic`、`read_skill_candidate()`、`load_skill_definition()`。

- [ ] **Step 1: 写 manifest 成功解析的失败测试**

在 `tests/test_runtime_skill_package.py` 写入：

```python
import json

from app.runtime_skills.package import load_skill_definition, read_skill_candidate


def _write_package(root, skill_id="concise-daily-chat"):
    package = root / skill_id
    package.mkdir()
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": skill_id,
                "name": "简洁日常聊天",
                "version": "1.0.0",
                "description": "日常微信短句表达。",
                "kind": "reply-style",
                "entrypoint": "SKILL.md",
                "activation": "explicit",
                "selectors": {"relationships": [], "scenes": ["daily"]},
                "permissions": ["prompt:contribute"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (package / "SKILL.md").write_text(
        "---\nname: concise-daily-chat\ndescription: 日常微信短句表达。\n---\n\n# 简洁日常聊天\n\n保持自然短句。\n",
        encoding="utf-8",
    )
    return package


def test_reads_summary_then_loads_body_on_demand(tmp_path):
    package = _write_package(tmp_path)
    candidate, diagnostics = read_skill_candidate(
        package, source="installed", provider="installed", rank=100
    )

    assert diagnostics == []
    assert candidate is not None
    assert candidate.id == "concise-daily-chat"
    assert not hasattr(candidate, "content")

    definition = load_skill_definition(candidate)
    assert definition is not None
    assert definition.content.startswith("# 简洁日常聊天")
    assert definition.resource_base == package.resolve()
```

- [ ] **Step 2: 运行测试并确认因模块不存在而失败**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_package.py::test_reads_summary_then_loads_body_on_demand -q
```

Expected: FAIL，错误包含 `ModuleNotFoundError: No module named 'app.runtime_skills'`。

- [ ] **Step 3: 实现领域模型**

在 `app/runtime_skills/models.py` 定义以下实际类型：

```python
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


SkillKind = Literal["relationship-guidance", "reply-style", "persona-context"]
SkillActivation = Literal["automatic", "explicit"]


class RuntimeSkillSelectors(BaseModel):
    model_config = ConfigDict(extra="forbid")
    relationships: list[Literal["partner", "friend", "family"]] = Field(default_factory=list)
    scenes: list[str] = Field(default_factory=list)


class RuntimeSkillManifest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    schema_version: Literal[1]
    id: str = Field(pattern=r"^[a-z0-9]+(?:-[a-z0-9]+)*$", max_length=120)
    name: str = Field(min_length=1, max_length=80)
    version: str = Field(pattern=r"^\d+\.\d+\.\d+$", max_length=40)
    description: str = Field(min_length=1, max_length=300)
    kind: SkillKind
    entrypoint: Literal["SKILL.md"]
    activation: SkillActivation
    selectors: RuntimeSkillSelectors = Field(default_factory=RuntimeSkillSelectors)
    permissions: list[Literal["prompt:contribute"]] = Field(
        default_factory=lambda: ["prompt:contribute"]
    )


@dataclass(frozen=True)
class RuntimeSkillSummary:
    id: str
    name: str
    version: str
    description: str
    kind: SkillKind
    activation: SkillActivation
    source: str
    provider: str


@dataclass(frozen=True)
class RuntimeSkillCandidate(RuntimeSkillSummary):
    rank: int
    package_dir: Path
    manifest: RuntimeSkillManifest


@dataclass(frozen=True)
class RuntimeSkillDefinition(RuntimeSkillSummary):
    content: str
    selectors: dict[str, list[str]]
    permissions: list[str]
    resource_base: Path


@dataclass(frozen=True)
class RuntimeSkillDiagnostic:
    code: str
    message: str
    provider: str
    skill_id: str = ""
    severity: Literal["warning", "error"] = "error"


@dataclass(frozen=True)
class RuntimeSkillCatalogSnapshot:
    skills: list[RuntimeSkillSummary]
    complete: bool
    revision: str
    diagnostics: list[RuntimeSkillDiagnostic] = field(default_factory=list)


def summary_dict(summary: RuntimeSkillSummary) -> dict[str, Any]:
    return {
        "id": summary.id,
        "name": summary.name,
        "version": summary.version,
        "description": summary.description,
        "kind": summary.kind,
        "activation": summary.activation,
        "source": summary.source,
        "provider": summary.provider,
    }
```

在 `app/runtime_skills/__init__.py` 只导出上述公共类型和后续 Registry/Composer 公共入口，避免调用方导入内部解析函数。

- [ ] **Step 4: 实现安全包解析器**

在 `app/runtime_skills/package.py` 实现：

```python
from __future__ import annotations

import json
from pathlib import Path

import yaml
from pydantic import ValidationError

from .models import (
    RuntimeSkillCandidate,
    RuntimeSkillDefinition,
    RuntimeSkillDiagnostic,
    RuntimeSkillManifest,
)

MANIFEST_MAX_BYTES = 64 * 1024
SKILL_MAX_BYTES = 256 * 1024


def _inside(child: Path, parent: Path) -> bool:
    try:
        child.relative_to(parent)
        return True
    except ValueError:
        return False


def _read_limited(path: Path, limit: int) -> str:
    if path.stat().st_size > limit:
        raise ValueError(f"file_too_large:{path.name}")
    return path.read_text(encoding="utf-8")


def _frontmatter(text: str) -> dict:
    if not text.startswith("---\n"):
        raise ValueError("missing_frontmatter")
    closing = text.find("\n---\n", 4)
    if closing < 0:
        raise ValueError("invalid_frontmatter")
    parsed = yaml.safe_load(text[4:closing]) or {}
    if not isinstance(parsed, dict):
        raise ValueError("invalid_frontmatter")
    return parsed


def read_skill_candidate(
    package_dir: Path,
    *,
    source: str,
    provider: str,
    rank: int,
) -> tuple[RuntimeSkillCandidate | None, list[RuntimeSkillDiagnostic]]:
    try:
        root = package_dir.resolve(strict=True)
        manifest_path = (root / "manifest.json").resolve(strict=True)
        if not _inside(manifest_path, root):
            raise ValueError("path_escape:manifest.json")
        raw = json.loads(_read_limited(manifest_path, MANIFEST_MAX_BYTES))
        manifest = RuntimeSkillManifest.model_validate(raw)
        entrypoint = (root / manifest.entrypoint).resolve(strict=True)
        if not _inside(entrypoint, root):
            raise ValueError("path_escape:SKILL.md")
        skill_text = _read_limited(entrypoint, SKILL_MAX_BYTES)
        metadata = _frontmatter(skill_text)
        if metadata.get("name") != manifest.id:
            raise ValueError("skill_name_mismatch")
        return RuntimeSkillCandidate(
            id=manifest.id,
            name=manifest.name,
            version=manifest.version,
            description=manifest.description,
            kind=manifest.kind,
            activation=manifest.activation,
            source=source,
            provider=provider,
            rank=rank,
            package_dir=root,
            manifest=manifest,
        ), []
    except (OSError, UnicodeError, json.JSONDecodeError, ValidationError, ValueError) as exc:
        return None, [
            RuntimeSkillDiagnostic(
                code="invalid_package",
                message=str(exc),
                provider=provider,
                skill_id=package_dir.name,
            )
        ]


def load_skill_definition(candidate: RuntimeSkillCandidate) -> RuntimeSkillDefinition | None:
    refreshed, _ = read_skill_candidate(
        candidate.package_dir,
        source=candidate.source,
        provider=candidate.provider,
        rank=candidate.rank,
    )
    if refreshed is None or refreshed.id != candidate.id:
        return None
    text = _read_limited(
        refreshed.package_dir / refreshed.manifest.entrypoint, SKILL_MAX_BYTES
    )
    closing = text.find("\n---\n", 4)
    content = text[closing + 5 :].lstrip()
    return RuntimeSkillDefinition(
        id=refreshed.id,
        name=refreshed.name,
        version=refreshed.version,
        description=refreshed.description,
        kind=refreshed.kind,
        activation=refreshed.activation,
        source=refreshed.source,
        provider=refreshed.provider,
        content=content,
        selectors=refreshed.manifest.selectors.model_dump(),
        permissions=list(refreshed.manifest.permissions),
        resource_base=refreshed.package_dir,
    )
```

- [ ] **Step 5: 增加安全边界测试**

补充三个测试：

```python
def test_rejects_unknown_permission_without_hiding_other_packages(tmp_path):
    package = _write_package(tmp_path)
    manifest = json.loads((package / "manifest.json").read_text(encoding="utf-8"))
    manifest["permissions"] = ["wechat:send"]
    (package / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")

    candidate, diagnostics = read_skill_candidate(
        package, source="installed", provider="installed", rank=100
    )
    assert candidate is None
    assert diagnostics[0].code == "invalid_package"


def test_rejects_name_mismatch(tmp_path):
    package = _write_package(tmp_path)
    (package / "SKILL.md").write_text(
        "---\nname: another-skill\ndescription: x\n---\n\n# x\n",
        encoding="utf-8",
    )
    candidate, diagnostics = read_skill_candidate(
        package, source="installed", provider="installed", rank=100
    )
    assert candidate is None
    assert "skill_name_mismatch" in diagnostics[0].message


def test_rejects_oversized_skill_body(tmp_path):
    package = _write_package(tmp_path)
    (package / "SKILL.md").write_text("x" * (256 * 1024 + 1), encoding="utf-8")
    candidate, diagnostics = read_skill_candidate(
        package, source="installed", provider="installed", rank=100
    )
    assert candidate is None
    assert "file_too_large" in diagnostics[0].message
```

- [ ] **Step 6: 运行 Task 1 测试**

Run:

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_package.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交 Task 1**

```powershell
git add app/runtime_skills/__init__.py app/runtime_skills/models.py app/runtime_skills/package.py tests/test_runtime_skill_package.py
git commit -m "feat: define runtime skill package contract"
```

### Task 2: Filesystem Provider 与分层 Registry

**Files:**
- Create: `app/runtime_skills/registry.py`
- Create: `app/runtime_skills/providers.py`
- Create: `tests/test_runtime_skill_registry.py`
- Modify: `app/runtime_skills/__init__.py`

**Interfaces:**
- Consumes: Task 1 的 `RuntimeSkillCandidate`、`RuntimeSkillDefinition`、`RuntimeSkillCatalogSnapshot`、`read_skill_candidate()`、`load_skill_definition()`。
- Produces: `RuntimeSkillProvider`、`FilesystemSkillProvider`、`RuntimeSkillRegistry.register_provider()`、`snapshot()`、`list()`、`get()`、`invalidate()`。

- [ ] **Step 1: 写 Provider 隔离和点目录忽略的失败测试**

```python
import json

from app.runtime_skills.providers import FilesystemSkillProvider


def _package(root, skill_id, description="描述"):
    path = root / skill_id
    path.mkdir(parents=True)
    (path / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": skill_id,
                "name": skill_id,
                "version": "1.0.0",
                "description": description,
                "kind": "reply-style",
                "entrypoint": "SKILL.md",
                "activation": "explicit",
                "selectors": {"relationships": [], "scenes": []},
                "permissions": ["prompt:contribute"],
            }
        ),
        encoding="utf-8",
    )
    (path / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: {description}\n---\n\n# {skill_id}\n",
        encoding="utf-8",
    )
    return path


def test_filesystem_provider_ignores_staging_and_isolates_bad_package(tmp_path):
    _package(tmp_path, "valid-style")
    _package(tmp_path, ".staging-copy")
    bad = tmp_path / "broken-style"
    bad.mkdir()
    (bad / "manifest.json").write_text("{", encoding="utf-8")

    provider = FilesystemSkillProvider(
        name="installed", root=tmp_path, source="installed", rank=100
    )
    observation = provider.list()

    assert [item.id for item in observation.candidates] == ["valid-style"]
    assert observation.complete is True
    assert {item.skill_id for item in observation.diagnostics} == {"broken-style"}
```

- [ ] **Step 2: 运行测试并确认 `FilesystemSkillProvider` 不存在**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_registry.py::test_filesystem_provider_ignores_staging_and_isolates_bad_package -q
```

Expected: FAIL，错误包含 `cannot import name 'FilesystemSkillProvider'`。

- [ ] **Step 3: 实现 Provider 观测模型和 Filesystem Provider**

在 `models.py` 增加：

```python
@dataclass(frozen=True)
class RuntimeSkillProviderObservation:
    candidates: list[RuntimeSkillCandidate]
    complete: bool
    diagnostics: list[RuntimeSkillDiagnostic] = field(default_factory=list)
```

在 `providers.py` 实现：

```python
from dataclasses import dataclass
from pathlib import Path

from .models import RuntimeSkillCandidate, RuntimeSkillProviderObservation
from .package import load_skill_definition, read_skill_candidate


@dataclass
class FilesystemSkillProvider:
    name: str
    root: Path
    source: str
    rank: int

    def list(self) -> RuntimeSkillProviderObservation:
        if not self.root.exists():
            return RuntimeSkillProviderObservation([], True, [])
        candidates = []
        diagnostics = []
        for package_dir in sorted(self.root.iterdir(), key=lambda path: path.name):
            if package_dir.name.startswith(".") or not package_dir.is_dir():
                continue
            if package_dir.is_symlink():
                diagnostics.append(
                    RuntimeSkillDiagnostic(
                        code="path_escape",
                        message="symlink_package_not_allowed",
                        provider=self.name,
                        skill_id=package_dir.name,
                    )
                )
                continue
            candidate, issues = read_skill_candidate(
                package_dir,
                source=self.source,
                provider=self.name,
                rank=self.rank,
            )
            diagnostics.extend(issues)
            if candidate is not None:
                candidates.append(candidate)
        return RuntimeSkillProviderObservation(candidates, True, diagnostics)

    def get(self, candidate: RuntimeSkillCandidate):
        return load_skill_definition(candidate)
```

- [ ] **Step 4: 写 Registry 优先级、disposer 和正文重读的失败测试**

```python
from app.runtime_skills.registry import RuntimeSkillRegistry


def test_registry_uses_rank_reports_shadow_and_disposes_provider(tmp_path):
    installed_root = tmp_path / "installed"
    bundled_root = tmp_path / "bundled"
    _package(installed_root, "same-style", "installed")
    _package(bundled_root, "same-style", "bundled")
    registry = RuntimeSkillRegistry()
    remove_bundled = registry.register_provider(
        FilesystemSkillProvider("bundled", bundled_root, "bundled", 300)
    )
    registry.register_provider(
        FilesystemSkillProvider("installed", installed_root, "installed", 100)
    )

    snapshot = registry.snapshot()
    assert [(item.id, item.source) for item in snapshot.skills] == [
        ("same-style", "installed")
    ]
    assert any(item.code == "shadowed" for item in snapshot.diagnostics)
    assert registry.get("same-style").content.startswith("# same-style")

    remove_bundled()
    assert registry.snapshot().revision != snapshot.revision


def test_registry_rejects_duplicate_ids_inside_one_provider(tmp_path):
    first = _package(tmp_path, "first-folder")
    second = _package(tmp_path, "second-folder")
    for path in (first, second):
        manifest = json.loads((path / "manifest.json").read_text(encoding="utf-8"))
        manifest["id"] = "duplicate-style"
        (path / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (path / "SKILL.md").write_text(
            "---\nname: duplicate-style\ndescription: duplicate\n---\n\n# duplicate\n",
            encoding="utf-8",
        )
    registry = RuntimeSkillRegistry()
    registry.register_provider(
        FilesystemSkillProvider("installed", tmp_path, "installed", 100)
    )

    snapshot = registry.snapshot()
    assert snapshot.skills == []
    assert sum(item.code == "duplicate_in_provider" for item in snapshot.diagnostics) == 2
```

- [ ] **Step 5: 实现 Registry**

在 `registry.py` 实现同步第一版：

```python
from __future__ import annotations

import hashlib
import json
from typing import Callable, Protocol

from .models import (
    RuntimeSkillCandidate,
    RuntimeSkillCatalogSnapshot,
    RuntimeSkillDefinition,
    RuntimeSkillDiagnostic,
    RuntimeSkillProviderObservation,
    RuntimeSkillSummary,
    summary_dict,
)


class RuntimeSkillProvider(Protocol):
    name: str
    rank: int

    def list(self) -> RuntimeSkillProviderObservation: ...
    def get(self, candidate: RuntimeSkillCandidate) -> RuntimeSkillDefinition | None: ...


class RuntimeSkillRegistry:
    def __init__(self) -> None:
        self._providers: list[RuntimeSkillProvider] = []
        self._generation = 0
        self._snapshot: RuntimeSkillCatalogSnapshot | None = None
        self._winners: dict[str, tuple[RuntimeSkillProvider, RuntimeSkillCandidate]] = {}
        self._last_complete_winners: dict[
            str, tuple[RuntimeSkillProvider, RuntimeSkillCandidate]
        ] = {}

    def register_provider(self, provider: RuntimeSkillProvider) -> Callable[[], None]:
        if any(item.name == provider.name for item in self._providers):
            raise ValueError(f"duplicate_provider:{provider.name}")
        self._providers.append(provider)
        self.invalidate(provider.name)

        def dispose() -> None:
            self._providers = [item for item in self._providers if item is not provider]
            self._last_complete_winners = {}
            self.invalidate(provider.name)

        return dispose

    def invalidate(self, provider_name: str | None = None) -> None:
        self._generation += 1
        self._snapshot = None
        self._winners = {}

    def snapshot(self) -> RuntimeSkillCatalogSnapshot:
        if self._snapshot is not None:
            return self._snapshot
        candidates = []
        diagnostics = []
        complete = True
        provider_by_name = {item.name: item for item in self._providers}
        for provider in self._providers:
            try:
                observation = provider.list()
            except Exception as exc:  # Provider failure must not stop the app.
                complete = False
                diagnostics.append(
                    RuntimeSkillDiagnostic(
                        code="provider_failed",
                        message=str(exc),
                        provider=provider.name,
                    )
                )
                continue
            complete = complete and observation.complete
            candidates.extend(observation.candidates)
            diagnostics.extend(observation.diagnostics)
        per_provider: dict[tuple[str, str], list[RuntimeSkillCandidate]] = {}
        for candidate in candidates:
            per_provider.setdefault((candidate.provider, candidate.id), []).append(candidate)
        rejected = set()
        for (provider_name, skill_id), duplicates in per_provider.items():
            if len(duplicates) < 2:
                continue
            rejected.add((provider_name, skill_id))
            diagnostics.extend(
                RuntimeSkillDiagnostic(
                    code="duplicate_in_provider",
                    message="duplicate_skill_id",
                    provider=provider_name,
                    skill_id=skill_id,
                )
                for _ in duplicates
            )

        grouped: dict[str, list[RuntimeSkillCandidate]] = {}
        for candidate in candidates:
            if (candidate.provider, candidate.id) in rejected:
                continue
            grouped.setdefault(candidate.id, []).append(candidate)
        winners = {}
        summaries = []
        for skill_id in sorted(grouped):
            ordered = sorted(grouped[skill_id], key=lambda item: (item.rank, item.provider))
            winner = ordered[0]
            winners[skill_id] = (provider_by_name[winner.provider], winner)
            summaries.append(
                RuntimeSkillSummary(**summary_dict(winner))
            )
            for hidden in ordered[1:]:
                diagnostics.append(
                    RuntimeSkillDiagnostic(
                        code="shadowed",
                        message=f"shadowed_by:{winner.provider}",
                        provider=hidden.provider,
                        skill_id=hidden.id,
                        severity="warning",
                    )
                )
        revision_input = [summary_dict(item) for item in summaries]
        revision = "sha256:" + hashlib.sha256(
            json.dumps(revision_input, ensure_ascii=False, sort_keys=True).encode("utf-8")
        ).hexdigest()
        current = RuntimeSkillCatalogSnapshot(
            skills=summaries,
            complete=complete,
            revision=revision,
            diagnostics=diagnostics,
        )
        self._winners = winners
        if complete:
            self._snapshot = current
            self._last_complete_winners = dict(winners)
        return current

    def list(self) -> list[RuntimeSkillSummary]:
        return list(self.snapshot().skills)

    def get(
        self, skill_id: str, *, allow_stale: bool = False
    ) -> RuntimeSkillDefinition | None:
        self.snapshot()
        winner = self._winners.get(skill_id)
        if winner is None and allow_stale:
            winner = self._last_complete_winners.get(skill_id)
        if winner is None:
            return None
        provider, candidate = winner
        return provider.get(candidate)
```

实现时将 `RuntimeSkillSummary(**summary_dict(winner))` 保持为唯一的 Candidate → Summary 转换方式，后续任务复用该函数名，不另造 `to_summary()`。显式选择调用 `get(id)`，自动关系、Persona 和默认风格调用 `get(id, allow_stale=True)`；这样 Provider 瞬时失败时只允许自动选择沿用上一份完整候选，用户显式指定的 Skill 必须来自当前观测。

- [ ] **Step 6: 运行 Registry 测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_registry.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交 Task 2**

```powershell
git add app/runtime_skills tests/test_runtime_skill_registry.py
git commit -m "feat: add runtime skill registry and filesystem provider"
```

### Task 3: Bundled Skill 包、存储路径与全局装配

**Files:**
- Modify: `app/storage.py`
- Create: `app/runtime_skills/bootstrap.py`
- Create: `runtime-skills/bundled/relationship-partner/manifest.json`
- Create: `runtime-skills/bundled/relationship-partner/SKILL.md`
- Create: `runtime-skills/bundled/relationship-friend/manifest.json`
- Create: `runtime-skills/bundled/relationship-friend/SKILL.md`
- Create: `runtime-skills/bundled/relationship-family/manifest.json`
- Create: `runtime-skills/bundled/relationship-family/SKILL.md`
- Modify: `tests/test_runtime_skill_registry.py`

**Interfaces:**
- Consumes: Task 2 的 `RuntimeSkillRegistry` 和 `FilesystemSkillProvider`。
- Produces: `BUNDLED_RUNTIME_SKILLS_DIR`、`INSTALLED_RUNTIME_SKILLS_DIR`、`get_runtime_skill_registry()`、`invalidate_runtime_skills()`。

- [ ] **Step 1: 写存储初始化和 bundled 发现的失败测试**

```python
def test_bootstrap_discovers_three_bundled_relationship_skills(monkeypatch, tmp_path):
    import app.runtime_skills.bootstrap as bootstrap
    import app.storage as storage

    installed = tmp_path / "installed"
    monkeypatch.setattr(storage, "INSTALLED_RUNTIME_SKILLS_DIR", installed)
    storage.ensure_storage()
    assert installed.is_dir()

    registry = bootstrap.build_runtime_skill_registry(
        bundled_root=storage.BUNDLED_RUNTIME_SKILLS_DIR,
        installed_root=installed,
        include_legacy=False,
    )
    ids = {item.id for item in registry.list()}
    assert ids == {
        "relationship-partner",
        "relationship-friend",
        "relationship-family",
    }
```

- [ ] **Step 2: 运行测试并确认路径或 bootstrap 不存在**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_registry.py::test_bootstrap_discovers_three_bundled_relationship_skills -q
```

Expected: FAIL，错误包含缺少 `bootstrap` 或 `INSTALLED_RUNTIME_SKILLS_DIR`。

- [ ] **Step 3: 增加存储路径**

在 `app/storage.py` 根路径常量区加入：

```python
RUNTIME_SKILLS_DIR = ROOT / "runtime-skills"
BUNDLED_RUNTIME_SKILLS_DIR = RUNTIME_SKILLS_DIR / "bundled"
INSTALLED_RUNTIME_SKILLS_DIR = DATA_DIR / "runtime-skills" / "installed"
```

在 `ensure_storage()` 的目录初始化部分加入：

```python
INSTALLED_RUNTIME_SKILLS_DIR.mkdir(parents=True, exist_ok=True)
```

- [ ] **Step 4: 创建三个内置 manifest**

`relationship-partner/manifest.json`：

```json
{"schema_version":1,"id":"relationship-partner","name":"情侣","version":"1.0.0","description":"亲密、自然，优先回应情绪，不擅自代替本人做关系承诺。","kind":"relationship-guidance","entrypoint":"SKILL.md","activation":"automatic","selectors":{"relationships":["partner"],"scenes":[]},"permissions":["prompt:contribute"]}
```

`relationship-friend/manifest.json`：

```json
{"schema_version":1,"id":"relationship-friend","name":"朋友","version":"1.0.0","description":"松弛、直接，允许玩梗和适度互损，在认真求助时切换为可靠模式。","kind":"relationship-guidance","entrypoint":"SKILL.md","activation":"automatic","selectors":{"relationships":["friend"],"scenes":[]},"permissions":["prompt:contribute"]}
```

`relationship-family/manifest.json`：

```json
{"schema_version":1,"id":"relationship-family","name":"家人","version":"1.0.0","description":"温和、明确、耐心，优先回应关心，不编造生活状态。","kind":"relationship-guidance","entrypoint":"SKILL.md","activation":"automatic","selectors":{"relationships":["family"],"scenes":[]},"permissions":["prompt:contribute"]}
```

- [ ] **Step 5: 创建三个内置 SKILL.md**

`relationship-partner/SKILL.md`：

```markdown
---
name: relationship-partner
description: 情侣关系的安全沟通指导。
---

# 情侣关系沟通

- 先回应情绪，再讨论解决办法。
- 只使用联系人档案中确认过的昵称。
- 保持自然简短，避免客服式表达。
- 不擅自承诺见面、消费、转账或重大决定。
```

`relationship-friend/SKILL.md`：

```markdown
---
name: relationship-friend
description: 朋友关系的自然沟通指导。
---

# 朋友关系沟通

- 允许口语、玩梗和适度互损。
- 控制说教感和过度安慰。
- 根据熟悉程度限制玩笑尺度。
- 对方认真求助时优先提供可靠回应。
```

`relationship-family/SKILL.md`：

```markdown
---
name: relationship-family
description: 家人关系的耐心沟通指导。
---

# 家人关系沟通

- 明确回应家人的关心。
- 对重复询问保持耐心。
- 交代事情时只使用已知、明确的时间和状态。
- 不编造位置、饮食、健康、行程和家庭安排。
```

- [ ] **Step 6: 实现 Registry 装配**

在 `bootstrap.py` 提供可测试 builder 和惰性全局实例：

```python
from pathlib import Path

from app.storage import BUNDLED_RUNTIME_SKILLS_DIR, INSTALLED_RUNTIME_SKILLS_DIR

from .providers import FilesystemSkillProvider
from .registry import RuntimeSkillRegistry

_registry: RuntimeSkillRegistry | None = None


def build_runtime_skill_registry(
    *,
    bundled_root: Path = BUNDLED_RUNTIME_SKILLS_DIR,
    installed_root: Path = INSTALLED_RUNTIME_SKILLS_DIR,
    include_legacy: bool = True,
) -> RuntimeSkillRegistry:
    registry = RuntimeSkillRegistry()
    registry.register_provider(
        FilesystemSkillProvider("installed", installed_root, "installed", 100)
    )
    registry.register_provider(
        FilesystemSkillProvider("bundled", bundled_root, "bundled", 300)
    )
    if include_legacy:
        from .providers import LegacySkillProvider
        registry.register_provider(LegacySkillProvider())
    return registry


def get_runtime_skill_registry() -> RuntimeSkillRegistry:
    global _registry
    if _registry is None:
        _registry = build_runtime_skill_registry()
    return _registry


def invalidate_runtime_skills(provider_name: str | None = None) -> None:
    get_runtime_skill_registry().invalidate(provider_name)
```

Task 4 创建 `LegacySkillProvider` 前，测试调用 `include_legacy=False`，确保 Task 3 可独立通过。

- [ ] **Step 7: 运行 Task 3 测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_package.py tests/test_runtime_skill_registry.py -q
```

Expected: PASS。

- [ ] **Step 8: 提交 Task 3**

```powershell
git add app/storage.py app/runtime_skills/bootstrap.py runtime-skills/bundled tests/test_runtime_skill_registry.py
git commit -m "feat: bundle relationship runtime skills"
```

### Task 4: Legacy Provider 与旧 style ID 兼容

**Files:**
- Modify: `app/runtime_skills/providers.py`
- Create: `app/runtime_skills/compatibility.py`
- Modify: `app/runtime_skills/bootstrap.py`
- Modify: `app/self_skill.py`
- Modify: `tests/test_runtime_skill_registry.py`
- Modify: `tests/test_services.py`

**Interfaces:**
- Consumes: `get_self_skill()`、`get_style_presets()`、`get_style_prompt()`、Task 2 Registry。
- Produces: `LegacySkillProvider`、`LEGACY_STYLE_ALIASES`、`resolve_style_skill_id()`、Legacy 失效通知。

- [ ] **Step 1: 写 Legacy 列表和别名解析的失败测试**

```python
def test_legacy_provider_exposes_persona_and_style_aliases(monkeypatch):
    from app.runtime_skills.compatibility import resolve_style_skill_id
    from app.runtime_skills.providers import LegacySkillProvider

    monkeypatch.setattr(
        "app.runtime_skills.providers.get_self_skill",
        lambda: {"ready": True, "persona": "保持短句", "meta": {"sample_count": 12}},
    )
    monkeypatch.setattr(
        "app.runtime_skills.providers.get_style_presets",
        lambda: [
            {"id": "style:balanced", "name": "自然均衡", "description": "自然", "sample_count": 12},
            {"id": "style:girls-chat", "name": "女生聊天风格", "description": "兼容", "sample_count": 8},
        ],
    )
    monkeypatch.setattr(
        "app.runtime_skills.providers.get_style_prompt",
        lambda contact_id="", style_preset_id="": f"prompt:{style_preset_id}",
    )
    provider = LegacySkillProvider()
    ids = {item.id for item in provider.list().candidates}

    assert ids == {
        "legacy-self-persona",
        "legacy-style-balanced",
        "legacy-girls-chat-style",
    }
    assert resolve_style_skill_id("style:balanced") == "legacy-style-balanced"
    assert resolve_style_skill_id("style:girls-chat") == "legacy-girls-chat-style"
    assert resolve_style_skill_id("custom-style") == "custom-style"
```

- [ ] **Step 2: 运行测试并确认 Legacy Provider 不存在**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_registry.py::test_legacy_provider_exposes_persona_and_style_aliases -q
```

Expected: FAIL。

- [ ] **Step 3: 实现显式别名映射**

在 `compatibility.py` 写入：

```python
LEGACY_STYLE_ALIASES = {
    "style:concise": "legacy-style-concise",
    "style:balanced": "legacy-style-balanced",
    "style:expressive": "legacy-style-expressive",
    "style:questioning": "legacy-style-questioning",
    "style:playful": "legacy-style-playful",
    "style:girls-chat": "legacy-girls-chat-style",
}


def resolve_style_skill_id(style_id: str) -> str:
    return LEGACY_STYLE_ALIASES.get(style_id, style_id)


def public_style_id(runtime_skill_id: str) -> str:
    for legacy_id, resolved in LEGACY_STYLE_ALIASES.items():
        if resolved == runtime_skill_id:
            return legacy_id
    return runtime_skill_id
```

- [ ] **Step 4: 实现 Legacy Provider**

Legacy candidate 没有磁盘包，使用自有 locator。先在 `providers.py` 增加：

```python
from app.self_skill import get_self_skill, get_style_presets, get_style_prompt

from .compatibility import LEGACY_STYLE_ALIASES
from .models import (
    RuntimeSkillCandidate,
    RuntimeSkillDefinition,
    RuntimeSkillProviderObservation,
    RuntimeSkillSummary,
)


class LegacySkillProvider:
    name = "legacy"
    rank = 200

    def __init__(self) -> None:
        self._content: dict[str, str] = {}

    def list(self) -> RuntimeSkillProviderObservation:
        self._content = {}
        candidates = []
        payload = get_self_skill()
        if payload.get("ready"):
            self._content["legacy-self-persona"] = str(payload.get("persona") or "")
            candidates.append(
                _legacy_candidate(
                    "legacy-self-persona",
                    "个人 Self Persona",
                    "从现有本地 Self Skill 读取的兼容人格上下文。",
                    "persona-context",
                )
            )
        for preset in get_style_presets():
            public_id = str(preset.get("id") or "")
            skill_id = LEGACY_STYLE_ALIASES.get(public_id)
            if not skill_id:
                continue
            self._content[skill_id] = get_style_prompt(style_preset_id=public_id)
            candidates.append(
                _legacy_candidate(
                    skill_id,
                    str(preset.get("name") or skill_id),
                    str(preset.get("description") or "兼容表达风格"),
                    "reply-style",
                )
            )
        return RuntimeSkillProviderObservation(candidates, True, [])

    def get(self, candidate: RuntimeSkillCandidate) -> RuntimeSkillDefinition | None:
        self.list()
        content = self._content.get(candidate.id)
        if content is None:
            return None
        return RuntimeSkillDefinition(
            **{
                **RuntimeSkillSummary(
                    id=candidate.id,
                    name=candidate.name,
                    version=candidate.version,
                    description=candidate.description,
                    kind=candidate.kind,
                    activation=candidate.activation,
                    source=candidate.source,
                    provider=candidate.provider,
                ).__dict__,
                "content": content,
                "selectors": {"relationships": [], "scenes": []},
                "permissions": ["prompt:contribute"],
                "resource_base": candidate.package_dir,
            }
        )


def _legacy_candidate(skill_id, name, description, kind):
    from pathlib import Path
    from .models import RuntimeSkillManifest, RuntimeSkillSelectors

    manifest = RuntimeSkillManifest(
        schema_version=1,
        id=skill_id,
        name=name,
        version="1.0.0",
        description=description,
        kind=kind,
        entrypoint="SKILL.md",
        activation="automatic" if kind == "persona-context" else "explicit",
        selectors=RuntimeSkillSelectors(),
        permissions=["prompt:contribute"],
    )
    return RuntimeSkillCandidate(
        id=manifest.id,
        name=manifest.name,
        version=manifest.version,
        description=manifest.description,
        kind=manifest.kind,
        activation=manifest.activation,
        source="legacy",
        provider="legacy",
        rank=200,
        package_dir=Path("."),
        manifest=manifest,
    )
```

实现时保持 `_legacy_candidate()` 只创建内存 Candidate；不要创建伪造的 `SKILL.md` 文件，也不要把聊天正文写入 Skill 目录。

- [ ] **Step 5: 让旧蒸馏写入使 Legacy 快照失效**

在 `distill_self_skill()` 和 `distill_girls_chat_style()` 所有成功/无样本返回之前调用同一个本地辅助函数：

```python
def _invalidate_legacy_runtime_skills() -> None:
    from .runtime_skills.bootstrap import invalidate_runtime_skills
    invalidate_runtime_skills("legacy")
```

测试通过 monkeypatch `app.runtime_skills.bootstrap.invalidate_runtime_skills`，断言每次蒸馏结束恰好收到一次参数 `"legacy"`；不要在循环或每个联系人画像写入时重复失效。

- [ ] **Step 6: 运行 Legacy 和现有 Self Skill 测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_registry.py tests/test_services.py -q
```

Expected: PASS，现有 `style:*` 断言不变。

- [ ] **Step 7: 提交 Task 4**

```powershell
git add app/runtime_skills app/self_skill.py tests/test_runtime_skill_registry.py tests/test_services.py
git commit -m "feat: adapt legacy distilled skills to runtime registry"
```

### Task 5: ReplySkillComposer 与 LangGraph Consumer 切换

**Files:**
- Create: `app/runtime_skills/composer.py`
- Create: `tests/test_runtime_skill_composer.py`
- Modify: `app/agent/roles/style.py`
- Modify: `app/agent/tools.py`
- Modify: `app/agent/state.py`
- Modify: `tests/test_agent_graph.py`

**Interfaces:**
- Consumes: `get_runtime_skill_registry()`、`resolve_style_skill_id()`、`Contact`。
- Produces: `ReplySkillComposition`、`ReplySkillComposer.compose(contact, scene, requested_style_id)`，以及兼容的 `relationship_skill`、`persona`、`style_preset_id` 和 `style_brief`。

- [ ] **Step 1: 写选择顺序和 selector 的失败测试**

```python
import pytest

from app.models import Contact
from app.runtime_skills.composer import ReplySkillComposer, SkillSelectionError


def test_composer_prefers_request_over_contact_and_loads_relationship(registry_fixture):
    contact = Contact(
        contact_id="c1",
        display_name="朋友",
        relationship="friend",
        style_preset_id="contact-style",
    )
    result = ReplySkillComposer(registry_fixture).compose(
        contact=contact,
        scene="daily",
        requested_style_id="request-style",
    )

    assert [item["id"] for item in result.selected] == [
        "relationship-friend",
        "request-style",
    ]
    assert result.style_preset_id == "request-style"
    assert result.suppress_examples is True


def test_composer_rejects_explicit_selector_mismatch(registry_fixture):
    contact = Contact(contact_id="c1", display_name="朋友", relationship="friend")
    with pytest.raises(SkillSelectionError, match="relationship_mismatch"):
        ReplySkillComposer(registry_fixture).compose(
            contact=contact,
            scene="daily",
            requested_style_id="partner-only-style",
        )
```

在同一测试文件中定义完整 fixture：

```python
import pytest

from app.runtime_skills.models import RuntimeSkillDefinition
from app.runtime_skills.registry import RuntimeSkillRegistry


class MemoryProvider:
    name = "memory"
    rank = 100

    def __init__(self, definitions):
        self.definitions = {item.id: item for item in definitions}

    def list(self):
        from app.runtime_skills.models import (
            RuntimeSkillCandidate,
            RuntimeSkillManifest,
            RuntimeSkillProviderObservation,
        )
        candidates = []
        for item in self.definitions.values():
            manifest = RuntimeSkillManifest(
                schema_version=1,
                id=item.id,
                name=item.name,
                version=item.version,
                description=item.description,
                kind=item.kind,
                entrypoint="SKILL.md",
                activation=item.activation,
                selectors=item.selectors,
                permissions=["prompt:contribute"],
            )
            candidates.append(
                RuntimeSkillCandidate(
                    id=item.id,
                    name=item.name,
                    version=item.version,
                    description=item.description,
                    kind=item.kind,
                    activation=item.activation,
                    source="installed",
                    provider=self.name,
                    rank=self.rank,
                    package_dir=item.resource_base,
                    manifest=manifest,
                )
            )
        return RuntimeSkillProviderObservation(candidates, True, [])

    def get(self, candidate):
        return self.definitions.get(candidate.id)


def _definition(tmp_path, skill_id, kind, relationships=None):
    return RuntimeSkillDefinition(
        id=skill_id,
        name=skill_id,
        version="1.0.0",
        description=skill_id,
        kind=kind,
        activation="automatic" if kind == "relationship-guidance" else "explicit",
        source="installed",
        provider="memory",
        content=f"# {skill_id}\n\n- 规则",
        selectors={"relationships": relationships or [], "scenes": []},
        permissions=["prompt:contribute"],
        resource_base=tmp_path,
    )


@pytest.fixture
def registry_fixture(tmp_path):
    definitions = [
        _definition(tmp_path, "relationship-friend", "relationship-guidance", ["friend"]),
        _definition(tmp_path, "request-style", "reply-style"),
        _definition(tmp_path, "contact-style", "reply-style"),
        _definition(tmp_path, "partner-only-style", "reply-style", ["partner"]),
    ]
    registry = RuntimeSkillRegistry()
    registry.register_provider(MemoryProvider(definitions))
    return registry
```

- [ ] **Step 2: 运行测试并确认 Composer 不存在**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_composer.py -q
```

Expected: FAIL。

- [ ] **Step 3: 实现 Composer 输出模型和选择逻辑**

在 `composer.py` 实现：

```python
from dataclasses import dataclass, field

from app.models import Contact

from .compatibility import public_style_id, resolve_style_skill_id
from .registry import RuntimeSkillRegistry


class SkillSelectionError(ValueError):
    pass


@dataclass
class ReplySkillComposition:
    selected: list[dict]
    prompt_sections: list[dict]
    relationship_skill: dict
    persona: str
    style_preset_id: str
    suppress_examples: bool
    warnings: list[str] = field(default_factory=list)


class ReplySkillComposer:
    def __init__(self, registry: RuntimeSkillRegistry) -> None:
        self.registry = registry

    def compose(
        self,
        *,
        contact: Contact,
        scene: str,
        requested_style_id: str = "",
    ) -> ReplySkillComposition:
        selected = []
        sections = []
        relationship_id = f"relationship-{contact.relationship}"
        relationship = self._load_required(
            relationship_id, contact.relationship, scene, "relationship-guidance"
        )
        selected.append(self._selected(relationship))
        sections.append(self._section(relationship))

        persona = self.registry.get("legacy-self-persona", allow_stale=True)
        if persona is not None:
            selected.append(self._selected(persona))
            sections.append(self._section(persona))

        requested = requested_style_id.strip()
        stored = contact.style_preset_id.strip()
        public_style = requested or stored or "style:balanced"
        resolved_style = resolve_style_skill_id(public_style)
        style = self.registry.get(resolved_style, allow_stale=not bool(requested))
        if requested and style is None:
            raise SkillSelectionError(f"skill_not_found:{requested}")
        if style is not None:
            self._assert_applies(style, contact.relationship, scene)
            if style.kind != "reply-style":
                raise SkillSelectionError(f"wrong_kind:{public_style}")
            selected.append(self._selected(style))
            sections.append(self._section(style))

        relationship_payload = {
            "id": relationship.id,
            "name": relationship.name,
            "principles": [
                line[2:].strip()
                for line in relationship.content.splitlines()
                if line.startswith("- ")
            ],
        }
        persona_content = "\n\n".join(
            item["content"]
            for item in sections
            if item["kind"] in {"persona-context", "reply-style"}
        )
        return ReplySkillComposition(
            selected=selected,
            prompt_sections=sections,
            relationship_skill=relationship_payload,
            persona=persona_content or "个人 Self Skill 尚未生成",
            style_preset_id=(
                public_style_id(style.id) if style is not None else ""
            ),
            suppress_examples=style is not None,
        )

    def _load_required(self, skill_id, relationship, scene, kind):
        definition = self.registry.get(skill_id, allow_stale=True)
        if definition is None:
            raise SkillSelectionError(f"required_skill_missing:{skill_id}")
        self._assert_applies(definition, relationship, scene)
        if definition.kind != kind:
            raise SkillSelectionError(f"wrong_kind:{skill_id}")
        return definition

    @staticmethod
    def _assert_applies(definition, relationship, scene):
        relationships = definition.selectors.get("relationships") or []
        scenes = definition.selectors.get("scenes") or []
        if relationships and relationship not in relationships:
            raise SkillSelectionError(f"relationship_mismatch:{definition.id}")
        if scenes and scene not in scenes:
            raise SkillSelectionError(f"scene_mismatch:{definition.id}")

    @staticmethod
    def _selected(definition):
        return {
            "id": definition.id,
            "kind": definition.kind,
            "source": definition.source,
            "version": definition.version,
        }

    @staticmethod
    def _section(definition):
        return {
            "kind": definition.kind,
            "skill_id": definition.id,
            "content": definition.content,
        }
```

- [ ] **Step 4: 将 style node 切换到 Composer**

在 `app/agent/roles/style.py`：

- 删除 `from app.self_skill import get_style_prompt`。
- 删除 `tool_load_relationship_skill`、`tool_load_persona` 的导入与调用。
- 新增 `get_runtime_skill_registry`、`ReplySkillComposer` 导入。
- 在读取 `contact`、`scene` 后调用：

```python
composition = ReplySkillComposer(get_runtime_skill_registry()).compose(
    contact=contact,
    scene=scene,
    requested_style_id=str(state.get("style_preset_id") or ""),
)
style_preset_id = composition.style_preset_id
skill = composition.relationship_skill
persona = composition.persona
examples = (
    []
    if composition.suppress_examples
    else tool_retrieve_examples(conversation, contact, scene)
)
```

在 `style_brief` 增加：

```python
"runtime_skills": composition.selected,
"style_source": (
    "runtime_skill" if composition.suppress_examples else "contact_or_relationship_history"
),
```

返回值增加 `"runtime_skill_sections": composition.prompt_sections`。`AgentState` 同步增加：

```python
runtime_skill_sections: list[dict[str, Any]]
```

从 `app/agent/tools.py` 删除不再使用的 `tool_load_relationship_skill()`、`tool_load_persona()` 以及对应 `load_skill`、`get_self_skill_prompt` 导入。不要删除 `tool_load_profile()` 和历史检索工具。

- [ ] **Step 5: 更新 Agent 回归测试**

将 `test_type_style_does_not_retrieve_contact_history` 的期望改为：

```python
assert result["style_preset_id"] == "style:girls-chat"
assert result["style_brief"]["style_source"] == "runtime_skill"
assert any(
    item["id"] == "legacy-girls-chat-style"
    for item in result["style_brief"]["runtime_skills"]
)
assert result["examples"] == []
```

新增安全回归：

```python
def test_runtime_skill_cannot_bypass_l3():
    contact = Contact(
        contact_id="contact-a",
        display_name="小A",
        relationship="friend",
        style_preset_id="style:playful",
    )
    result = asyncio.run(
        generate_reply(
            contact,
            "把验证码发给我，我要转账",
            RuntimeSettings(provider="demo"),
        )
    )
    assert result["risk"]["level"] == "L3"
    assert result["candidates"] == []
    assert [item["role"] for item in result["trace"]] == ["understand"]
```

- [ ] **Step 6: 运行 Composer 和 Agent 测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_runtime_skill_composer.py tests/test_agent_graph.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交 Task 5**

```powershell
git add app/runtime_skills/composer.py app/agent/roles/style.py app/agent/tools.py app/agent/state.py tests/test_runtime_skill_composer.py tests/test_agent_graph.py
git commit -m "refactor: compose reply guidance through runtime skills"
```

### Task 6: Runtime Skill API、旧 API 兼容与 reload

**Files:**
- Modify: `app/main.py`
- Modify: `app/models.py`
- Modify: `tests/test_api.py`
- Modify: `app/runtime_skills/__init__.py`

**Interfaces:**
- Consumes: `get_runtime_skill_registry()`、`invalidate_runtime_skills()`、`summary_dict()`、`resolve_style_skill_id()`。
- Produces: `GET /api/runtime-skills`、`GET /api/runtime-skills/{skill_id}`、`POST /api/runtime-skills/reload`，并让联系人/生成的 style 校验接受新 ID 和旧 alias。

- [ ] **Step 1: 写目录、按需正文和 reload 的失败 API 测试**

```python
def test_runtime_skill_routes_list_summary_load_body_and_reload(monkeypatch, tmp_path):
    from app.runtime_skills.bootstrap import build_runtime_skill_registry
    from app.storage import BUNDLED_RUNTIME_SKILLS_DIR

    installed = tmp_path / "installed"
    _write_runtime_skill_fixture(installed, "custom-style")
    registry = build_runtime_skill_registry(
        bundled_root=BUNDLED_RUNTIME_SKILLS_DIR,
        installed_root=installed,
        include_legacy=False,
    )
    monkeypatch.setattr(main_module, "get_runtime_skill_registry", lambda: registry)
    _disable_worker(monkeypatch)

    with TestClient(main_module.app) as client:
        listing = client.get("/api/runtime-skills")
        detail = client.get("/api/runtime-skills/custom-style")
        reload_result = client.post("/api/runtime-skills/reload")

    assert listing.status_code == 200
    assert "content" not in listing.json()["skills"][0]
    assert detail.status_code == 200
    assert detail.json()["content"].startswith("# custom-style")
    assert reload_result.json()["revision"].startswith("sha256:")
```

在 `tests/test_api.py` 中加入完整 fixture helper：

```python
def _write_runtime_skill_fixture(root, skill_id):
    package = root / skill_id
    package.mkdir(parents=True)
    (package / "manifest.json").write_text(
        json.dumps(
            {
                "schema_version": 1,
                "id": skill_id,
                "name": skill_id,
                "version": "1.0.0",
                "description": "测试 Runtime Skill",
                "kind": "reply-style",
                "entrypoint": "SKILL.md",
                "activation": "explicit",
                "selectors": {"relationships": [], "scenes": []},
                "permissions": ["prompt:contribute"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (package / "SKILL.md").write_text(
        f"---\nname: {skill_id}\ndescription: 测试 Runtime Skill\n---\n\n# {skill_id}\n",
        encoding="utf-8",
    )
```

- [ ] **Step 2: 运行 API 测试并确认路由 404**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api.py::test_runtime_skill_routes_list_summary_load_body_and_reload -q
```

Expected: FAIL，至少一个请求返回 404。

- [ ] **Step 3: 增加序列化辅助与三个路由**

在 `main.py` 导入 Runtime Skill 入口，并实现：

```python
@app.get("/api/runtime-skills")
def runtime_skills() -> dict:
    snapshot = get_runtime_skill_registry().snapshot()
    return {
        "skills": [summary_dict(item) for item in snapshot.skills],
        "complete": snapshot.complete,
        "revision": snapshot.revision,
        "diagnostics": [item.__dict__ for item in snapshot.diagnostics],
    }


@app.get("/api/runtime-skills/{skill_id}")
def runtime_skill(skill_id: str) -> dict:
    definition = get_runtime_skill_registry().get(resolve_style_skill_id(skill_id))
    if definition is None:
        raise HTTPException(status_code=404, detail="Runtime Skill 不存在或已失效")
    return {
        **summary_dict(definition),
        "content": definition.content,
        "selectors": definition.selectors,
        "permissions": definition.permissions,
    }


@app.post("/api/runtime-skills/reload")
def reload_runtime_skills() -> dict:
    registry = get_runtime_skill_registry()
    registry.invalidate()
    snapshot = registry.snapshot()
    return {
        "complete": snapshot.complete,
        "revision": snapshot.revision,
        "skill_count": len(snapshot.skills),
        "diagnostic_count": len(snapshot.diagnostics),
    }
```

不要返回 `resource_base`、`package_dir` 或任何本机绝对路径。

- [ ] **Step 4: 改造 style ID 校验但保留旧接口响应**

将 `_validate_style_preset_id()` 改为：

```python
def _validate_style_preset_id(style_preset_id: str) -> None:
    if not style_preset_id:
        return
    resolved = resolve_style_skill_id(style_preset_id)
    definition = get_runtime_skill_registry().get(resolved)
    if definition is None or definition.kind != "reply-style":
        raise HTTPException(
            status_code=400,
            detail="指定的回复风格不存在或尚未生成",
        )
```

`GET /api/style-presets` 第一阶段继续返回 `get_style_presets()` 的原字段，另追加 installed reply-style 的兼容项：

```python
existing = get_style_presets()
existing_ids = {item["id"] for item in existing}
installed = [
    {
        "id": item.id,
        "name": item.name,
        "description": item.description,
        "sample_count": 0,
        "confidence": "package",
    }
    for item in get_runtime_skill_registry().list()
    if item.kind == "reply-style" and item.source == "installed" and item.id not in existing_ids
]
return [*existing, *installed]
```

`GET /api/skills` 暂时继续返回旧关系结构，避免联系人 UI 同时承担两种迁移；新目录以 `/api/runtime-skills` 为唯一插件化入口。

- [ ] **Step 5: 增加 reload 不改变自动化设置测试**

```python
def test_runtime_skill_reload_does_not_change_automation_settings(monkeypatch):
    _disable_worker(monkeypatch)
    before = main_module.load_auto_reply_config()
    with TestClient(main_module.app) as client:
        response = client.post("/api/runtime-skills/reload")
    after = main_module.load_auto_reply_config()
    assert response.status_code == 200
    assert after == before
```

- [ ] **Step 6: 运行 API 和兼容测试**

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_api.py tests/test_services.py -q
```

Expected: PASS。

- [ ] **Step 7: 提交 Task 6**

```powershell
git add app/main.py app/models.py app/runtime_skills/__init__.py tests/test_api.py
git commit -m "feat: expose runtime skill catalog API"
```

### Task 7: 通用 Runtime Skill 前端目录

**Files:**
- Modify: `frontend/src/App.jsx`
- Modify: `frontend/src/App.css`

**Interfaces:**
- Consumes: `GET /api/runtime-skills`、`POST /api/runtime-skills/reload`、现有 `/api/style-presets`。
- Produces: 通用 Skill 目录、诊断展示、reload 操作；联系人仍通过原 `style_preset_id` 字段保存选择。

- [ ] **Step 1: 增加前端状态和加载请求**

在 `App` 顶层状态区增加：

```jsx
const [runtimeSkills, setRuntimeSkills] = useState({
  skills: [],
  diagnostics: [],
  complete: true,
  revision: '',
})
```

在现有初始化 `Promise.all` 中增加 `api('/api/runtime-skills')`，并调用 `setRuntimeSkills(nextRuntimeSkills)`。不要删除 Self Skill、女生聊天兼容数据或 style preset 请求。

- [ ] **Step 2: 实现 reload handler**

```jsx
const reloadRuntimeSkills = async () => {
  setBusy('runtime-skills')
  try {
    const result = await api('/api/runtime-skills/reload', { method: 'POST' })
    const catalog = await api('/api/runtime-skills')
    setRuntimeSkills(catalog)
    setStylePresets(await api('/api/style-presets'))
    showNotice(`已重新加载 ${result.skill_count} 个 Runtime Skill`)
  } catch (error) {
    showNotice(error.message, 'error')
  } finally {
    setBusy('')
  }
}
```

- [ ] **Step 3: 将固定女生风格区域改为通用目录**

保留“蒸馏个人 Skill”和“蒸馏女生聊天风格”按钮作为兼容操作；在其下新增：

```jsx
<div className="runtime-skill-catalog">
  <div className="runtime-skill-heading">
    <div>
      <span>Runtime Skill</span>
      <small>
        {runtimeSkills.skills.length} 个 · {runtimeSkills.complete ? '目录完整' : '部分可用'}
      </small>
    </div>
    <button
      type="button"
      className="button secondary"
      onClick={reloadRuntimeSkills}
      disabled={busy === 'runtime-skills'}
    >
      <RefreshCw size={16} />
      重新加载
    </button>
  </div>
  <div className="runtime-skill-list">
    {runtimeSkills.skills.map((skill) => (
      <article className="runtime-skill-item" key={skill.id}>
        <div>
          <strong>{skill.name}</strong>
          <small>{skill.id} · v{skill.version}</small>
        </div>
        <span>{skill.kind}</span>
        <p>{skill.description}</p>
        <small>{skill.source}</small>
      </article>
    ))}
  </div>
  {runtimeSkills.diagnostics.length > 0 && (
    <div className="runtime-skill-diagnostics">
      {runtimeSkills.diagnostics.map((item, index) => (
        <p key={`${item.provider}-${item.skill_id}-${item.code}-${index}`}>
          {item.skill_id || item.provider}：{item.code}
        </p>
      ))}
    </div>
  )}
</div>
```

诊断只展示 API 已脱敏的 provider、skill_id 和 code，不拼接本机路径。

- [ ] **Step 4: 添加响应式样式**

在 `App.css` 增加：

```css
.runtime-skill-catalog {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  width: 100%;
}

.runtime-skill-heading,
.runtime-skill-item > div {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.runtime-skill-list {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 10px;
}

.runtime-skill-item {
  display: grid;
  gap: 6px;
  padding: 12px;
  border: 1px solid #dce2df;
  border-radius: 14px;
  background: #fff;
}

.runtime-skill-item p,
.runtime-skill-item small,
.runtime-skill-diagnostics p {
  margin: 0;
}

.runtime-skill-diagnostics {
  padding: 10px 12px;
  border-radius: 12px;
  color: #b03740;
  background: #fff4f1;
}

@media (max-width: 640px) {
  .runtime-skill-heading {
    align-items: stretch;
    flex-direction: column;
  }
}
```

- [ ] **Step 5: 运行前端静态检查与构建**

```powershell
Set-Location frontend
npm run lint
npm run build
```

Expected: 两条命令均退出码 0；构建产物包含更新后的 `dist/assets`。

- [ ] **Step 6: 本地 API 联调检查**

启动应用后检查：

```text
GET  /api/runtime-skills
POST /api/runtime-skills/reload
GET  /api/style-presets
```

验收：目录有三种 bundled 关系 Skill；存在本地蒸馏结果时显示 Legacy Skill；reload 前后自动回复设置不变；联系人下拉仍能选择旧 `style:*` 和 installed reply-style。

- [ ] **Step 7: 提交 Task 7**

```powershell
git add frontend/src/App.jsx frontend/src/App.css
git commit -m "feat: add runtime skill catalog to workspace"
```

当前仓库不跟踪 `frontend/dist`；构建只用于验证，提交仅包含两个源文件。

### Task 8: Harness 文档、全量验证与安全链路验收

**Files:**
- Modify: `docs/harness/architecture.md`
- Modify: `docs/harness/commands.md`
- Modify: `docs/harness/knowledge-index.md`
- Modify: `docs/harness/skill-registry.md`
- Modify: `README.md`
- Modify: `skill/wechat-local-auto-reply/SKILL.md`

**Interfaces:**
- Consumes: Tasks 1–7 的最终代码和 API。
- Produces: 可复核的架构说明、安装目录说明、reload 命令、安全限制和最终验证证据。

- [ ] **Step 1: 更新架构与职责文档**

在 `docs/harness/architecture.md` 增加：

```text
Runtime Skill 数据流：
Bundled/Installed/Legacy Provider → RuntimeSkillRegistry → ReplySkillComposer
→ LangGraph style node → writer → 核心 reviewer。

安全边界：Runtime Skill 仅贡献声明式提示内容，不能执行代码、读取原始聊天、
调用微信发送或覆盖 L0-L3、dry-run、白名单和真实发送确认。
```

将 `app/self_skill.py` 职责改为“兼容期蒸馏生产者”，将 `app/runtime_skills/` 登记为运行时 Skill 加载与组合所有者。

- [ ] **Step 2: 更新命令与 README**

在 `docs/harness/commands.md` 和 `README.md` 记录本地安装方式：

```powershell
$skillSource = 'C:\path\to\my-skill'
$skillTarget = 'F:\wxChatAssistant\data\runtime-skills\installed\my-skill'
Copy-Item -LiteralPath $skillSource -Destination $skillTarget -Recurse
Invoke-RestMethod -Method Post -Uri 'http://127.0.0.1:8787/api/runtime-skills/reload'
```

同时写明：复制前确认目标目录不存在；生产工具应先写 `.staging-<uuid>`，校验完成后原子改名；当前不执行包内脚本。

- [ ] **Step 3: 更新 Harness 知识索引和项目 Skill**

在 `docs/harness/knowledge-index.md` 新增一条 `[已验证]` 知识：运行时 Skill 通过三个 Provider 和 Registry 加载，核心安全层不可覆盖。证据必须指向：

```text
app/runtime_skills/registry.py
app/runtime_skills/providers.py
app/runtime_skills/composer.py
tests/test_runtime_skill_registry.py
tests/test_runtime_skill_composer.py
```

在 `skill/wechat-local-auto-reply/SKILL.md` 的回复质量与硬边界中补充 Runtime Skill 选择顺序和“不得执行第三方代码/不得绕过发送保护”。不要把实现细节复制成第二份架构文档。

- [ ] **Step 4: 运行 Python 全量验证**

```powershell
.\.venv\Scripts\python.exe -m compileall -q app
.\.venv\Scripts\python.exe -m pytest -q
```

Expected: 两条命令退出码 0；pytest 无失败、错误或意外跳过。

- [ ] **Step 5: 运行前端全量验证**

```powershell
Set-Location frontend
npm run lint
npm run build
```

Expected: 两条命令退出码 0。

- [ ] **Step 6: 运行安全 API smoke test**

应用启动且自动回复保持关闭或 dry-run 开启时检查：

```text
GET  /api/health
GET  /api/runtime-skills
POST /api/runtime-skills/reload
GET  /api/style-presets
GET  /api/automation/settings
POST /api/generate  （使用 demo 联系人和 L0 测试文本）
POST /api/generate  （使用包含验证码和转账的 L3 测试文本）
```

验收：L0 返回候选和 `style_brief.runtime_skills`；L3 返回空候选且 reviewer 不执行；reload 前后 `enabled`、`dry_run`、白名单和游标完全一致。不得运行真实发送测试。

- [ ] **Step 7: 检查兼容和隐私回归**

使用 `rg` 确认：

```powershell
rg -n "get_style_prompt|tool_load_relationship_skill|tool_load_persona" app/agent
rg -n "api_key|conversation|SKILL.md" app/runtime_skills app/main.py
```

Expected:

- 第一条在 `app/agent` 中无匹配，证明 Consumer 不再直接依赖蒸馏实现。
- 第二条人工检查确认 Runtime Skill 日志/API 不返回 API Key、聊天正文、本机绝对包路径或完整模型提示词。

- [ ] **Step 8: 提交 Task 8**

```powershell
git add docs/harness README.md skill/wechat-local-auto-reply/SKILL.md
git commit -m "docs: document pluggable runtime skill workflow"
```

## 最终自检清单

- [ ] AC1：`app/agent` 不再导入 `app.self_skill` 获取 Skill。
- [ ] AC2：安装目录加入合法包后 reload 可发现并选用。
- [ ] AC3：目录 API 不含正文和绝对路径；详情/使用时才加载正文。
- [ ] AC4：三种关系、Self Persona、五种聚合风格和女生聊天风格兼容测试通过。
- [ ] AC5：旧 `style_preset_id` 和旧 API 无需数据迁移。
- [ ] AC6：坏包、重名和 Provider 失败被隔离并有诊断。
- [ ] AC7：L1/L2/L3、dry-run、白名单和真实发送确认保持核心控制。
- [ ] AC8：没有第三方代码执行、网络安装或数据删除入口。
- [ ] AC9：fixture 包不导入项目源码即可被 Installed Provider 加载。
- [ ] 未修改或提交用户原有的未跟踪规格文件。
