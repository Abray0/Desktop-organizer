"""Auto-detection of installed apps by walking the Start Menu shortcut trees."""
from __future__ import annotations

import os
from pathlib import Path

# Shortcuts that are noise rather than apps.
NOISE = (
    "uninstall", "uninstaller", "remove ", "readme", "read me", "release notes",
    "help", "documentation", "dokumentation", "docs", "manual", "license",
    "licence", "eula", "website", "web site", "homepage", "home page",
    "on the web", "support", "changelog", "report a", "feedback", "register",
    "activate", "repair", "modify ", "command prompt", "powershell", "setup",
    "install", "update ", "check for updates", "safe mode", "troubleshoot",
    "config editor", "faq", "redistributable", "program directory", "samples for",
    "tools for", "telemetry", "error and usage", "language preferences",
    "application verifier", "app cert kit", "upload center", "getting started",
    "what's new", "software development kit", "sdk", "tutorial", "example",
)

# Shortcuts whose whole name is generic shell noise.
NOISE_EXACT = {"run", "console", "explorer", "notepad"}

CATEGORIES: list[tuple[str, str, tuple[str, ...]]] = [
    ("Games", "⚔︎", (
        "overwolf",
        "steam", "epic games", "gog galaxy", "battle.net", "riot", "ubisoft",
        "ea app", "origin", "rockstar", "minecraft", "roblox", "albion",
        "league of legends", "valorant", "xbox", "game", "playnite", "itch",
    )),
    ("Creative", "✎︎", (
        "blackmagic", "raw player", "raw speed", "autosubs",
        "blender", "photoshop", "illustrator", "premiere", "after effects",
        "davinci", "resolve", "gimp", "krita", "inkscape", "audacity", "obs",
        "figma", "aseprite", "unity", "unreal", "godot", "substance", "maya",
        "cinema 4d", "capcut", "canva", "clip studio",
    )),
    ("Development", "⚙︎", (
        "sql server", "xampp", "bitnami", "virtualbox", "oracle",
        "gpuview", "performance analyzer", "performance recorder", "sqlite",
        "visual studio", "vs code", "vscode", "jetbrains", "pycharm", "intellij",
        "webstorm", "clion", "rider", "android studio", "git", "github",
        "docker", "postman", "sublime", "notepad++", "python", "anaconda",
        "miniconda", "node", "npm", "java", "jdk", "eclipse", "netbeans",
        "tomcat", "mysql", "postgres", "mongodb", "putty", "wsl", "cursor",
        "arduino", "ollama", "terminal",
    )),
    ("Internet", "◍", (
        "chrome", "firefox", "edge", "opera", "brave", "vivaldi", "tor browser",
        "discord", "slack", "telegram", "whatsapp", "zoom", "teams", "skype",
        "thunderbird", "outlook", "qbittorrent", "utorrent", "download manager",
        "filezilla", "signal",
    )),
    ("Media", "▶︎", (
        "vlc", "spotify", "media player", "mpc-hc", "potplayer", "itunes",
        "kodi", "plex", "netflix", "youtube", "winamp", "foobar", "musicbee",
        "photos", "movies",
    )),
    ("Office", "▤", (
        "wps ", "mindmanager", "spreadsheet compare", "database compare",
        "pdf",
        "word", "excel", "powerpoint", "access", "publisher", "onenote",
        "onedrive", "acrobat", "reader", "libreoffice", "openoffice", "notion",
        "obsidian", "evernote", "sumatra", "foxit", "calculator", "sticky notes",
    )),
    ("System", "❖", (
        "control panel", "task manager", "settings", "defender", "security",
        "cleaner", "ccleaner", "7-zip", "winrar", "explorer", "device manager",
        "disk", "driver", "nvidia", "amd ", "radeon", "intel", "backup",
        "antivirus", "firewall", "vpn", "cisco", "wireshark",
    )),
]

FALLBACK_GROUP = ("Other", "\u2726")

_START_MENUS = (
    Path(os.environ.get("APPDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
    Path(os.environ.get("PROGRAMDATA", "")) / "Microsoft/Windows/Start Menu/Programs",
)


def categorize(name: str, path: str) -> tuple[str, str]:
    """Pick a group for a shortcut from its name and its Start Menu folder."""
    haystack = f"{name} {path}".lower()
    for group, glyph, keywords in CATEGORIES:
        if any(word in haystack for word in keywords):
            return group, glyph
    return FALLBACK_GROUP


def _is_noise(name: str) -> bool:
    low = name.lower().strip()
    return low in NOISE_EXACT or any(word in low for word in NOISE)


def scan() -> list[dict]:
    """Return [{name, path, group, glyph}] for every real app shortcut found."""
    found: dict[str, dict] = {}
    for root in _START_MENUS:
        if not root.is_dir():
            continue
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [d for d in dirnames if d.lower() not in
                           ("startup", "administrative tools", "accessibility",
                            "windows administrative tools", "windows tools")]
            for filename in filenames:
                if not filename.lower().endswith((".lnk", ".url")):
                    continue
                name = filename.rsplit(".", 1)[0].strip()
                if _is_noise(name) or len(name) < 2:
                    continue
                full = str(Path(dirpath) / filename)
                key = name.lower()
                # Same app in both Start Menus: keep the first one seen.
                if key in found:
                    continue
                group, glyph = categorize(name, full)
                found[key] = {"name": name, "path": full, "group": group, "glyph": glyph}
    return sorted(found.values(), key=lambda item: (item["group"], item["name"].lower()))
