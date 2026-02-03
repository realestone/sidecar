import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

from .errors import SidecarError
from .models import SCHEMA_VERSION, Prompt

DEFAULT_DB_PATH = Path.home() / ".config" / "sidecar" / "sidecar.db"


class Storage:
    def __init__(self, db_path: Path | None = None):
        self.db_path = db_path or DEFAULT_DB_PATH
        self.db_path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.db_path))
        self._conn.row_factory = sqlite3.Row
        self.init_db()

    def init_db(self) -> None:
        try:
            self._conn.executescript("""
                CREATE TABLE IF NOT EXISTS meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );

                CREATE TABLE IF NOT EXISTS prompts (
                    id TEXT PRIMARY KEY,
                    name TEXT UNIQUE NOT NULL,
                    content TEXT NOT NULL,
                    category TEXT NOT NULL DEFAULT 'general',
                    variables TEXT NOT NULL DEFAULT '[]',
                    use_count INTEGER NOT NULL DEFAULT 0,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    record_type TEXT NOT NULL DEFAULT 'prompt',
                    schema_version INTEGER NOT NULL DEFAULT 1
                );
            """)
            row = self._conn.execute(
                "SELECT value FROM meta WHERE key = 'schema_version'"
            ).fetchone()
            if row is None:
                self._conn.execute(
                    "INSERT INTO meta (key, value) VALUES ('schema_version', ?)",
                    (str(SCHEMA_VERSION),),
                )
                self._conn.commit()
            else:
                self.check_schema_version(int(row["value"]))
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e

    def check_schema_version(self, version: int) -> None:
        if version != SCHEMA_VERSION:
            raise SidecarError.schema_version(SCHEMA_VERSION, version)

    def _row_to_prompt(self, row: sqlite3.Row) -> Prompt:
        return Prompt(
            id=row["id"],
            name=row["name"],
            content=row["content"],
            category=row["category"],
            variables=json.loads(row["variables"]),
            use_count=row["use_count"],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
            record_type=row["record_type"],
            schema_version=row["schema_version"],
        )

    def save_prompt(self, prompt: Prompt) -> Prompt:
        try:
            self._conn.execute(
                """INSERT INTO prompts
                   (id, name, content, category, variables, use_count,
                    created_at, updated_at, record_type, schema_version)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    prompt.id,
                    prompt.name,
                    prompt.content,
                    prompt.category,
                    json.dumps(prompt.variables),
                    prompt.use_count,
                    prompt.created_at,
                    prompt.updated_at,
                    prompt.record_type,
                    prompt.schema_version,
                ),
            )
            self._conn.commit()
            return prompt
        except sqlite3.IntegrityError:
            raise SidecarError.prompt_already_exists(prompt.name)
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e

    def get_prompt(self, name: str) -> Prompt:
        try:
            row = self._conn.execute(
                "SELECT * FROM prompts WHERE name = ?", (name,)
            ).fetchone()
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e
        if row is None:
            raise SidecarError.prompt_not_found(name)
        return self._row_to_prompt(row)

    def delete_prompt(self, name: str) -> Prompt:
        prompt = self.get_prompt(name)
        try:
            self._conn.execute("DELETE FROM prompts WHERE name = ?", (name,))
            self._conn.commit()
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e
        return prompt

    def list_prompts(self, category: str | None = None) -> list[Prompt]:
        try:
            if category:
                rows = self._conn.execute(
                    "SELECT * FROM prompts WHERE category = ? ORDER BY name",
                    (category,),
                ).fetchall()
            else:
                rows = self._conn.execute(
                    "SELECT * FROM prompts ORDER BY name"
                ).fetchall()
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e
        return [self._row_to_prompt(row) for row in rows]

    def search_prompts(self, query: str) -> list[Prompt]:
        try:
            pattern = f"%{query}%"
            rows = self._conn.execute(
                """SELECT * FROM prompts
                   WHERE name LIKE ? OR content LIKE ? OR category LIKE ?
                   ORDER BY name""",
                (pattern, pattern, pattern),
            ).fetchall()
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e
        return [self._row_to_prompt(row) for row in rows]

    def recent_prompts(self, limit: int = 10) -> list[Prompt]:
        try:
            rows = self._conn.execute(
                "SELECT * FROM prompts ORDER BY updated_at DESC LIMIT ?",
                (limit,),
            ).fetchall()
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e
        return [self._row_to_prompt(row) for row in rows]

    def record_use(self, name: str) -> Prompt:
        prompt = self.get_prompt(name)
        now = datetime.now(timezone.utc).isoformat()
        try:
            self._conn.execute(
                "UPDATE prompts SET use_count = use_count + 1, updated_at = ? WHERE name = ?",
                (now, name),
            )
            self._conn.commit()
        except sqlite3.Error as e:
            raise SidecarError.storage(str(e)) from e
        return self.get_prompt(name)
