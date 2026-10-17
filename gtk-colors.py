#!/usr/bin/env python3
"""Передаёт цвет текста часов GTK в Qt-процесс по stdout (JSON Lines).

GTK работает отдельно от Qt; скрытые виджеты нужны только для CSS-стиля.
XSettings обновляет тему через X11, в том числе при запуске без D-Bus.
"""

import json
import os
from pathlib import Path
import xml.etree.ElementTree as ET

import gi

gi.require_version("Gtk", "3.0")
from gi.repository import GLib, Gtk


class ClockColors:
    def __init__(self):
        self.parent_pid = os.getppid()
        self.last_color = None
        self.config_mtime = None
        self.config = Path(os.environ.get("XDG_CONFIG_HOME", str(Path.home() / ".config"))) / "xfce4/xfconf/xfce-perchannel-xml/xfce4-panel.xml"

        self.window = Gtk.Window()
        self.window.set_name("XfcePanelWindow")
        self.window.get_style_context().add_class("xfce4-panel")
        self.plugin = Gtk.Box()
        self.plugin.get_style_context().add_class("clock")
        self.button = Gtk.ToggleButton()
        self.button.set_name("clock-button")
        self.button.set_relief(Gtk.ReliefStyle.NONE)
        self.clock = Gtk.Box()
        self.clock.set_name("clock-digital")
        self.label = Gtk.Label(label="12:34")
        self.window.add(self.plugin)
        self.plugin.add(self.button)
        self.button.add(self.clock)
        self.clock.add(self.label)
        self.settings = Gtk.Settings.get_default()
        self.settings.connect("notify::gtk-theme-name", self.theme_changed)
        self.settings.connect("notify::gtk-application-prefer-dark-theme", self.theme_changed)

    def theme_changed(self, *_args):
        GLib.idle_add(self.publish)

    def sync_panel_settings(self):
        """Учитывает имя плагина в CSS и отдельный тёмный режим панели XFCE."""
        try:
            mtime = self.config.stat().st_mtime_ns
            if mtime == self.config_mtime:
                return
            root = ET.parse(self.config).getroot()
            plugins = root.find("./property[@name='plugins']")
            if plugins is not None:
                for plugin in plugins:
                    if plugin.get("value") == "clock":
                        self.plugin.set_name("clock-" + plugin.get("name").split("-")[-1])
                        break
            dark = root.find("./property[@name='panels']/property[@name='dark-mode']")
            if dark is not None:
                self.settings.set_property("gtk-application-prefer-dark-theme", dark.get("value") == "true")
            self.config_mtime = mtime
        except (OSError, ET.ParseError):
            pass  # XFConf может в этот момент заменять свой XML-файл.

    def publish(self):
        self.sync_panel_settings()
        rgba = self.label.get_style_context().get_color(Gtk.StateFlags.NORMAL)
        color = [round(rgba.red * 255), round(rgba.green * 255), round(rgba.blue * 255)]
        if color != self.last_color:
            print(json.dumps({"foreground": color}), flush=True)
            self.last_color = color
        return False

    def poll(self):
        if os.getppid() != self.parent_pid:
            Gtk.main_quit()
            return False
        self.publish()
        return True


def main():
    colors = ClockColors()
    colors.publish()
    GLib.timeout_add_seconds(1, colors.poll)
    Gtk.main()


if __name__ == "__main__":
    main()
