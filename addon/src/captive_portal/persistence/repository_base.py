# SPDX-FileCopyrightText: 2025 Andrew Grimberg
# SPDX-License-Identifier: Apache-2.0
"""Base repository abstraction for data access."""

from abc import ABC, abstractmethod
from typing import Generic, TypeVar

from sqlmodel import Session

T = TypeVar("T")


class BaseRepository(ABC, Generic[T]):
    """Base repository with common CRUD operations.

    Type parameter T represents the model class.
    """

    def __init__(self, session: Session) -> None:
        """Initialize repository with database session.

        Args:
            session: SQLModel/SQLAlchemy session.
        """
        self.session = session

    @abstractmethod
    def get_model_class(self) -> type[T]:
        """Return the model class this repository manages."""
        ...

    def add(self, entity: T) -> T:
        """Add new entity to session and flush.

        Args:
            entity: Model instance to add.

        Returns:
            Added entity with generated fields populated.
        """
        self.session.add(entity)
        self.session.flush()
        self.session.refresh(entity)
        return entity

    def commit(self) -> None:
        """Commit current transaction."""
        self.session.commit()

    def rollback(self) -> None:
        """Rollback current transaction."""
        self.session.rollback()
