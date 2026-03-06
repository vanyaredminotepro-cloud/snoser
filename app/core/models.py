from dataclasses import dataclass


@dataclass(slots=True)
class IncomingPost:
    source_country: str
    source_channel: str
    message_id: int
    text: str
    has_media: bool
    media_file_id: str | None = None
    media_type: str | None = None
