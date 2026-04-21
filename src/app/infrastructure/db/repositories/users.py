"""UserRepository: реализация порта IUserRepository."""

from __future__ import annotations

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.application.users.ports import IUserRepository
from app.domain.shared.types import UserId
from app.domain.users.entities import User as UserEntity
from app.infrastructure.db.mappers.user import (
    apply_to_model,
    new_model_from_domain,
    to_domain,
)
from app.infrastructure.db.models.user import User as UserModel


class UserRepository(IUserRepository):
    def __init__(self, session: AsyncSession) -> None:
        self._s = session

    async def get(self, user_id: UserId) -> UserEntity | None:
        row = await self._s.get(UserModel, int(user_id))
        return to_domain(row) if row else None

    async def get_by_nick(self, nick_lower: str) -> UserEntity | None:
        stmt = select(UserModel).where(func.lower(UserModel.author_nick) == nick_lower)
        row = (await self._s.execute(stmt)).scalar_one_or_none()
        return to_domain(row) if row else None

    async def save(self, user: UserEntity) -> None:
        existing = await self._s.get(UserModel, int(user.id))
        if existing is None:
            self._s.add(new_model_from_domain(user))
        else:
            apply_to_model(existing, user)
        await self._s.flush()

    async def upsert_touch(self, user: UserEntity) -> None:
        """Быстрый upsert для middleware user_upsert. Ничего не flush'ит сверх обычного save."""
        await self.save(user)

    async def get_role(self, user_id: UserId) -> str | None:
        stmt = select(UserModel.role).where(UserModel.id == int(user_id))
        val = (await self._s.execute(stmt)).scalar_one_or_none()
        return val.value if val is not None else None

    async def is_nick_taken(
        self,
        nick_lower: str,
        *,
        except_user_id: UserId | None = None,
    ) -> bool:
        stmt = select(UserModel.id).where(func.lower(UserModel.author_nick) == nick_lower)
        if except_user_id is not None:
            stmt = stmt.where(UserModel.id != int(except_user_id))
        val = (await self._s.execute(stmt.limit(1))).scalar_one_or_none()
        return val is not None
