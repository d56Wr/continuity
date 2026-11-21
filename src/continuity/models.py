"""Qt list models for QML."""
from __future__ import annotations

from typing import Any, Callable, Iterable

from PySide6.QtCore import QAbstractListModel, QByteArray, QModelIndex, Qt, Signal, Property


class DictListModel(QAbstractListModel):
    """A list model over a list of dicts; roles are the dict keys given at construction."""

    countChanged = Signal()

    def __init__(self, roles: Iterable[str], key: str | None = None, parent=None):
        super().__init__(parent)
        self._roles = list(roles)
        self._key = key
        self._rows: list[dict[str, Any]] = []
        self._role_ids = {Qt.ItemDataRole.UserRole + 1 + i: r for i, r in enumerate(self._roles)}

    # Qt API
    def roleNames(self):
        return {rid: QByteArray(name.encode()) for rid, name in self._role_ids.items()}

    def rowCount(self, parent=QModelIndex()):
        return 0 if parent.isValid() else len(self._rows)

    def data(self, index, role=Qt.ItemDataRole.DisplayRole):
        if not index.isValid() or not (0 <= index.row() < len(self._rows)):
            return None
        name = self._role_ids.get(role)
        return self._rows[index.row()].get(name) if name else None

    @Property(int, notify=countChanged)
    def count(self) -> int:
        return len(self._rows)

    # Python API
    def rows(self) -> list[dict[str, Any]]:
        return self._rows

    def set_rows(self, rows: list[dict[str, Any]]) -> None:
        """Replace content, keeping row identity where the key matches (smooth ListView updates)."""
        if self._key is None or not self._rows or not rows:
            self.beginResetModel()
            self._rows = list(rows)
            self.endResetModel()
            self.countChanged.emit()
            return
        old_keys = [r[self._key] for r in self._rows]
        new_keys = [r[self._key] for r in rows]
        if old_keys == new_keys:
            for i, r in enumerate(rows):
                if r != self._rows[i]:
                    self._rows[i] = r
                    idx = self.index(i)
                    self.dataChanged.emit(idx, idx)
            return
        # Different order or membership: if the old list is a suffix/prefix of the new one,
        # insert only the new rows (typical when messages arrive or older ones load).
        n_old = len(old_keys)
        if new_keys[-n_old:] == old_keys:
            added = len(new_keys) - n_old
            self.beginInsertRows(QModelIndex(), 0, added - 1)
            self._rows = list(rows)
            self.endInsertRows()
        elif new_keys[:n_old] == old_keys:
            self.beginInsertRows(QModelIndex(), n_old, len(new_keys) - 1)
            self._rows = list(rows)
            self.endInsertRows()
        else:
            self.beginResetModel()
            self._rows = list(rows)
            self.endResetModel()
        self.countChanged.emit()


class FilterHelper:
    """Keeps an unfiltered row list and pushes the filtered view into a model."""

    def __init__(self, model: DictListModel, match: Callable[[dict, str], bool]):
        self.model, self.match = model, match
        self.all: list[dict] = []
        self.query = ""
        self.extra: Callable[[dict], bool] | None = None  # additional predicate (e.g. unread only)

    def set_all(self, rows: list[dict]) -> None:
        self.all = rows
        self.apply()

    def set_query(self, q: str) -> None:
        self.query = q.strip().casefold()
        self.apply()

    def apply(self) -> None:
        q = self.query
        extra = self.extra
        self.model.set_rows([r for r in self.all
                             if (not q or self.match(r, q)) and (extra is None or extra(r))])
