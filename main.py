"""Portfolio Control System V3.1 — Entry Point."""

from __future__ import annotations

import logging
import sys
import os

# ---------------------------------------------------------------------------
# Ensure the project root is on sys.path so domain/application/etc imports work
# ---------------------------------------------------------------------------
_PROJECT_ROOT = os.path.dirname(os.path.abspath(__file__))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    )
    log = logging.getLogger("portfolio")

    # ── Database setup ─────────────────────────────────────────────────
    from infrastructure.database import create_db_engine, create_tables, make_session_factory
    from infrastructure.write_queue import WriteQueueManager

    engine = create_db_engine()
    create_tables(engine)
    session_factory = make_session_factory(engine)

    log.info("Database ready")

    # ── WriteQueueManager ──────────────────────────────────────────────
    wq = WriteQueueManager(session_factory)
    wq.start()
    log.info("WriteQueueManager started")

    # ── Qt Application ─────────────────────────────────────────────────
    from PySide6.QtWidgets import QApplication
    from PySide6.QtCore import Qt

    app = QApplication(sys.argv)
    app.setStyle("windowsvista")

    # Apply global stylesheet
    from ui.styles import GLOBAL_STYLESHEET
    app.setStyleSheet(GLOBAL_STYLESHEET)

    # ── Main Window ────────────────────────────────────────────────────
    from ui.main_window import MainWindow

    window = MainWindow(session_factory, wq)
    window.show()

    log.info("Application started")

    exit_code = app.exec()

    # ── Cleanup ────────────────────────────────────────────────────────
    wq.stop()
    engine.dispose()
    log.info("Application exited")
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
