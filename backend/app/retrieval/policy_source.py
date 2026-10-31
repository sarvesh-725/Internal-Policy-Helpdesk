import hashlib
from datetime import date
from enum import StrEnum
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator
from pypdf import PdfReader

from app.schemas import Domain, Role


class DocumentStatus(StrEnum):
    DRAFT = "draft"
    PUBLISHED = "published"
    REVOKED = "revoked"


class PolicyMetadata(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(pattern=r"^[A-Z]+-[A-Z0-9]+-\d+$", max_length=120)
    title: str = Field(min_length=3, max_length=300)
    domain: Domain
    allowed_roles: frozenset[Role] = Field(min_length=1)
    allowed_regions: frozenset[str] = Field(min_length=1)
    effective_date: date
    version: str = Field(pattern=r"^\d+(?:\.\d+){0,2}$", max_length=40)
    status: DocumentStatus
    owner_role: Role
    review_due_date: date
    expires_at: date | None = None

    @field_validator("allowed_regions")
    @classmethod
    def normalize_regions(cls, values: frozenset[str]) -> frozenset[str]:
        return frozenset(value.upper() for value in values)

    @model_validator(mode="after")
    def check_dates_and_owner(self) -> "PolicyMetadata":
        if self.review_due_date < self.effective_date:
            raise ValueError("review_due_date cannot precede effective_date")
        if self.expires_at is not None and self.expires_at <= self.effective_date:
            raise ValueError("expires_at must follow effective_date")
        if self.owner_role not in self.allowed_roles:
            raise ValueError("owner_role must be included in allowed_roles")
        return self


class PolicySourceDocument(BaseModel):
    model_config = ConfigDict(frozen=True, arbitrary_types_allowed=True)

    path: Path
    relative_path: str
    metadata: PolicyMetadata
    content: str = Field(min_length=1)
    source_hash: str


class PolicySourceError(ValueError):
    pass


def discover_policy_sources(root: Path) -> list[PolicySourceDocument]:
    if not root.exists() or not root.is_dir():
        raise PolicySourceError(f"Knowledge directory does not exist: {root}")
    sources: list[PolicySourceDocument] = []
    domain_folders = {domain.value for domain in Domain}
    for path in sorted(root.rglob("*")):
        if path.suffix.lower() not in {".md", ".pdf"} or path.parent.name not in domain_folders:
            continue
        sources.append(load_policy_source(path, root))
    if not sources:
        raise PolicySourceError("No Markdown or PDF policy sources were found.")
    return sources


def load_policy_source(path: Path, root: Path) -> PolicySourceDocument:
    raw_bytes = path.read_bytes()
    relative_path = path.relative_to(root).as_posix()
    if path.suffix.lower() == ".md":
        metadata_dict, content = parse_markdown_front_matter(raw_bytes.decode("utf-8"), relative_path)
    else:
        metadata_dict, content = parse_pdf_source(path, relative_path)

    try:
        metadata = PolicyMetadata.model_validate(metadata_dict)
    except Exception as exc:
        raise PolicySourceError(f"Invalid metadata in {relative_path}: {exc}") from exc

    parent_domain = path.parent.name.lower()
    if parent_domain != metadata.domain.value:
        raise PolicySourceError(f"Domain folder and metadata domain differ for {relative_path}")
    if not content.strip():
        raise PolicySourceError(f"No policy content found in {relative_path}")
    return PolicySourceDocument(
        path=path,
        relative_path=relative_path,
        metadata=metadata,
        content=content.strip(),
        source_hash=hashlib.sha256(raw_bytes).hexdigest(),
    )


def parse_markdown_front_matter(raw_content: str, relative_path: str) -> tuple[dict, str]:
    if not raw_content.startswith("---\n"):
        raise PolicySourceError(f"Missing YAML front matter in {relative_path}")
    _, delimiter, remainder = raw_content.partition("\n---\n")
    if not delimiter:
        raise PolicySourceError(f"Unterminated YAML front matter in {relative_path}")
    front_matter = raw_content[4 : raw_content.index("\n---\n")]
    metadata = yaml.safe_load(front_matter)
    if not isinstance(metadata, dict):
        raise PolicySourceError(f"Front matter must be a mapping in {relative_path}")
    return metadata, remainder


def parse_pdf_source(path: Path, relative_path: str) -> tuple[dict, str]:
    sidecar = path.with_suffix(".yaml")
    if not sidecar.exists():
        raise PolicySourceError(f"PDF policy requires a matching YAML metadata sidecar: {relative_path}")
    metadata = yaml.safe_load(sidecar.read_text(encoding="utf-8"))
    if not isinstance(metadata, dict):
        raise PolicySourceError(f"PDF metadata sidecar must be a mapping for {relative_path}")
    reader = PdfReader(path)
    return metadata, "\n".join(page.extract_text() or "" for page in reader.pages)
