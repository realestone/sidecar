from dataclasses import dataclass, field
from datetime import datetime, timezone
from uuid import uuid4

SCHEMA_VERSION = 1


@dataclass
class Prompt:
    name: str
    content: str
    category: str = "general"
    variables: list[str] = field(default_factory=list)
    id: str = field(default_factory=lambda: str(uuid4()))
    use_count: int = 0
    created_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    updated_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )
    record_type: str = "prompt"
    schema_version: int = SCHEMA_VERSION

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "content": self.content,
            "category": self.category,
            "variables": self.variables,
            "use_count": self.use_count,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "record_type": self.record_type,
            "schema_version": self.schema_version,
        }
