"""Common editor interface over the existing Kdenlive and Resolve back ends.

These wrappers only delegate: every call goes straight to the existing
``KdenliveProject`` / ``ResolveAdapter`` method with the same arguments, so
validation, preview/apply/verify and undo semantics are unchanged. New editor
adapters (future milestones) implement the same small surface.
"""
from __future__ import annotations

import os
import threading
from typing import Any, Protocol, runtime_checkable

from . import resolve as _resolve
from .kdenlive import KdenliveProject
from .resolve import ResolveAdapter


@runtime_checkable
class EditorAdapter(Protocol):
    name: str
    operations: frozenset[str]

    def describe(self) -> dict: ...
    def plan(self, operation: str, args: dict | None = None) -> dict: ...
    def apply(self, plan: dict, **kwargs: Any) -> dict: ...
    def supports(self, operation: str) -> bool: ...


class UnsupportedEditorOperation(NotImplementedError):
    pass


class KdenliveEditor:
    """Kdenlive back end. Edits are always written to a project copy (``output``)."""
    name = "kdenlive"
    operations = frozenset({"add_guide", "split", "trim"})

    def __init__(self, path: str | os.PathLike[str] | None = None, *, project: KdenliveProject | None = None):
        if project is None and path is None:
            raise ValueError("A .kdenlive path or a KdenliveProject is required.")
        self.project = project if project is not None else KdenliveProject(path)

    def supports(self, operation: str) -> bool:
        return operation in self.operations

    def describe(self) -> dict:
        return self.project.describe()

    def plan(self, operation: str, args: dict | None = None) -> dict:
        return self.project.plan(operation, args)

    def apply(self, plan: dict, *, output: str | os.PathLike[str], cancel: threading.Event | None = None) -> dict:
        return self.project.apply(plan, output, cancel)

    def undo(self, *_args: Any, **_kwargs: Any) -> dict:
        raise UnsupportedEditorOperation("Kdenlive edits go to a project copy; the original is never changed, so there is nothing to undo in place.")


class ResolveEditor:
    """DaVinci Resolve back end (verified timeline markers)."""
    name = "resolve"
    operations = frozenset({"inspect", "add_marker"})

    def __init__(self, connect: Any = None, *, adapter: ResolveAdapter | None = None):
        # Looked up at call time so tests and callers patching resolve.ResolveAdapter still apply.
        self.adapter = adapter if adapter is not None else _resolve.ResolveAdapter(connect)

    def supports(self, operation: str) -> bool:
        return operation in self.operations

    def describe(self) -> dict:
        return self.adapter.describe()

    def plan(self, operation: str, args: dict | None = None) -> dict:
        return self.adapter.plan(operation, args)

    def apply(self, plan: dict, *, cancel: threading.Event | None = None) -> dict:
        return self.adapter.apply(plan, cancel)

    def undo(self, transaction: dict, *, cancel: threading.Event | None = None) -> dict:
        return self.adapter.undo(transaction, cancel)

    def probe(self) -> dict:
        return self.adapter.probe()


EDITORS = {"kdenlive": KdenliveEditor, "resolve": ResolveEditor}


def open_editor(editor: str, *args: Any, **kwargs: Any) -> EditorAdapter:
    try:
        factory = EDITORS[str(editor).lower()]
    except KeyError:
        raise ValueError(f"Unknown editor: {editor!r}. Supported: {', '.join(sorted(EDITORS))}.") from None
    return factory(*args, **kwargs)
