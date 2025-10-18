import json
from pathlib import Path
from typing import Dict, List, Optional

from app.schemas import DocumentSummary


class DocumentStore:
    def __init__(self, base_path: Path):
        self._file_path = base_path / "documents.json"
        self._file_path.parent.mkdir(parents=True, exist_ok=True)
        if not self._file_path.exists():
            self._write({})

    def _read(self) -> Dict[str, dict]:
        with self._file_path.open("r", encoding="utf-8") as f:
            return json.load(f)

    def _write(self, data: Dict[str, dict]) -> None:
        with self._file_path.open("w", encoding="utf-8") as f:
            json.dump(data, f, indent=2)

    def upsert(self, summary: DocumentSummary) -> None:
        data = self._read()
        data[summary.document_id] = summary.dict()
        self._write(data)

    def list(self) -> List[DocumentSummary]:
        data = self._read()
        return [DocumentSummary(**item) for item in data.values()]

    def get(self, document_id: str) -> Optional[DocumentSummary]:
        data = self._read()
        record = data.get(document_id)
        return DocumentSummary(**record) if record else None
