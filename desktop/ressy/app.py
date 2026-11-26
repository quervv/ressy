from __future__ import annotations

import argparse
import ctypes
import getpass
import logging
import signal
import sys
import threading

from . import APP_NAME, __version__
from .config import Settings
from .log import setup_logging
from .system_integration import SingleInstance, relaunch, wait_for_exit
from .i18n import language, saved_language, tr

log = logging.getLogger("ressy.app")

APP_ID = "top.ressy.desktop"


def _server_name() -> str:
    user = "".join(ch for ch in getpass.getuser() if ch.isalnum()) or "user"
    return f"ressy-desktop-{user}"


def _parse(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog="ressy", description=tr("Ressy, l'assistente vocale AI per desktop."))
    parser.add_argument("--background", action="store_true", help="avvio silenzioso (solo icona nell'area di notifica)")
    parser.add_argument("--debug", action="store_true", help="registri dettagliati")
    parser.add_argument("--server", action="store_true", help="avvia il server del tuo bot (self-host), senza finestre")
    parser.add_argument("--server-stop", action="store_true", help="ferma il server del bot")
    parser.add_argument("--uninstall", action="store_true", help="disinstalla Ressy")
    parser.add_argument("--quiet", action="store_true", help="con --uninstall: senza domande")
    parser.add_argument("--after", type=int, default=0, help=argparse.SUPPRESS)
    parser.add_argument("--version", action="version", version=f"Ressy {__version__}")
    return parser.parse_args(argv)


def _ask_running_instance_to_show() -> bool:
    from PySide6.QtNetwork import QLocalSocket

    socket = QLocalSocket()
    socket.connectToServer(_server_name())
    if not socket.waitForConnected(1500):
        return False
    socket.write(b"show\n")
    socket.waitForBytesWritten(1000)
    socket.disconnectFromServer()
    return True


def _install_excepthooks() -> None:
    def hook(exc_type, exc, tb) -> None:
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc, tb)
            return
        log.critical("uncaught exception", exc_info=(exc_type, exc, tb))

    def thread_hook(args: threading.ExceptHookArgs) -> None:
        log.critical("uncaught exception in %s", args.thread, exc_info=(args.exc_type, args.exc_value, args.exc_traceback))

    sys.excepthook = hook
    threading.excepthook = thread_hook


