import os
from datetime import datetime
from pathlib import Path
from typing import Any

from core.execution.execution_plan import RiskLevel
from core.infra.config import config
from core.infra.logger_config import logger
from core.shared.paths import get_app_root, get_user_data_dir
from core.shared.sqlite_base import SQLiteBase
from core.tools.base import BaseTool


class NotesDatabase(SQLiteBase):
    """SQLite repository for quick notes and to-do reminders."""

    def __init__(self, db_path: str | Path | None = None) -> None:
        target_db: str | Path = (
            get_user_data_dir() / "notes.db" if db_path is None else db_path
        )
        super().__init__(target_db)
        self._init_tables()

    def _init_tables(self) -> None:
        try:
            with self.connection() as conn:
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS notes (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        tag TEXT,
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    """
                    CREATE TABLE IF NOT EXISTS reminders (
                        id INTEGER PRIMARY KEY AUTOINCREMENT,
                        content TEXT NOT NULL,
                        status TEXT NOT NULL DEFAULT 'pending',
                        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                        completed_at TIMESTAMP
                    );
                    """
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_notes_created ON notes(created_at DESC);"
                )
                conn.execute(
                    "CREATE INDEX IF NOT EXISTS idx_reminders_status ON reminders(status);"
                )
        except Exception as e:
            logger.error(f"Error initializing notes database tables: {e}")


