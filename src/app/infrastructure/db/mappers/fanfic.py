"""Мапперы Fanfic ↔ ORM и Chapter ↔ ORM."""

from __future__ import annotations

from app.domain.fanfics.entities import Chapter as ChapterEntity
from app.domain.fanfics.entities import Fanfic as FanficEntity
from app.domain.fanfics.value_objects import (
    ChapterNumber,
    ChapterTitle,
    FanficTitle,
    FicStatus,
    Summary,
)
from app.domain.shared.types import (
    ChapterId,
    FandomId,
    FanficId,
    FanficVersionId,
    UserId,
)
from app.infrastructure.db.models.chapter import Chapter as ChapterModel
from app.infrastructure.db.models.fanfic import Fanfic as FanficModel

# ---------- Fanfic ----------


def fanfic_to_domain(m: FanficModel) -> FanficEntity:
    return FanficEntity(
        id=FanficId(m.id),
        author_id=UserId(m.author_id),
        title=FanficTitle(m.title),
        summary=Summary(m.summary),
        summary_entities=list(m.summary_entities or []),
        cover_file_id=m.cover_file_id,
        cover_file_unique_id=m.cover_file_unique_id,
        fandom_id=FandomId(m.fandom_id),
        age_rating_id=int(m.age_rating_id),
        status=FicStatus(m.status),
        current_version_id=(
            FanficVersionId(m.current_version_id) if m.current_version_id is not None else None
        ),
        chapters_count=int(m.chapters_count),
        chars_count=int(m.chars_count),
        first_published_at=m.first_published_at,
        last_edit_at=m.last_edit_at,
        archived_at=m.archived_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def apply_fanfic_to_model(m: FanficModel, e: FanficEntity) -> None:
    m.author_id = int(e.author_id)
    m.title = str(e.title)
    m.summary = str(e.summary)
    m.summary_entities = list(e.summary_entities)
    m.cover_file_id = e.cover_file_id
    m.cover_file_unique_id = e.cover_file_unique_id
    m.fandom_id = int(e.fandom_id)
    m.age_rating_id = int(e.age_rating_id)
    m.status = e.status
    m.current_version_id = int(e.current_version_id) if e.current_version_id is not None else None
    m.chapters_count = int(e.chapters_count)
    m.chars_count = int(e.chars_count)
    m.first_published_at = e.first_published_at
    m.last_edit_at = e.last_edit_at
    m.archived_at = e.archived_at


def new_fanfic_model(e: FanficEntity) -> FanficModel:
    return FanficModel(
        author_id=int(e.author_id),
        title=str(e.title),
        summary=str(e.summary),
        summary_entities=list(e.summary_entities),
        cover_file_id=e.cover_file_id,
        cover_file_unique_id=e.cover_file_unique_id,
        fandom_id=int(e.fandom_id),
        age_rating_id=int(e.age_rating_id),
        status=e.status,
        current_version_id=(
            int(e.current_version_id) if e.current_version_id is not None else None
        ),
        chapters_count=int(e.chapters_count),
        chars_count=int(e.chars_count),
        first_published_at=e.first_published_at,
        last_edit_at=e.last_edit_at,
        archived_at=e.archived_at,
    )


# ---------- Chapter ----------


def chapter_to_domain(m: ChapterModel) -> ChapterEntity:
    return ChapterEntity(
        id=ChapterId(m.id),
        fic_id=FanficId(m.fic_id),
        number=ChapterNumber(int(m.number)),
        title=ChapterTitle(m.title),
        text=m.text,
        entities=list(m.entities or []),
        chars_count=int(m.chars_count),
        status=FicStatus(m.status),
        created_at=m.created_at,
        updated_at=m.updated_at,
        first_approved_at=m.first_approved_at,
    )


def apply_chapter_to_model(m: ChapterModel, e: ChapterEntity) -> None:
    m.fic_id = int(e.fic_id)
    m.number = int(e.number)
    m.title = str(e.title)
    m.text = e.text
    m.entities = list(e.entities)
    m.chars_count = int(e.chars_count)
    m.status = e.status
    m.first_approved_at = e.first_approved_at


def new_chapter_model(e: ChapterEntity) -> ChapterModel:
    return ChapterModel(
        fic_id=int(e.fic_id),
        number=int(e.number),
        title=str(e.title),
        text=e.text,
        entities=list(e.entities),
        chars_count=int(e.chars_count),
        status=e.status,
        first_approved_at=e.first_approved_at,
    )
