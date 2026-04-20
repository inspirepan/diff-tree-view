from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class HunkStats:
    added: int = 0
    removed: int = 0

    def __add__(self, other: HunkStats) -> HunkStats:
        return HunkStats(self.added + other.added, self.removed + other.removed)


@dataclass(frozen=True, slots=True)
class FileChange:
    path: str
    status: str
    stats: HunkStats = field(default_factory=HunkStats)
    old_path: str | None = None
    ignored: bool = False
    is_binary: bool = False
    is_conflict: bool = False

    @property
    def is_rename(self) -> bool:
        return self.status == "R" or self.old_path is not None


@dataclass(frozen=True, slots=True)
class FileSides:
    before: str = ""
    after: str = ""
    binary: bool = False


@dataclass(frozen=True, slots=True)
class Change:
    change_id: str
    short_id: str
    description: str
    author: str = ""
    timestamp: str = ""
    files: tuple[FileChange, ...] = ()
    graph: str = "○"

    def stats(self) -> HunkStats:
        total = HunkStats()
        for file_change in self.files:
            total += file_change.stats
        return total