def main(argv: list[str] | None = None) -> int:
    args = _parse(sys.argv[1:] if argv is None else argv)
    if args.server:
        from .install import run_server

        return run_server()
    if args.server_stop:
        from .install import stop_server

        return 0 if stop_server() else 1
    if sys.platform == "win32":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(APP_ID)
        except (AttributeError, OSError):
            pass

    from PySide6.QtCore import QTimer
    from PySide6.QtNetwork import QLocalServer
    from PySide6.QtWidgets import QApplication, QMessageBox, QSystemTrayIcon

    app = QApplication(sys.argv[:1])
    app.setApplicationName(APP_NAME)
    app.setApplicationVersion(__version__)
    app.setOrganizationName(APP_NAME)
    app.setQuitOnLastWindowClosed(False)

    if args.uninstall:
        from .ui.uninstall import run_uninstall

        return run_uninstall(app, quiet=args.quiet)

    if args.after:
        wait_for_exit(args.after)
    instance = SingleInstance()
    if instance.already_running:
        _ask_running_instance_to_show()
        return 0

    setup_logging(logging.DEBUG if args.debug else logging.INFO)
    _install_excepthooks()
    log.info("Ressy %s starting", __version__)

    from .core.controller import Controller
    from .ui import logo, theme
    from .ui.bridge import UiBridge
    from .ui.hud import Hud
    from .ui.pair_dialog import PairDialog
    from .ui.settings_dialog import SettingsDialog
    from .ui.tray import Tray

    app.setWindowIcon(logo.app_icon())
    app.setFont(theme.font(14))
    app.setStyleSheet(theme.stylesheet())

    if not QSystemTrayIcon.isSystemTrayAvailable():
        QMessageBox.critical(None, "Ressy", tr("L'area di notifica di Windows non è disponibile: Ressy non può partire."))
        return 1

    settings = Settings.load()
    changed = settings.ensure_identity()
    if not saved_language():
        settings.use_language(language())
        changed = True
    if changed:
        settings.save()

    bridge = UiBridge()
    controller = Controller(settings, ui=bridge)
    hud = Hud(controller, bridge)
    windows: dict[str, object] = {}

    def open_pairing() -> None:
        dialog = windows.get("pair")
        if dialog is None:
            dialog = windows["pair"] = PairDialog(controller, bridge)
        dialog.open_and_request()

    def restart() -> None:
        if relaunch():
            log.info("restarting")
            app.quit()

    def open_settings(reason: str = "") -> None:
        dialog = windows.get("settings")
        if dialog is None:
            dialog = windows["settings"] = SettingsDialog(
                controller, bridge, open_pairing=open_pairing, restart=restart
            )
        dialog.open_with(reason)

    tray = Tray(controller, bridge, open_settings=open_settings, open_pairing=open_pairing, quit_app=app.quit)
    bridge.settingsRequested.connect(open_settings)

    def open_video_upload(request: dict) -> None:
        from .ui.video_dialog import VideoUploadDialog

        dlg = VideoUploadDialog(defaults=request.get("defaults") or {})
        if dlg.exec() == dlg.DialogCode.Accepted and dlg.result_payload:
            request["result"]["payload"] = dlg.result_payload
        event = request.get("event")
        if event is not None:
            event.set()

    bridge.videoUploadRequested.connect(open_video_upload)

    from .ui.update_dialog import UpdateChecker, UpdateDialog

    update_dialog = UpdateDialog(quit_app=app.quit)
    update_action = tray.add_update_action(lambda: update_dialog.offer(update_checker.release))
    update_checker = UpdateChecker(lambda: controller.settings.auto_update)
    offered: set[str] = set()

    def on_update(release) -> None:
        update_checker.release = release
        update_action.setText(tr("Aggiorna Ressy alla versione {version}…").format(version=release.version))
        update_action.setVisible(True)
        if release.version not in offered:
            offered.add(release.version)
            update_dialog.offer(release)

    update_checker.found.connect(on_update)

    server = QLocalServer()
    QLocalServer.removeServer(_server_name())
    if server.listen(_server_name()):
        def on_connection() -> None:
            socket = server.nextPendingConnection()
            if socket is not None:
                def on_read() -> None:
                    data = bytes(socket.readAll())
                    if data.strip() == b"quit":
                        log.info("asked to quit (installer or uninstaller)")
                        app.quit()
                    else:
                        open_settings("")

                socket.readyRead.connect(on_read)
                socket.disconnected.connect(socket.deleteLater)

        server.newConnection.connect(on_connection)
    else:
        log.warning("local server unavailable: %s", server.errorString())

    controller.start()
    app.aboutToQuit.connect(controller.shutdown)

    signal.signal(signal.SIGINT, lambda *_: app.quit())
    heartbeat = QTimer()
    heartbeat.start(500)
    heartbeat.timeout.connect(lambda: None)

    just_updated = bool(settings.last_version) and settings.last_version != __version__
    if settings.last_version != __version__:
        settings.last_version = __version__
        settings.save()

    if just_updated:
        tray.toast(tr("Ressy aggiornata"), tr("Ora hai la versione {version}.").format(version=__version__))
    if not settings.brain_ready:
        open_settings(
            tr("Benvenuto! Per iniziare scegli l'intelligenza di Ressy (Groq, Gemini, OpenRouter o Claude) e incolla la chiave. Poi tieni premuto {hotkey_name} e di' «Ressy, sveglia!».").format(hotkey_name=settings.hotkey_name)
        )
    elif not args.background:
        tray.toast(tr("Ressy è pronta"), tr("Tieni premuto {hotkey_name} e di' «Ressy, sveglia!»").format(hotkey_name=settings.hotkey_name))

    code = app.exec()
    log.info("Ressy stopped (%s)", code)
    del hud, tray, instance
    return code
