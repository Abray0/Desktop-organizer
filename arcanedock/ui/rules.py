"""Editor for a fence's extra rules: name patterns and age."""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (QCheckBox, QDialog, QDialogButtonBox, QFormLayout,
                               QLabel, QLineEdit, QSpinBox, QVBoxLayout)

from . import theme


class RulesDialog(QDialog):
    """Rules win over the plain kind-of-file matching, so a Screenshots fence
    beats the Images fence for anything that matches its pattern."""

    def __init__(self, fence: dict, parent=None):
        super().__init__(parent)
        self.setWindowTitle(f"Rules for “{fence['name']}”")
        self.setStyleSheet(theme.qss())
        self.setMinimumWidth(430)
        rules = fence.get("rules") or {}

        layout = QVBoxLayout(self)
        blurb = QLabel(
            "Items matching these rules land in this fence whatever their kind.\n"
            "Leave everything blank to sort by kind only.")
        blurb.setObjectName("Subtle")
        blurb.setWordWrap(True)
        layout.addWidget(blurb)

        form = QFormLayout()
        form.setContentsMargins(0, 10, 0, 6)
        form.setSpacing(8)

        self.patterns = QLineEdit(", ".join(rules.get("patterns") or []))
        self.patterns.setObjectName("Search")
        self.patterns.setPlaceholderText("Screenshot*, *.log, invoice*")
        form.addRow("Name matches", self.patterns)

        self.older_on = QCheckBox("Only items not touched for")
        self.older_on.setChecked(bool(rules.get("older_than_days")))
        self.older = QSpinBox()
        self.older.setRange(1, 3650)
        self.older.setSuffix("  days")
        self.older.setValue(int(rules.get("older_than_days") or 30))
        form.addRow(self.older_on, self.older)

        self.newer_on = QCheckBox("Only items touched within")
        self.newer_on.setChecked(bool(rules.get("newer_than_days")))
        self.newer = QSpinBox()
        self.newer.setRange(1, 3650)
        self.newer.setSuffix("  days")
        self.newer.setValue(int(rules.get("newer_than_days") or 7))
        form.addRow(self.newer_on, self.newer)
        layout.addLayout(form)

        buttons = QDialogButtonBox(QDialogButtonBox.Ok | QDialogButtonBox.Cancel,
                                   Qt.Horizontal, self)
        buttons.accepted.connect(self.accept)
        buttons.rejected.connect(self.reject)
        layout.addWidget(buttons)

    def rules(self) -> dict:
        patterns = [p.strip() for p in self.patterns.text().split(",") if p.strip()]
        return {
            "patterns": patterns,
            "older_than_days": self.older.value() if self.older_on.isChecked() else 0,
            "newer_than_days": self.newer.value() if self.newer_on.isChecked() else 0,
        }
