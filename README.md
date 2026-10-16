# Tray Monitor: индикаторы CPU/RAM в системном трее (Astra Linux 1.8, Fly)

Два отдельных индикатора загрузки в системном трее панели Fly — по иконке на CPU
и на RAM (живой мини-график).

- Скрипт: PyQt5 + psutil, иконка 64×64 (в трее масштабируется до ~22×22).
- **Две отдельные иконки**: CPU и RAM докнутся в трей как два независимых
  элемента (по ячейке на каждую).
- **Фон иконки — цвет панели**: снимается пикселем с реальной панели
  (`QScreen::grabWindow` по верхней полосе экрана, берётся наиболее частый цвет);
  запасной вариант — системная палитра `QPalette::Window`.
- **Цвет графика — инверсный** к фону: `QColor(255 − r, 255 − g, 255 − b)` —
  максимальный контраст на любом фоне панели (для #4D7593 → график #B28A6C).
- История: 32 точки, заливка под линией (alpha 90), линия — `QPen(color, 3)`.
- Обновление раз в секунду.
- Подсказки: CPU-иконка — `CPU: 12.3%`; RAM-иконка — `RAM: 45.6% (5.2 / 11.4 ГБ)`.
- Контекстное меню «Выход» на каждой иконке.
- Если системный трей недоступен — сообщение в stderr и выход с кодом 1.

---

## Установка

### 1. Проверка/установка зависимостей

Ставить только через apt из штатных репозиториев Astra (без pip/Flatpak/AppImage/скачанных .deb):

```bash
dpkg -s python3-pyqt5 python3-psutil | grep -E '^(Package|Status|Version)'
# если чего-то нет:
sudo apt-get install -y python3-pyqt5 python3-psutil
```

Проверено на: `python3-pyqt5 5.15.9+dfsg-1+b9`, `python3-psutil 5.9.4-1+ci1`.

### 2. Скрипт и установка

Приложение живёт в каталоге проекта (никаких копий в `~`). Установка и
обслуживание — одним скриптом `install.sh` (должен запускаться из каталога
проекта `trayinfo`):

```bash
cd ~/projects/trayinfo

./install.sh            # или: ./install.sh install
                        # - проверяет зависимости (ставит через apt при необходимости)
                        # - создаёт автозапуск ~/.config/autostart/tray-monitor.desktop
./install.sh start      # запустить индикатор из каталога проекта
./install.sh restart    # перезапустить
./install.sh stop       # остановить
./install.sh status     # состояние (процесс, скрипт, автозапуск)
./install.sh uninstall  # остановить и удалить автозапуск
```

Команды `install.sh`:
| Команда | Действие |
|---|---|
| (без аргументов) / `install` | зависимости + автозапуск |
| `start` / `restart` | запуск/перезапуск из каталога проекта (detect DISPLAY/XAUTHORITY/DBUS, `QT_QPA_PLATFORMTHEME=` и `setsid nohup`) |
| `stop` | остановка |
| `status` | состояние |
| `uninstall` | остановка + удаление автозапуска |

### 3. Автозапуск

Создаётся `install.sh`, содержимое `~/.config/autostart/tray-monitor.desktop`:

```ini
[Desktop Entry]
Version=1.0
Type=Application
Name=Tray Monitor
Comment=CPU and RAM usage monitor in the system tray
Exec=/home/mik/projects/trayinfo/install.sh start
Terminal=false
X-GNOME-Autostart-enabled=true
```

> **Важно:** автозапуск идёт через `install.sh start` — именно он выставляет
> пустую `QT_QPA_PLATFORMTHEME=` (см. «Подводные камни», пункт 1) и запускает
> скрипт из каталога проекта.

### 4. Ручной запуск (как это делает install.sh start)

```bash
DISPLAY=:0 XAUTHORITY=/home/mik/.Xauthority \
DBUS_SESSION_BUS_ADDRESS="unix:path=/run/user/1000z0_0_0x0_0x0/bus" \
QT_QPA_PLATFORMTHEME= \
setsid nohup python3 ~/projects/trayinfo/tray-monitor.py \
  >/tmp/tray-monitor.log 2>&1 < /dev/null &

# проверка
pgrep -af tray-monitor.py          # процесс жив
cat /tmp/tray-monitor.log          # пусто = ошибок нет
```

Внутри графической сессии достаточно `QT_QPA_PLATFORMTHEME= python3 ~/projects/trayinfo/tray-monitor.py &`
(остальные переменные сессия уже экспортирует); `setsid nohup` нужен только при
запуске из-под SSH/терминала, чтобы процесс пережил закрытие сессии.
Адрес сессионной шины узнаётся: `echo $DBUS_SESSION_BUS_ADDRESS` (или `ps -e | grep dbus-daemon`).

---

## Управление

| Действие | Команда |
|---|---|
| Остановить | `~/projects/trayinfo/install.sh stop` |
| Запустить | `~/projects/trayinfo/install.sh start` |
| Перезапустить | `~/projects/trayinfo/install.sh restart` |
| Состояние | `~/projects/trayinfo/install.sh status` |
| Убрать из автозапуска | `~/projects/trayinfo/install.sh uninstall` |
| Лог | `cat /tmp/tray-monitor.log` |

> Примечание: `pkill -f tray-monitor.py`, набранный в командной строке оболочки,
> совпадает сам с собой (паттерн есть в собственной command line bash). Безопаснее:
> `for P in $(pgrep -f 'tray-m''onitor.py'); do kill $P; done` или `pkill -f '/home/mik/tray-monitor.py'`.

---

## Проверка после запуска

```bash
# окно иконки 22×22 должно быть докнуто в трей (у панели):
xwininfo -root -tree | grep -E 'tray-monitor.py'

# пиксельный контроль: в иконке должны появиться тёмно-зелёный (#004C00)
# и синий (#1E4180) цвета графиков:
import -window root -crop 300x40+1620+0 /tmp/strip.png
convert /tmp/strip.png -format %c histogram:info:- | sort -rn | head

# регистрация в трее идёт по XEmbed: иконка приходит как вложенное окно
# 22×22 в ячейки контейнера трея панели (как у nm-applet, xkb, max).
```

---

## Подводные камни (что было выяснено отладкой)

### 1. `QT_QPA_PLATFORMTHEME=fly` перехватывает трей и «глотает» иконку

На Astra Linux 1.8 в сессии Fly глобально выставлено `QT_QPA_PLATFORMTHEME=fly`.
Плагин `flyqt5platformtheme` (`/usr/lib/x86_64-linux-gnu/qt5/plugins/platformthemes/libfly.so`)
реализует `createPlatformSystemTrayIcon()` (свой SNI через QStatusNotifierItemAdaptor),
**но** на панельном трее Fly его SNI-регистрация молча не срабатывает:

- приложение подключается к сессионной шине, но не вызывает
  `RegisterStatusNotifierItem` (проверено dbus-monitor);
- имя `org.kde.StatusNotifierItem-<pid>-1` не регистрируется;
- у владельца трея (`org.kde.StatusNotifierWatcher`, сам fly-wm) список
  `RegisteredStatusNotifierItems` остаётся пустым.

Результат: `QSystemTrayIcon.isSystemTrayAvailable()` возвращает `true`
(вотчер на шине есть), иконка «молча» не появляется, XEmbed-запасной вариант не используется.

**Решение:** запускать с пустой переменной `QT_QPA_PLATFORMTHEME=`
(пустая строка = default QPlatformTheme, без перехвата трея), тогда Qt идёт
по классическому XEmbed-пути, который панель Fly обслуживает
(так докнуты nm-applet, xkb, max).

### 2. Сборка мусора Python убивает иконку сразу после старта

`QSystemTrayIcon` не имеет Qt-родителя. Если инстанс-обёртка хранится только
в локальной переменной и не переживает `main()`:

```python
TrayMonitor()          # объект сразу уничтожается GC Python
return app.exec_()
```

— иконка успевает «докнуться» и тут же пропадает (трей создаёт сокет, затем
Unmap+Destroy; окно возвращается в root unmapped). **Решение:** удерживать ссылку:

```python
app._trayMonitor = TrayMonitor()
return app.exec_()
```

### 3. Порядок инициализации имеет значение (симптоматика)

Стабильно рабочий порядок вызовов (именно он в `tray-monitor.py`):

1. `QSystemTrayIcon()` — создание
2. первый `tick()` (установить tooltip + иконку ДО показа)
3. `setContextMenu(menu)`
4. `show()`
5. создание/запуск `QTimer` ПОСЛЕ `show()`

Запуск `QTimer.start()` до `show()` в сочетании с пунктами 2–3 давал
нестабильный док (воспроизводилось многократными пробами: док либо не происходил,
либо отваливался через несколько секунд).

### 4. Инструменты для отладки

При диагностике использовались:

- `xwininfo -root -tree` — дерево окон, поиск докнутой 22×22 иконки и сокета;
- `xev -id <окно_трея>` — события CreateNotify/MapNotify/UnmapNotify сокета трея;
- `xdotool search --name` / `getwindowgeometry` — геометрия окон иконок;
- `dbus-monitor --session "member=RegisterStatusNotifierItem"` — SNI-трафик;
- `busctl --user list` + `qdbus --session org.freedesktop.StatusNotifierWatcher /StatusNotifierWatcher org.freedesktop.DBus.Properties.GetAll` — состояние вотчера;
- `strace -f -e trace=write,writev -s 200000` — интернирование атомов
  `_NET_SYSTEM_TRAY_*` (XConnect/atom intern уходит через writev!);
- `import -window root` (ImageMagick) + histogram — пиксельный контроль иконки;
- владелец селекшена: `_NET_SYSTEM_TRAY_S0` (при падении/перезапуске панели
  владелец меняется, старые id окон трея устаревают).

---

## Структура репозитория

```
trayinfo/
├── README.md          <- этот файл
├── install.sh         <- установка/запуск/остановка/автозапуск (apt, автозапуск, env)
└── tray-monitor.py    <- рабочий скрипт индикатора (запускается из этого каталога)
```

Скрипт работает прямо из каталога проекта (`/home/mik/projects/trayinfo/`),
отдельная копия в `~/` не требуется (старая удалена).
