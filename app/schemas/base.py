"""Shared Pydantic base configuration.

`ORMModel` turns on `from_attributes` once so every read schema can be built
directly from a SQLAlchemy row (`Schema.model_validate(orm_obj)`), instead of
repeating the config on each class.
"""

from pydantic import BaseModel, ConfigDict


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)
