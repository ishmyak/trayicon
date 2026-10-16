#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Tray Monitor: два индикатора в системном трее — CPU и RAM.

- Фон иконки — цвет панели (снимается пикселем с экрана, запасной вариант —
  системная палитра QPalette::Window).
- Цвет графика (цвет2) — производный от фона (цвет1) в HSV: спокойный оттенок
  и гарантированный контраст; для тёмного фона осветляем, для светлого — затемняем.
- История 32 точки, график CPU — только линия, RAM — линия с заливкой под ней,
  обновление раз в секунду.
- Цвета пересчитываются при каждой перерисовке, чтобы реагировать на смену
  системной темы без перезапуска.
- Контекстное меню «Выход» на каждой иконке.
- Если системный трей недоступен — сообщение в stderr и выход с кодом 1.
"""

import sys

import psutil
from PyQt5.QtCore import QRectF, QTimer, Qt
from PyQt5.QtGui import QColor, QGuiApplication, QIcon, QPainter, QPainterPath, QPen, QPixmap
from PyQt5.QtWidgets import QApplication, QMenu, QSystemTrayIcon

ICON_SIZE = 64
HISTORY = 32
UPDATE_MS = 1000
MARGIN = 4
PANEL_SAMPLE_Y = 18
PANEL_SAMPLE_X = (0.3, 0.5, 0.7)
OUTLINE_RADIUS = 2          # радиус скругления углов обводки графика
FILL_ALPHA = 77             # 30% прозрачности заливки под линией RAM (из 255)

# Константы расчёта цвета2 из цвета1 (фона трея).
LUMA_THRESHOLD = 0.5    # >= порога — фон считается светлым
SAT_MAX = 35            # ограничение насыщенности, чтобы цвет был спокойным
V_DELTA = 40            # сдвиг яркости: светлый фон — темнее, тёмный — светлее
V_MIN = 15              # нижняя граница яркости (без чистого чёрного)
V_MAX = 90              # верхняя граница яркости (без чистого белого)
V_DIFF_MIN = 30         # минимальный контраст яркости с фоном


def gb(nBytes):
    return nBytes / (1024.0 ** 3)


def computeGraphColor(oColor):
    """Вычисляет цвет2 из цвета фона трея (цвет1) для максимального спокойного контраста.

    Порядок: считается светлота luma; затем HSV-составляющие цвет2 —
    H берётся как у фона, S ограничивается 35, а V сдвигается на 40 в сторону
    контраста и упирается в диапазон 15..90 с гарантированным отличием от фона.
    """
    # Светлота по формуле Rec. 601 (0..1): >= 0.5 — светлый фон.
    dLuma = (0.299 * oColor.red() + 0.587 * oColor.green()
             + 0.114 * oColor.blue()) / 255.0
    bLight = dLuma >= LUMA_THRESHOLD

    nHue, nSat1, nVal1, _ = oColor.getHsv()   # PyQt: H(0-359), S(0-255), V(0-255)

    # Пересчёт в шкалу 0..100 из 0..255.
    dSat1 = nSat1 / 255.0 * 100.0
    dVal1 = nVal1 / 255.0 * 100.0

    dSat2 = min(dSat1, SAT_MAX)
    dVal2 = dVal1 - V_DELTA if bLight else dVal1 + V_DELTA
    dVal2 = max(min(dVal2, V_MAX), V_MIN)

    # Если после ограничения контраст слишком мал — довести до V_DIFF_MIN.
    if abs(dVal2 - dVal1) < V_DIFF_MIN:
        dVal2 = (dVal1 + V_DIFF_MIN) if dVal2 >= dVal1 else (dVal1 - V_DIFF_MIN)
        dVal2 = max(min(dVal2, V_MAX), V_MIN)

    oColor2 = QColor()
    oColor2.setHsv(nHue, int(round(dSat2 / 100.0 * 255)),
                   int(round(dVal2 / 100.0 * 255)))
    return oColor2


def _sampleStrip(nY, oScreen):
    """Снимает цвет горизонтальной полосы экрана на высоте nY: три точки по
    ширине, возвращает самое частое значение (r, g, b, count) или None."""
    aSamples = []
    for dX in PANEL_SAMPLE_X:
        nX = int(oScreen.geometry().width() * dX)
        oPix = oScreen.grabWindow(0, nX, nY, 1, 1)
        if oPix.isNull():
            continue
        oColor = oPix.toImage().pixelColor(0, 0)
        if not oColor.isValid():
            continue

        nRed, nGreen, nBlue = oColor.red(), oColor.green(), oColor.blue()
        if nRed > 245 and nGreen > 245 and nBlue > 245:
            continue

        aSamples.append((nRed, nGreen, nBlue))
    if not aSamples:
        return None

    dBestCount = 0
    aBest = None
    for nRgb in aSamples:
        dCount = aSamples.count(nRgb)
        if dCount > dBestCount:
            dBestCount = dCount
            aBest = nRgb
    if aBest is None:
        return None
    return aBest[0], aBest[1], aBest[2], dBestCount


def detectPanelColor():
    """Цвет фона панели: снимает полосы по верху и низу экрана (панель Xfce
    может быть внизу, как на Xubuntu без верхней панели) и берёт ту, что
    выглядит однотоннее — панель сплошная, а обои обычно пёстрые.
    При неудаче — цвет QPalette::Window."""
    fallback = QGuiApplication.palette().window().color()
    try:
        oScreen = QGuiApplication.primaryScreen()
        if oScreen is None:
            return fallback
        oGeometry = oScreen.geometry()
        if oGeometry.height() <= PANEL_SAMPLE_Y + 1:
            return fallback

        topStripe = _sampleStrip(PANEL_SAMPLE_Y, oScreen)
        bottomStripe = _sampleStrip(oGeometry.height() - PANEL_SAMPLE_Y - 1, oScreen)

        aBest = None
        dBestCount = 0
        for entry in (topStripe, bottomStripe):
            if entry is None:
                continue
            if entry[3] >= dBestCount:
                dBestCount = entry[3]
                aBest = entry[:3]
        if aBest is None:
            return fallback
        return QColor(aBest[0], aBest[1], aBest[2])
    except Exception:
        return fallback


class TrayMonitor(object):
    def __init__(self):
        self.cpuHistory = [0.0] * HISTORY
        self.ramHistory = [0.0] * HISTORY

        self.pCpuTray = QSystemTrayIcon()
        self.pRamTray = QSystemTrayIcon()

        menu = QMenu()
        actExit = menu.addAction("Выход")
        actExit.triggered.connect(QApplication.instance().quit)
        self.pCpuTray.setContextMenu(menu)
        self.pRamTray.setContextMenu(menu)

        psutil.cpu_percent(None)
        self.tick()

        self.pCpuTray.show()
        self.pRamTray.show()

        self.pTimer = QTimer()
        self.pTimer.timeout.connect(self.tick)
        self.pTimer.start(UPDATE_MS)

    def tick(self):
        self.cpuHistory.append(psutil.cpu_percent(None))
        self.ramHistory.append(psutil.virtual_memory().percent)
        del self.cpuHistory[:-HISTORY]
        del self.ramHistory[:-HISTORY]

        vmem = psutil.virtual_memory()
        self.pCpuTray.setToolTip("CPU: {0:4.1f}%".format(self.cpuHistory[-1]))
        self.pRamTray.setToolTip("RAM: {0:4.1f}% ({1:.1f} / {2:.1f} ГБ)".format(
            self.ramHistory[-1], gb(vmem.used), gb(vmem.total)))
        self.pCpuTray.setIcon(QIcon(self._renderIcon(self.cpuHistory, False)))
        self.pRamTray.setIcon(QIcon(self._renderIcon(self.ramHistory, True)))

    def _renderIcon(self, values, bFill):
        # Цвета пересчитываются при каждой перерисовке: так проект реагирует
        # на смену системной/трейной темы на лету, без перезапуска.
        oBg = detectPanelColor()          # цвет1 — фон трея
        oAccent = computeGraphColor(oBg)  # цвет2 — контрастный спокойный
        pixmap = QPixmap(ICON_SIZE, ICON_SIZE)
        pixmap.fill(oBg)
        painter = QPainter(pixmap)
        painter.setRenderHint(QPainter.Antialiasing)
        rect = QRectF(MARGIN, MARGIN, ICON_SIZE - 2 * MARGIN, ICON_SIZE - 2 * MARGIN)
        self._plot(painter, values, oAccent, rect, bFill)
        painter.end()
        return pixmap

    def _plot(self, painter, values, color, rect, bFill):
        n = len(values)
        path = QPainterPath()
        for i, value in enumerate(values):
            x = rect.left() + i * (rect.width() / (n - 1))
            y = rect.bottom() - value / 100.0 * rect.height()
            if i == 0:
                path.moveTo(x, y)
            else:
                path.lineTo(x, y)

        # Заливка под линией — только для RAM: линия остаётся непрозрачной.
        if bFill:
            areaPath = QPainterPath(path)
            areaPath.lineTo(rect.right(), rect.bottom())
            areaPath.lineTo(rect.left(), rect.bottom())
            areaPath.closeSubpath()
            oFill = QColor(color)
            oFill.setAlpha(FILL_ALPHA)
            painter.fillPath(areaPath, oFill)

        painter.setPen(QPen(color, 1))
        painter.drawPath(path)

        # Обводка графика: 1px, скруглённые углы, внутри границ (размер иконки не меняется).
        painter.setBrush(Qt.NoBrush)
        painter.setPen(QPen(color, 1))
        painter.drawRoundedRect(rect, OUTLINE_RADIUS, OUTLINE_RADIUS)


def main():
    app = QApplication(sys.argv)

    if not QSystemTrayIcon.isSystemTrayAvailable():
        sys.stderr.write("Ошибка: системный трей недоступен (QSystemTrayIcon.isSystemTrayAvailable() == False)\n")
        return 1

    app._trayMonitor = TrayMonitor()
    return app.exec_()


if __name__ == "__main__":
    sys.exit(main())