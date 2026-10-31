import hashlib
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class PolicyChunkDraft:
    section_id: str
    ordinal: int
    content: str
    content_hash: str


def chunk_policy_content(content: str, *, chunk_size: int, overlap: int) -> list[PolicyChunkDraft]:
    if chunk_size < 300 or overlap < 0 or overlap >= chunk_size:
        raise ValueError("Chunk configuration is invalid.")
    sections = split_sections(content)
    chunks: list[PolicyChunkDraft] = []
    ordinal = 0
    for heading, section_text in sections:
        for fragment in split_text(section_text, chunk_size=chunk_size, overlap=overlap):
            normalized = "\n".join(line.rstrip() for line in fragment.strip().splitlines()).strip()
            if not normalized:
                continue
            ordinal += 1
            chunks.append(
                PolicyChunkDraft(
                    section_id=slugify(heading),
                    ordinal=ordinal,
                    content=normalized,
                    content_hash=hashlib.sha256(normalized.encode("utf-8")).hexdigest(),
                )
            )
    if not chunks:
        raise ValueError("Policy content produced no chunks.")
    return chunks


def split_sections(content: str) -> list[tuple[str, str]]:
    matches = list(re.finditer(r"(?m)^#{1,3}\s+(.+?)\s*$", content))
    if not matches:
        return [("policy", content)]
    sections: list[tuple[str, str]] = []
    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(content)
        body = content[match.start() : end].strip()
        sections.append((match.group(1), body))
    return sections


def split_text(text: str, *, chunk_size: int, overlap: int) -> list[str]:
    if len(text) <= chunk_size:
        return [text]
    paragraphs = [paragraph.strip() for paragraph in re.split(r"\n\s*\n", text) if paragraph.strip()]
    chunks: list[str] = []
    current = ""
    for paragraph in paragraphs:
        candidate = f"{current}\n\n{paragraph}".strip()
        if len(candidate) <= chunk_size:
            current = candidate
            continue
        if current:
            chunks.append(current)
        carry = current[-overlap:] if overlap else ""
        current = f"{carry}\n\n{paragraph}".strip()
        while len(current) > chunk_size:
            chunks.append(current[:chunk_size])
            current = current[chunk_size - overlap :]
    if current:
        chunks.append(current)
    return chunks


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return slug or "policy"
