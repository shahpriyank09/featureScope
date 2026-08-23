from __future__ import annotations

from enum import StrEnum
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DiagramType(StrEnum):
    FLOWCHART = "flowchart"
    SEQUENCE = "sequence"
    STATE_MACHINE = "state_machine"


class EvidenceSource(StrEnum):
    GITHUB = "github"
    GREPTILE = "greptile"
    CLAUDE_MEM = "claude_mem"


class PRReference(BaseModel):
    model_config = ConfigDict(frozen=True)

    owner: str
    repository: str
    number: int = Field(gt=0)

    @property
    def slug(self) -> str:
        return f"{self.owner}/{self.repository}"

    @property
    def url(self) -> str:
        return f"https://github.com/{self.slug}/pull/{self.number}"

    @property
    def cache_slug(self) -> str:
        return f"{self.owner}__{self.repository}__{self.number}"


class ChangedFile(BaseModel):
    filename: str
    status: str = "modified"
    additions: int = 0
    deletions: int = 0
    patch: str | None = None
    blob_url: str | None = None


class PullRequestContext(BaseModel):
    reference: PRReference
    title: str
    body: str = ""
    base_ref: str = "main"
    head_sha: str
    html_url: str
    author: str | None = None
    changed_files: list[ChangedFile] = Field(default_factory=list)

    @property
    def cache_key(self) -> str:
        return f"{self.reference.cache_slug}__{self.head_sha}"


class GreptileContext(BaseModel):
    available: bool = False
    summary: str = ""
    review_comments: list[str] = Field(default_factory=list)
    raw: dict[str, Any] = Field(default_factory=dict)
    error: str | None = None


class MemoryObservation(BaseModel):
    observation_id: str
    title: str
    relevance: str = ""
    narrative: str = ""
    project: str | None = None
    created_at: str | None = None


class Evidence(BaseModel):
    id: str
    source: EvidenceSource
    file_path: str | None = None
    line_start: int | None = Field(default=None, gt=0)
    line_end: int | None = Field(default=None, gt=0)
    url: str | None = None
    description: str
    excerpt: str | None = None
    observation_id: str | None = None

    @model_validator(mode="after")
    def validate_location(self) -> "Evidence":
        if self.line_end and self.line_start and self.line_end < self.line_start:
            raise ValueError("line_end must be greater than or equal to line_start")
        if self.source == EvidenceSource.CLAUDE_MEM and not self.observation_id:
            raise ValueError("Claude-Mem evidence requires observation_id")
        if self.source != EvidenceSource.CLAUDE_MEM and not (self.file_path or self.url):
            raise ValueError("Code evidence requires file_path or url")
        return self


class DiagramNode(BaseModel):
    id: str = Field(pattern=r"^[A-Za-z][A-Za-z0-9_]*$")
    label: str
    kind: str = "process"
    evidence_ids: list[str] = Field(min_length=1)


class DiagramEdge(BaseModel):
    source: str
    target: str
    label: str = ""


class DiagramSpec(BaseModel):
    diagram_type: DiagramType
    title: str
    selection_reason: str
    summary: str
    participants: list[str] = Field(default_factory=list)
    nodes: list[DiagramNode] = Field(min_length=1)
    edges: list[DiagramEdge] = Field(default_factory=list)
    evidence: list[Evidence] = Field(min_length=1)
    memories: list[MemoryObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_references(self) -> "DiagramSpec":
        node_ids = [node.id for node in self.nodes]
        if len(node_ids) != len(set(node_ids)):
            raise ValueError("diagram node IDs must be unique")

        evidence_ids = [item.id for item in self.evidence]
        if len(evidence_ids) != len(set(evidence_ids)):
            raise ValueError("evidence IDs must be unique")

        known_nodes = set(node_ids)
        known_evidence = set(evidence_ids)
        for node in self.nodes:
            missing = set(node.evidence_ids) - known_evidence
            if missing:
                raise ValueError(f"node {node.id!r} references unknown evidence: {sorted(missing)}")
        for edge in self.edges:
            if edge.source not in known_nodes or edge.target not in known_nodes:
                raise ValueError(
                    f"edge {edge.source!r} -> {edge.target!r} references an unknown node"
                )
        return self


class AnalysisSource(StrEnum):
    LIVE = "live"
    CACHE = "cache"
    FIXTURE = "fixture"


class AnalysisResult(BaseModel):
    pull_request: PullRequestContext
    diagram: DiagramSpec
    greptile: GreptileContext = Field(default_factory=GreptileContext)
    source: AnalysisSource = AnalysisSource.LIVE
    generated_at: str
    warnings: list[str] = Field(default_factory=list)
