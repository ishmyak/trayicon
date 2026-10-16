#!/usr/bin/env bash
# ============================================================================
# Tray Monitor (CPU/RAM в трее Fly, Astra Linux 1.8)
# Установка, запуск и обслуживание индикатора из каталога проекта trayinfo.
#
# Использование:
#   ./install.sh            — установка (зависимости + автозапуск), по умолчанию
#   ./install.sh install    — то же самое
#   ./install.sh start      — запустить индикатор (из каталога проекта)
#   ./install.sh stop       — остановить индикатор
#   ./install.sh restart    — перезапустить
#   ./install.sh uninstall  — остановить и удалить автозапуск
#   ./install.sh status     — текущее состояние
# ============================================================================

set -euo pipefail

PROG_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
TRAY_SCRIPT="$PROG_DIR/tray-monitor.py"
AUTOSTART_DIR="$HOME/.config/autostart"
DESKTOP_FILE="$AUTOSTART_DIR/tray-monitor.desktop"
LOG_FILE="/tmp/tray-monitor.log"
# Паттерн разбит кавычками, чтобы pgrep/pkill не «убивали» саму командную строку,
# в которой встречается это имя.
PATTERN='tray-monitor''.py'

die() {
    echo "Ошибка: $*" >&2
    exit 1
}

require_script() {
    [[ -f "$TRAY_SCRIPT" ]] || \
        die "не найден $TRAY_SCRIPT — запускайте install.sh из каталога проекта trayinfo"
}

# Переменные графической сессии, если скрипт запущен из SSH/терминала.
detect_display_env() {
    [[ -n "${DISPLAY:-}" ]] || export DISPLAY=":0"
    [[ -n "${XAUTHORITY:-}" || ! -f "$HOME/.Xauthority" ]] || export XAUTHORITY="$HOME/.Xauthority"
    if [[ -z "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
        local wm_pid bus=""
        # Кандидаты: fly-wm (Astra), xfwm4/xfce4-session (Xubuntu/Xfce) и др. DE.
        # Берём шину из окружения первого подходящего процесса.
        for wm in fly-wm xfwm4 xfce4-session mate-session gnome-session lxsession; do
            wm_pid="$(pgrep -u "$USER" -x "$wm" | head -1 || true)"
            [[ -n "$wm_pid" && -r "/proc/$wm_pid/environ" ]] || continue
            bus="$(tr '\0' '\n' < "/proc/$wm_pid/environ" 2>/dev/null \
                | sed -n 's/^DBUS_SESSION_BUS_ADDRESS=//p' | head -1 || true)"
            [[ -n "$bus" ]] && break
        done
        # Портативный фолбэк: шина по XDG_RUNTIME_DIR (принято во всех современных сессиях).
        if [[ -z "$bus" && -n "${XDG_RUNTIME_DIR:-}" && -S "$XDG_RUNTIME_DIR/bus" ]]; then
            bus="unix:path=$XDG_RUNTIME_DIR/bus"
        fi
        if [[ -n "$bus" ]]; then
            export DBUS_SESSION_BUS_ADDRESS="$bus"
            echo "Сессионная шина: $DBUS_SESSION_BUS_ADDRESS"
        fi
    fi
}

monitor_pids() {
    pgrep -f "$PATTERN" 2>/dev/null || true
}

stop_monitor() {
    local pids
    pids="$(monitor_pids)"
    if [[ -z "$pids" ]]; then
        echo "Индикатор не запущен."
        return 0
    fi
    for pid in $pids; do
        [[ "$pid" == "$$" || "$pid" == "$PPID" ]] && continue
        kill "$pid" 2>/dev/null || true
    done
    sleep 1
    echo "Индикатор остановлен."
}

start_monitor() {
    require_script
    detect_display_env
    stop_monitor

    local env_prefix=(DISPLAY="$DISPLAY" XAUTHORITY="$XAUTHORITY" QT_QPA_PLATFORMTHEME=)
    if [[ -n "${DBUS_SESSION_BUS_ADDRESS:-}" ]]; then
        env_prefix+=(DBUS_SESSION_BUS_ADDRESS="$DBUS_SESSION_BUS_ADDRESS")
    fi

    # QT_QPA_PLATFORMTHEME= (пусто) обязательно: тема fly перехватывает трей и иконка не появляется.
    setsid nohup env "${env_prefix[@]}" python3 "$TRAY_SCRIPT" >"$LOG_FILE" 2>&1 < /dev/null &
    disown || true
    sleep 2

    if monitor_pids >/dev/null; then
        echo "Индикатор запущен: $TRAY_SCRIPT"
        echo "Лог: $LOG_FILE — должен быть пустым (нет ошибок)"
    else
        die "процесс не запустился; см. $LOG_FILE"
    fi
}

install_app() {
    require_script

    local missing=() pkg
    for pkg in python3-pyqt5 python3-psutil; do
        if ! dpkg -s "$pkg" >/dev/null 2>&1; then
            missing+=("$pkg")
        fi
    done
    if ((${#missing[@]})); then
        echo "Устанавливаются пакеты: ${missing[*]}"
        sudo -E apt-get install -y "${missing[@]}"
    else
        echo "Зависимости уже установлены: python3-pyqt5, python3-psutil"
    fi

    mkdir -p "$AUTOSTART_DIR"
    cat > "$DESKTOP_FILE" <<EOF
[Desktop Entry]
Version=1.0
Type=Application
Name=Tray Monitor
Comment=CPU and RAM usage monitor in the system tray
Exec=$PROG_DIR/install.sh start
Terminal=false
X-GNOME-Autostart-enabled=true
EOF
    echo "Автозапуск создан: $DESKTOP_FILE"
    echo "Путь к скрипту в автозапуске: $TRAY_SCRIPT"
}

uninstall_app() {
    stop_monitor
    rm -f "$DESKTOP_FILE"
    echo "Автозапуск удалён: $DESKTOP_FILE"
}

status_app() {
    require_script
    local pids
    pids="$(monitor_pids)"
    if [[ -n "$pids" ]]; then
        echo "Индикатор работает (PID: $(echo "$pids" | tr '\n' ' '))"
        echo "Скрипт: $TRAY_SCRIPT"
        echo "Автозапуск: $([ -f "$DESKTOP_FILE" ] && echo 'установлен' || echo 'не установлен')"
    else
        echo "Индикатор не запущен."
        echo "Скрипт: $TRAY_SCRIPT"
        echo "Автозапуск: $([ -f "$DESKTOP_FILE" ] && echo 'установлен' || echo 'не установлен')"
    fi
}

case "${1:-install}" in
    install)   install_app ;;
    start)     start_monitor ;;
    stop)      stop_monitor ;;
    restart)   start_monitor ;;
    uninstall) uninstall_app ;;
    status)    status_app ;;
    *) die "неизвестная команда: $1 (ожидалось: install|start|stop|restart|uninstall|status)" ;;
esac

exit 0