from pydantic import BaseModel, Field
from typing import Optional


class WAText(BaseModel):
    body: str


class WAMessage(BaseModel):
    id: str
    from_: str = Field(alias="from")
    type: str
    text: Optional[WAText] = None

    model_config = {"populate_by_name": True}


class WAValue(BaseModel):
    messages: list[WAMessage] = []


class WAChange(BaseModel):
    value: WAValue = Field(default_factory=WAValue)


class WAEntry(BaseModel):
    changes: list[WAChange] = []


class WAWebhookPayload(BaseModel):
    entry: list[WAEntry] = []