class NotesTool(BaseTool):
    """Tool for capturing quick notes, searching thoughts, and managing to-do reminders with optional Markdown/Obsidian sync."""

    name = "notes"
    description = (
        "Gerencia anotações rápidas e lembretes/tarefas (To-Do) em banco SQLite local, "
        "com suporte a espelhamento automático em arquivos Markdown ou cofre do Obsidian."
    )
    risk_level = RiskLevel.SAFE

    def __init__(
        self,
        db: NotesDatabase | None = None,
        markdown_dir: str | Path | None = None,
    ) -> None:
        self._db = db
        cfg_notes = config.get("tools", {}).get("notes", {})
        self._markdown_dir_override = Path(markdown_dir) if markdown_dir else None
        self._cfg_markdown_dir = cfg_notes.get("markdown_dir", "")

    @property
    def db(self) -> NotesDatabase:
        if self._db is None:
            self._db = NotesDatabase()
        return self._db

    @property
    def markdown_dir(self) -> Path | None:
        if self._markdown_dir_override:
            return self._markdown_dir_override
        configured = (
            config.get("tools", {})
            .get("notes", {})
            .get("markdown_dir", self._cfg_markdown_dir)
        )
        if configured and str(configured).strip():
            p = Path(configured)
            return p if p.is_absolute() else (get_app_root() / p)
        return None

    def get_parameters_schema(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action": {
                    "type": "string",
                    "enum": [
                        "add_note",
                        "list_notes",
                        "search_notes",
                        "add_reminder",
                        "list_reminders",
                        "complete_reminder",
                    ],
                    "description": (
                        "Ação a executar: 'add_note' (salvar anotação), 'list_notes' (listar últimas notas), "
                        "'search_notes' (buscar termo nas notas), 'add_reminder' (novo lembrete/tarefa), "
                        "'list_reminders' (listar pendências) ou 'complete_reminder' (concluir tarefa)."
                    ),
                },
                "content": {
                    "type": "string",
                    "description": "Conteúdo textual da nota ou lembrete.",
                },
                "tag": {
                    "type": "string",
                    "description": "Etiqueta ou categoria opcional para a nota (ex: 'ideia', 'trabalho', 'reuniao').",
                },
                "query": {
                    "type": "string",
                    "description": "Termo de busca para filtrar notas existentes.",
                },
                "reminder_id": {
                    "type": "integer",
                    "description": "ID do lembrete a marcar como concluído.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Número máximo de registros retornados (padrão: 10).",
                },
            },
            "required": ["action"],
        }

    def execute(
        self,
        action: str = "list_notes",
        content: str = "",
        tag: str = "",
        query: str = "",
        reminder_id: int | None = None,
        limit: int = 10,
        **kwargs: Any,
    ) -> dict[str, Any]:
        act = (action or "list_notes").strip().lower()

        if act == "add_note":
            return self._add_note(content=content, tag=tag)
        elif act in ("list_notes", "get_notes"):
            return self._list_notes(limit=limit, tag=tag)
        elif act == "search_notes":
            return self._search_notes(query=query or content, limit=limit)
        elif act == "add_reminder":
            return self._add_reminder(content=content)
        elif act in ("list_reminders", "get_reminders"):
            return self._list_reminders(limit=limit)
        elif act == "complete_reminder":
            return self._complete_reminder(
                reminder_id=reminder_id, content_match=content
            )
        else:
            return {
                "success": False,
                "error": f"Ação de notas desconhecida '{action}'.",
            }

    def _add_note(self, content: str, tag: str = "") -> dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {
                "success": False,
                "error": "O conteúdo da nota não pode estar vazio.",
            }

        clean_tag = tag.strip().lower() if tag else None
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO notes (content, tag, created_at) VALUES (?, ?, ?);",
                (text, clean_tag, now_iso),
            )
            note_id = cursor.lastrowid

        md_synced = self._append_to_markdown_if_configured(text, clean_tag)

        logger.info(
            f"Created note #{note_id} (tag: {clean_tag}, md_synced: {md_synced})"
        )
        return {
            "success": True,
            "action": "add_note",
            "note_id": note_id,
            "content": text,
            "tag": clean_tag,
            "created_at": now_iso,
            "markdown_synced": md_synced,
            "message": "Nota registrada com sucesso.",
        }

    def _list_notes(self, limit: int = 10, tag: str = "") -> dict[str, Any]:
        lim = max(1, min(limit, 50))
        clean_tag = tag.strip().lower() if tag else None

        with self.db.connection() as conn:
            cursor = conn.cursor()
            if clean_tag:
                cursor.execute(
                    "SELECT id, content, tag, created_at FROM notes WHERE tag = ? ORDER BY id DESC LIMIT ?;",
                    (clean_tag, lim),
                )
            else:
                cursor.execute(
                    "SELECT id, content, tag, created_at FROM notes ORDER BY id DESC LIMIT ?;",
                    (lim,),
                )
            rows = cursor.fetchall()

        items = [
            {
                "id": r[0],
                "content": r[1],
                "tag": r[2],
                "created_at": str(r[3]),
            }
            for r in rows
        ]

        return {
            "success": True,
            "action": "list_notes",
            "count": len(items),
            "notes": items,
        }

    def _search_notes(self, query: str, limit: int = 10) -> dict[str, Any]:
        q = (query or "").strip()
        if not q:
            return self._list_notes(limit=limit)

        lim = max(1, min(limit, 50))
        search_pattern = f"%{q}%"

        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, content, tag, created_at FROM notes WHERE content LIKE ? OR tag LIKE ? ORDER BY id DESC LIMIT ?;",
                (search_pattern, search_pattern, lim),
            )
            rows = cursor.fetchall()

        items = [
            {
                "id": r[0],
                "content": r[1],
                "tag": r[2],
                "created_at": str(r[3]),
            }
            for r in rows
        ]

        return {
            "success": True,
            "action": "search_notes",
            "query": q,
            "count": len(items),
            "notes": items,
        }

    def _add_reminder(self, content: str) -> dict[str, Any]:
        text = (content or "").strip()
        if not text:
            return {
                "success": False,
                "error": "O texto do lembrete não pode estar vazio.",
            }

        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO reminders (content, status, created_at) VALUES (?, 'pending', ?);",
                (text, now_iso),
            )
            rem_id = cursor.lastrowid

        logger.info(f"Added reminder #{rem_id}: '{text}'")
        return {
            "success": True,
            "action": "add_reminder",
            "reminder_id": rem_id,
            "content": text,
            "status": "pending",
            "message": f"Lembrete '{text}' adicionado com sucesso.",
        }

    def _list_reminders(self, limit: int = 20) -> dict[str, Any]:
        lim = max(1, min(limit, 100))
        with self.db.connection() as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT id, content, status, created_at FROM reminders WHERE status = 'pending' ORDER BY id ASC LIMIT ?;",
                (lim,),
            )
            rows = cursor.fetchall()

        items = [
            {
                "id": r[0],
                "content": r[1],
                "status": r[2],
                "created_at": str(r[3]),
            }
            for r in rows
        ]

        return {
            "success": True,
            "action": "list_reminders",
            "count": len(items),
            "reminders": items,
        }

    def _complete_reminder(
        self, reminder_id: int | None = None, content_match: str = ""
    ) -> dict[str, Any]:
        now_iso = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        with self.db.connection() as conn:
            cursor = conn.cursor()
            target_id = None
            target_content = ""

            if reminder_id is not None:
                cursor.execute(
                    "SELECT id, content FROM reminders WHERE id = ? AND status = 'pending';",
                    (reminder_id,),
                )
                row = cursor.fetchone()
                if row:
                    target_id, target_content = row[0], row[1]
            elif content_match and content_match.strip():
                clean_term = f"%{content_match.strip()}%"
                cursor.execute(
                    "SELECT id, content FROM reminders WHERE content LIKE ? AND status = 'pending' ORDER BY id ASC LIMIT 1;",
                    (clean_term,),
                )
                row = cursor.fetchone()
                if row:
                    target_id, target_content = row[0], row[1]

            if target_id is None:
                return {
                    "success": False,
                    "action": "complete_reminder",
                    "error": "Nenhum lembrete pendente correspondente foi encontrado.",
                }

            cursor.execute(
                "UPDATE reminders SET status = 'completed', completed_at = ? WHERE id = ?;",
                (now_iso, target_id),
            )

        logger.info(f"Marked reminder #{target_id} as completed.")
        return {
            "success": True,
            "action": "complete_reminder",
            "reminder_id": target_id,
            "content": target_content,
            "message": f"Lembrete '{target_content}' marcado como concluído.",
        }

    def _append_to_markdown_if_configured(self, text: str, tag: str | None) -> bool:
        md_dir = self.markdown_dir
        if not md_dir:
            return False

        try:
            os.makedirs(md_dir, exist_ok=True)
            today_str = datetime.now().strftime("%Y-%m-%d")
            file_path = md_dir / f"Jarvis_Notes_{today_str}.md"

            tag_part = f" `#{tag}`" if tag else ""
            time_str = datetime.now().strftime("%H:%M")
            entry = f"- **{time_str}**{tag_part}: {text}\n"

            with open(file_path, "a", encoding="utf-8") as f:
                f.write(entry)
            return True
        except Exception as e:
            logger.warning(f"Failed to append note to Markdown file in '{md_dir}': {e}")
            return False
