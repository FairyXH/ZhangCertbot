from pathlib import Path

from src.zhangcertbot.ssh_manager import SSHManager, strip_ansi


def test_strip_ansi_removes_bracketed_paste_sequences():
    assert strip_ansi("\x1b[?2004hroot@server:~# \x1b[?2004l") == "root@server:~# "


def test_strip_ansi_removes_cursor_and_color_sequences():
    assert strip_ansi("\x1b[32mready\x1b[0m\x1b[2K") == "ready"


def test_remote_directory_is_created_from_absolute_path():
    assert SSHManager.remote_directory("/www/server/panel/vhost/ssl/site/fullchain.pem") == "/www/server/panel/vhost/ssl/site"
    assert SSHManager.remote_directory("fullchain.pem") == "."
