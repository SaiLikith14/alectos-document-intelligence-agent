from uuid import UUID
from pydantic import BaseModel, ConfigDict


class DocumentRead(BaseModel):
    id: UUID
    filename: str
    mime_type: str
    status: str
    page_count: int | None
    error_message: str | None
    model_config = ConfigDict(from_attributes=True)
