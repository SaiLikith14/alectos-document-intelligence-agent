from uuid import UUID
from pydantic import BaseModel, ConfigDict


class SessionCreate(BaseModel):
    title: str | None = None


class SessionRead(BaseModel):
    id: UUID
    title: str | None
    model_config = ConfigDict(from_attributes=True)
