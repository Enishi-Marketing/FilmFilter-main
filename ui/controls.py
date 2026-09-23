"""Reusable parameter widgets used by the parameter panel.

Each ``ParamControl`` exposes a uniform interface:

- ``value()`` / ``set_value()`` reads or writes the underlying value
- ``valueChanged`` signal fires whenever the user edits the control
- ``reset_to_default()`` restores the schema default

The parameter panel wires these into the live preview without needing to know
the internal layout of any individual control.
"""

from __future__ import annotations

from typing import Any

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QDoubleValidator, QIntValidator
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QSizePolicy,
    QSlider,
    QSpinBox,
    QToolButton,
    QVBoxLayout,
    QWidget,
)

from .schema import Param


_SLIDER_TICKS = 1000


class _ResetButton(QToolButton):
    """Tiny reset-to-default button used by every numeric/color control."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setText("↺")  # anticlockwise open circle arrow
        self.setToolTip("Reset to default")
        self.setAutoRaise(True)
        self.setFixedWidth(22)


class _LabelRow(QWidget):
    """Top row showing the parameter label and the reset button."""

    reset_clicked = Signal()

    def __init__(self, label: str, tooltip: str = "", parent: QWidget | None = None) -> None:
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._label = QLabel(label, self)
        self._label.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        if tooltip:
            self._label.setToolTip(tooltip)
        self._reset = _ResetButton(self)
        self._reset.clicked.connect(self.reset_clicked.emit)
        layout.addWidget(self._label)
        layout.addWidget(self._reset)


class FloatControl(QWidget):
    """Slider + spin box pair for a floating-point parameter."""

    valueChanged = Signal(float)

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert param.kind == "float"
        self._param = param
        self._minimum = float(param.minimum if param.minimum is not None else 0.0)
        self._maximum = float(param.maximum if param.maximum is not None else 1.0)
        self._span = max(self._maximum - self._minimum, 1e-9)
        self._default = float(param.default if param.default is not None else self._minimum)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = _LabelRow(param.label, param.tooltip, self)
        header.reset_clicked.connect(self.reset_to_default)
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._slider = QSlider(Qt.Orientation.Horizontal, self)
        self._slider.setRange(0, _SLIDER_TICKS)
        self._slider.setSingleStep(1)
        self._slider.setPageStep(max(1, _SLIDER_TICKS // 20))
        self._slider.valueChanged.connect(self._on_slider_changed)

        self._spin = QDoubleSpinBox(self)
        self._spin.setRange(self._minimum, self._maximum)
        decimals = self._auto_decimals()
        self._spin.setDecimals(decimals)
        if param.step is not None:
            self._spin.setSingleStep(float(param.step))
        else:
            self._spin.setSingleStep(self._span / 100.0)
        self._spin.setKeyboardTracking(False)
        self._spin.setFixedWidth(76)
        self._spin.valueChanged.connect(self._on_spin_changed)

        row.addWidget(self._slider, 1)
        row.addWidget(self._spin, 0)
        layout.addLayout(row)

        self.set_value(self._default)

    def _auto_decimals(self) -> int:
        # One decimal place beyond the step so values like 0.045 with a 0.01 step
        # do not round-trip-snap when loaded from a preset.
        step = self._param.step
        if step is None:
            return 3
        step = float(step)
        if step >= 1.0:
            return 0
        if step >= 0.1:
            return 2
        if step >= 0.01:
            return 3
        if step >= 0.001:
            return 4
        return 5

    def _slider_to_value(self, tick: int) -> float:
        return self._minimum + (tick / _SLIDER_TICKS) * self._span

    def _value_to_slider(self, value: float) -> int:
        ratio = (value - self._minimum) / self._span
        return int(round(max(0.0, min(1.0, ratio)) * _SLIDER_TICKS))

    def _on_slider_changed(self, tick: int) -> None:
        value = self._slider_to_value(tick)
        blocked = self._spin.blockSignals(True)
        self._spin.setValue(value)
        self._spin.blockSignals(blocked)
        self.valueChanged.emit(float(self._spin.value()))

    def _on_spin_changed(self, value: float) -> None:
        blocked = self._slider.blockSignals(True)
        self._slider.setValue(self._value_to_slider(value))
        self._slider.blockSignals(blocked)
        self.valueChanged.emit(float(value))

    def value(self) -> float:
        return float(self._spin.value())

    def set_value(self, value: Any) -> None:
        if value is None:
            value = self._default
        v = float(value)
        v = max(self._minimum, min(self._maximum, v))
        blocked_spin = self._spin.blockSignals(True)
        blocked_slider = self._slider.blockSignals(True)
        self._spin.setValue(v)
        self._slider.setValue(self._value_to_slider(v))
        self._spin.blockSignals(blocked_spin)
        self._slider.blockSignals(blocked_slider)

    def reset_to_default(self) -> None:
        self.set_value(self._default)
        self.valueChanged.emit(self.value())


class IntControl(QWidget):
    """Integer slider + spin box, with an optional 'blank = None' mode for seeds."""

    valueChanged = Signal(object)

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert param.kind == "int"
        self._param = param
        self._allow_none = param.default is None
        self._minimum = int(param.minimum if param.minimum is not None else 0)
        self._maximum = int(param.maximum if param.maximum is not None else 1000)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = _LabelRow(param.label, param.tooltip, self)
        header.reset_clicked.connect(self.reset_to_default)
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(6)

        self._line = QLineEdit(self)
        validator = QIntValidator(self._minimum, self._maximum, self)
        self._line.setValidator(validator)
        self._line.setFixedWidth(110)
        self._line.setPlaceholderText("(none)" if self._allow_none else "")
        self._line.editingFinished.connect(self._on_line_changed)

        self._spin: QSpinBox | None = None
        if not self._allow_none:
            self._spin = QSpinBox(self)
            self._spin.setRange(self._minimum, self._maximum)
            if param.step is not None:
                self._spin.setSingleStep(int(param.step))
            self._spin.setKeyboardTracking(False)
            self._spin.setFixedWidth(110)
            self._spin.valueChanged.connect(self._on_spin_changed)
            row.addWidget(self._spin, 1)
        else:
            row.addWidget(self._line, 1)
            row.addStretch(1)

        layout.addLayout(row)

        self.set_value(param.default)

    def _on_line_changed(self) -> None:
        text = self._line.text().strip()
        if not text:
            self.valueChanged.emit(None)
            return
        try:
            v = int(text)
        except ValueError:
            return
        v = max(self._minimum, min(self._maximum, v))
        self.valueChanged.emit(v)

    def _on_spin_changed(self, value: int) -> None:
        self.valueChanged.emit(int(value))

    def value(self) -> int | None:
        if self._allow_none:
            text = self._line.text().strip()
            if not text:
                return None
            try:
                return int(text)
            except ValueError:
                return None
        assert self._spin is not None
        return int(self._spin.value())

    def set_value(self, value: Any) -> None:
        if self._allow_none:
            blocked = self._line.blockSignals(True)
            self._line.setText("" if value is None else str(int(value)))
            self._line.blockSignals(blocked)
        else:
            assert self._spin is not None
            blocked = self._spin.blockSignals(True)
            self._spin.setValue(int(value if value is not None else self._param.default))
            self._spin.blockSignals(blocked)

    def reset_to_default(self) -> None:
        self.set_value(self._param.default)
        self.valueChanged.emit(self.value())


class BoolControl(QWidget):
    """Single-row checkbox parameter."""

    valueChanged = Signal(bool)

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert param.kind == "bool"
        self._param = param
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(4)
        self._check = QCheckBox(param.label, self)
        if param.tooltip:
            self._check.setToolTip(param.tooltip)
        self._check.toggled.connect(self.valueChanged.emit)
        layout.addWidget(self._check, 1)
        reset = _ResetButton(self)
        reset.clicked.connect(self.reset_to_default)
        layout.addWidget(reset)
        self.set_value(bool(param.default))

    def value(self) -> bool:
        return bool(self._check.isChecked())

    def set_value(self, value: Any) -> None:
        blocked = self._check.blockSignals(True)
        self._check.setChecked(bool(value))
        self._check.blockSignals(blocked)

    def reset_to_default(self) -> None:
        self.set_value(bool(self._param.default))
        self.valueChanged.emit(self.value())


class ChoiceControl(QWidget):
    """Drop-down for string-enum parameters such as light-leak position."""

    valueChanged = Signal(str)

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert param.kind == "choice" and param.choices
        self._param = param
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = _LabelRow(param.label, param.tooltip, self)
        header.reset_clicked.connect(self.reset_to_default)
        layout.addWidget(header)

        self._combo = QComboBox(self)
        for choice in param.choices:
            self._combo.addItem(choice)
        self._combo.currentTextChanged.connect(self.valueChanged.emit)
        layout.addWidget(self._combo)

        self.set_value(param.default)

    def value(self) -> str:
        return str(self._combo.currentText())

    def set_value(self, value: Any) -> None:
        text = str(value)
        idx = self._combo.findText(text)
        blocked = self._combo.blockSignals(True)
        if idx >= 0:
            self._combo.setCurrentIndex(idx)
        self._combo.blockSignals(blocked)

    def reset_to_default(self) -> None:
        self.set_value(self._param.default)
        self.valueChanged.emit(self.value())


class Color3Control(QWidget):
    """Three small numeric fields for an (R, G, B) tint tuple."""

    valueChanged = Signal(tuple)

    def __init__(self, param: Param, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        assert param.kind == "color3"
        self._param = param
        self._default = tuple(float(v) for v in param.default)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(2)

        header = _LabelRow(param.label, param.tooltip, self)
        header.reset_clicked.connect(self.reset_to_default)
        layout.addWidget(header)

        row = QHBoxLayout()
        row.setContentsMargins(0, 0, 0, 0)
        row.setSpacing(4)
        self._fields: list[QLineEdit] = []
        for letter in ("R", "G", "B"):
            label = QLabel(letter, self)
            label.setFixedWidth(12)
            row.addWidget(label)
            edit = QLineEdit(self)
            validator = QDoubleValidator(0.0, 2.0, 3, self)
            validator.setNotation(QDoubleValidator.Notation.StandardNotation)
            edit.setValidator(validator)
            edit.setFixedWidth(60)
            edit.editingFinished.connect(self._on_edited)
            row.addWidget(edit)
            self._fields.append(edit)
        row.addStretch(1)
        layout.addLayout(row)
        self.set_value(self._default)

    def _on_edited(self) -> None:
        self.valueChanged.emit(self.value())

    def value(self) -> tuple[float, float, float]:
        result: list[float] = []
        for i, edit in enumerate(self._fields):
            text = edit.text().strip()
            try:
                result.append(float(text))
            except ValueError:
                result.append(float(self._default[i]))
        return tuple(result)  # type: ignore[return-value]

    def set_value(self, value: Any) -> None:
        if value is None:
            value = self._default
        seq = tuple(value) + (0.0, 0.0, 0.0)
        for i, edit in enumerate(self._fields):
            blocked = edit.blockSignals(True)
            edit.setText(f"{float(seq[i]):.3f}")
            edit.blockSignals(blocked)

    def reset_to_default(self) -> None:
        self.set_value(self._default)
        self.valueChanged.emit(self.value())


def build_control(param: Param, parent: QWidget | None = None) -> QWidget:
    """Construct the right control widget for a schema entry."""
    if param.kind == "float":
        return FloatControl(param, parent)
    if param.kind == "int":
        return IntControl(param, parent)
    if param.kind == "bool":
        return BoolControl(param, parent)
    if param.kind == "choice":
        return ChoiceControl(param, parent)
    if param.kind == "color3":
        return Color3Control(param, parent)
    raise ValueError(f"Unknown parameter kind: {param.kind}")
