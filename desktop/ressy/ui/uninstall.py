from __future__ import annotations

import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication, QCheckBox, QMessageBox

from .. import install
from . import logo, theme
from ..i18n import tr


def run_uninstall(app: QApplication, *, quiet: bool = False) -> int:
    app.setWindowIcon(logo.app_icon())
    app.setStyleSheet(theme.stylesheet())
    folder = install.installed_dir() or Path(sys.executable).resolve().parent
    remove_data = False
    if not quiet:
        box = QMessageBox()
        box.setWindowTitle(tr("Disinstalla Ressy"))
        box.setIcon(QMessageBox.Icon.Question)
        box.setText(tr("Vuoi disinstallare Ressy da questo PC?"))
        box.setInformativeText(
            tr("Tolgo l'app, i collegamenti, l'avvio con Windows e, se c'è, il server del tuo bot.")
        )
        keep = QCheckBox(tr("Elimina anche impostazioni, chiavi e registri"))
        box.setCheckBox(keep)
        box.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No)
        box.button(QMessageBox.StandardButton.Yes).setText(tr("Disinstalla"))
        box.button(QMessageBox.StandardButton.No).setText(tr("Annulla"))
        if box.exec() != QMessageBox.StandardButton.Yes:
            return 1
        remove_data = keep.isChecked()
    install.ask_app_to_quit()
    install.uninstall(folder, remove_data)
    if not quiet:
        QMessageBox.information(None, "Ressy", tr("Ressy è stata disinstallata. Grazie per averla provata!"))
    return 0
