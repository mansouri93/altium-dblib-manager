# -*- coding: utf-8 -*-
from __future__ import annotations
import logging
from PySide6.QtCore import Qt, QObject, QEvent, QPropertyAnimation, QEasingCurve, QPoint
from PySide6.QtGui import QWheelEvent
from PySide6.QtWidgets import (
    QAbstractItemView,
    QApplication,
    QComboBox,
    QAbstractSpinBox,
    QSlider,
    QDateTimeEdit,
)

logger = logging.getLogger(__name__)

class SmoothScrollFilter(QObject):
    """
    Event filter for QAbstractItemView that provides smooth, non-cellular,
    continuous pixel scrolling for both vertical and horizontal directions.
    """

    def __init__(
        self,
        target_view: QAbstractItemView,
        step_v: int = 45,
        step_h: int = 60,
        duration_ms: int = 160,
        parent: QObject | None = None,
    ) -> None:
        super().__init__(parent or target_view)
        self.view = target_view
        self.step_v = step_v
        self.step_h = step_h
        self.duration_ms = duration_ms

        self.v_bar = target_view.verticalScrollBar()
        self.h_bar = target_view.horizontalScrollBar()

        self.v_anim = QPropertyAnimation(self.v_bar, b"value", self)
        self.v_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.v_anim.setDuration(self.duration_ms)

        self.h_anim = QPropertyAnimation(self.h_bar, b"value", self)
        self.h_anim.setEasingCurve(QEasingCurve.Type.OutCubic)
        self.h_anim.setDuration(self.duration_ms)

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if event.type() == QEvent.Type.Wheel:
            # If the input device delivers high-precision pixel deltas (e.g. precision touchpads),
            # let Qt handle it directly in ScrollPerPixel mode for natural 1:1 hardware responsiveness.
            p_delta = event.pixelDelta()
            if not p_delta.isNull() and (p_delta.x() != 0 or p_delta.y() != 0):
                return False

            dx = event.angleDelta().x()
            dy = event.angleDelta().y()

            modifiers = event.modifiers()
            # Support Shift+Wheel or Alt+Wheel for horizontal scrolling
            if modifiers & Qt.KeyboardModifier.AltModifier or modifiers & Qt.KeyboardModifier.ShiftModifier:
                dx, dy = dy, dx

            handled = False

            # Vertical wheel animation
            if dy != 0 and self.v_bar.isVisible():
                steps = -dy / 120.0
                cur = (
                    self.v_anim.endValue()
                    if self.v_anim.state() == QPropertyAnimation.State.Running
                    else self.v_bar.value()
                )
                target = int(round(cur + steps * self.step_v))
                target = max(self.v_bar.minimum(), min(self.v_bar.maximum(), target))
                if target != self.v_bar.value():
                    self.v_anim.stop()
                    self.v_anim.setStartValue(self.v_bar.value())
                    self.v_anim.setEndValue(target)
                    self.v_anim.start()
                handled = True

            # Horizontal wheel animation
            if dx != 0 and self.h_bar.isVisible():
                steps = -dx / 120.0
                cur = (
                    self.h_anim.endValue()
                    if self.h_anim.state() == QPropertyAnimation.State.Running
                    else self.h_bar.value()
                )
                target = int(round(cur + steps * self.step_h))
                target = max(self.h_bar.minimum(), min(self.h_bar.maximum(), target))
                if target != self.h_bar.value():
                    self.h_anim.stop()
                    self.h_anim.setStartValue(self.h_bar.value())
                    self.h_anim.setEndValue(target)
                    self.h_anim.start()
                handled = True

            if handled:
                event.accept()
                return True

        return super().eventFilter(obj, event)


def enable_smooth_scroll(
    view: QAbstractItemView,
    step_v: int = 45,
    step_h: int = 60,
    duration_ms: int = 160,
) -> SmoothScrollFilter:
    """
    Enables pixel-based smooth scrolling on a QAbstractItemView (e.g. QTableView),
    detaching scroll step size from individual cell / row / column dimensions.
    """
    view.setVerticalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.setHorizontalScrollMode(QAbstractItemView.ScrollMode.ScrollPerPixel)
    view.verticalScrollBar().setSingleStep(step_v)
    view.horizontalScrollBar().setSingleStep(step_h)

    smooth_filter = SmoothScrollFilter(
        view,
        step_v=step_v,
        step_h=step_h,
        duration_ms=duration_ms,
        parent=view,
    )
    view.viewport().installEventFilter(smooth_filter)
    # Keep reference on view to avoid GC
    view._smooth_scroll_filter = smooth_filter
    return smooth_filter


class DisableWidgetWheelScrollFilter(QObject):
    """
    Global event filter that blocks mouse wheel value changes on input widgets
    (such as QComboBox, QSpinBox, QDoubleSpinBox, QSlider, QDateTimeEdit),
    ensuring that mouse wheel scrolling only navigates/scrolls the window or view.
    """

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._is_forwarding = False

    def eventFilter(self, obj: QObject, event: QEvent) -> bool:
        if self._is_forwarding:
            return False

        if event.type() == QEvent.Type.Wheel:
            target = None
            if isinstance(obj, (QComboBox, QAbstractSpinBox, QSlider, QDateTimeEdit)):
                target = obj
            elif hasattr(obj, "parent") and isinstance(obj.parent(), (QComboBox, QAbstractSpinBox, QSlider, QDateTimeEdit)):
                target = obj.parent()

            if target is not None:
                # If combobox dropdown popup view is currently open and visible, allow scrolling inside its popup list
                if isinstance(target, QComboBox) and target.view() and target.view().isVisible():
                    return False

                # Forward wheel event up the parent hierarchy so the enclosing scroll area/window scrolls
                parent = target.parentWidget()
                self._is_forwarding = True
                try:
                    while parent:
                        fwd = QWheelEvent(
                            event.position(),
                            event.globalPosition(),
                            event.pixelDelta(),
                            event.angleDelta(),
                            event.buttons(),
                            event.modifiers(),
                            event.phase(),
                            event.inverted(),
                        )
                        fwd.setAccepted(False)
                        QApplication.sendEvent(parent, fwd)
                        if fwd.isAccepted():
                            break
                        parent = parent.parentWidget()
                finally:
                    self._is_forwarding = False

                # Consume the wheel event on the parameter widget to prevent changing its value
                event.accept()
                return True

        return super().eventFilter(obj, event)


_global_wheel_filter_instance: DisableWidgetWheelScrollFilter | None = None


def install_global_wheel_scroll_filter(app: QApplication | None = None) -> DisableWidgetWheelScrollFilter | None:
    """
    Install application-wide event filter to disable mouse wheel value modification
    on all lists/comboboxes, spinboxes, and sliders across the application.
    """
    global _global_wheel_filter_instance
    if _global_wheel_filter_instance is not None:
        return _global_wheel_filter_instance

    if app is None:
        app = QApplication.instance()
    if not app:
        return None

    _global_wheel_filter_instance = DisableWidgetWheelScrollFilter(app)
    app.installEventFilter(_global_wheel_filter_instance)
    logger.info("Installed global wheel scroll filter: parameter value changing via mouse wheel is disabled.")
    return _global_wheel_filter_instance

