"""Main window — sidebar navigation and stacked content area."""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from typing import Optional

from PySide6.QtCore import Qt, QTimer
from PySide6.QtWidgets import (
    QFileDialog, QHBoxLayout, QLabel, QListWidget, QListWidgetItem,
    QMainWindow, QMenuBar, QMessageBox, QPushButton,
    QStackedWidget, QStatusBar, QTableView, QToolBar,
    QVBoxLayout, QWidget, QHeaderView, QGroupBox,
    QFormLayout, QComboBox, QTextBrowser,
)

from application.position_calculator import PositionCalculator, SaleResult
from application.tax_calculator import TaxCalculatorBR
from application.use_cases import (
    DetectCorporateActionUseCase,
    ImportB3CsvUseCase,
    RebuildAllUseCase,
    SaveTransactionUseCase,
)
from domain.entities import Transaction
from domain.enums import AssetClass, TradeType, TransactionType
from infrastructure.database import get_db_path
from infrastructure.price_provider import YahooFinanceProvider
from infrastructure.repositories import (
    CustodianRepository,
    InstitutionRepository,
    PositionRepository,
    SettingsRepository,
    TransactionRepository,
)
from ui.asset_ledger import AssetLedgerWidget
from ui.b3_reconciliation import B3ReconciliationWidget
from ui.corporate_action_dialog import CorporateActionDialog
from ui.custody_view import CustodyView
from ui.dashboard import DashboardWidget
from ui.styles import GLOBAL_STYLESHEET
from ui.table_models import PositionTableModel, TransactionTableModel
from ui.transaction_dialog import TransactionDialog
from reports.report_export import export_csv, export_pdf

log = logging.getLogger(__name__)

ZERO = Decimal("0")


# ═══════════════════════════════════════════════════════════════════════════
# Transactions Page
# ═══════════════════════════════════════════════════════════════════════════

class TransactionsPage(QWidget):
    """Full transaction list with add/edit/delete buttons."""

    def __init__(self, parent_window: "MainWindow"):
        super().__init__()
        self.main_win = parent_window
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # Header row
        header = QHBoxLayout()
        title = QLabel("Transações")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px;")
        header.addWidget(title)
        header.addStretch()

        btn_add = QPushButton("➕ Nova Transação")
        btn_add.setObjectName("primaryBtn")
        btn_add.clicked.connect(self._add_transaction)
        header.addWidget(btn_add)

        btn_edit = QPushButton("✏️ Editar")
        btn_edit.clicked.connect(self._edit_transaction)
        header.addWidget(btn_edit)

        btn_del = QPushButton("🗑️ Excluir")
        btn_del.setObjectName("dangerBtn")
        btn_del.clicked.connect(self._delete_transaction)
        header.addWidget(btn_del)

        layout.addLayout(header)

        # Table
        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.setSelectionMode(QTableView.SingleSelection)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self.table.setWordWrap(False)
        self._model = TransactionTableModel()
        self.table.setModel(self._model)
        self.table.doubleClicked.connect(self._on_table_double_click)
        layout.addWidget(self.table)

    def refresh(self) -> None:
        session = self.main_win.read_session()
        txs = TransactionRepository.get_all(session)
        self._model.set_data(txs)
        session.close()

    def _get_institutions(self) -> list[str]:
        session = self.main_win.read_session()
        names = InstitutionRepository.get_active_names(session)
        session.close()
        return names

    def _add_institution_callback(self, name: str) -> None:
        """Persist a new institution via WriteQueue."""
        wq = self.main_win.write_queue

        def do_add(session):
            InstitutionRepository.add(session, name)

        wq.submit_and_wait(do_add)

    def _add_transaction(self) -> None:
        institutions = self._get_institutions()
        dlg = TransactionDialog(
            self,
            institutions=institutions,
            add_institution_callback=self._add_institution_callback,
        )
        self._last_dialog = dlg
        dlg.saved.connect(self._on_saved)
        dlg.exec()

    def _edit_transaction(self) -> None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        tx = self._model.get_transaction(idx.row())
        if tx is None:
            return
        institutions = self._get_institutions()
        dlg = TransactionDialog(
            self,
            transaction=tx,
            institutions=institutions,
            add_institution_callback=self._add_institution_callback,
        )
        self._last_dialog = dlg
        dlg.saved.connect(self._on_saved)
        dlg.exec()

    def _delete_transaction(self) -> None:
        idx = self.table.currentIndex()
        if not idx.isValid():
            return
        tx = self._model.get_transaction(idx.row())
        if tx is None:
            return
        reply = QMessageBox.question(
            self, "Confirmar Exclusão",
            f"Excluir transação de {tx.ticker} em {tx.date}?",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply == QMessageBox.Yes:
            wq = self.main_win.write_queue

            def do_delete(session):
                TransactionRepository.delete(session, tx.id)

            wq.submit_and_wait(do_delete)
            self.main_win.refresh_all()

    def _on_table_double_click(self, index) -> None:
        """Handle double-click: if notes column, open tx; otherwise edit."""
        self._edit_transaction()

    def _on_saved(self, tx: Transaction) -> None:
        wq = self.main_win.write_queue
        strict = self.main_win.tax_strict_mode
        uc = SaveTransactionUseCase(tax_strict_mode=strict)

        log.info(
            "Saving transaction: ticker=%s type=%s qty=%s price=%s inst=%s",
            tx.ticker, tx.type.value, tx.quantity, tx.price, tx.institution,
        )

        try:

            def do_save(session):
                return uc.execute(session, tx)

            wq.submit_and_wait(do_save)
            log.info("Transaction saved successfully: %s", tx.ticker)

            # Check if rebuild is needed (date != today)
            if hasattr(self, '_last_dialog') and hasattr(self._last_dialog, '_needs_rebuild'):
                if self._last_dialog._needs_rebuild:
                    log.info("Triggering rebuild due to non-current date transaction")
                    rebuild_uc = RebuildAllUseCase()
                    def do_rebuild(session):
                        return rebuild_uc.execute(session)
                    wq.submit_and_wait(do_rebuild, timeout=120)

            self.main_win.refresh_all()
        except Exception as e:
            error_msg = str(e)
            # Extract root cause from chained exceptions
            if hasattr(e, '__cause__') and e.__cause__:
                error_msg = str(e.__cause__)
            log.error("Failed to save transaction: %s", error_msg)
            QMessageBox.critical(
                self, "Erro ao Salvar Transação", error_msg
            )


# ═══════════════════════════════════════════════════════════════════════════
# Positions Page — net open positions only
# ═══════════════════════════════════════════════════════════════════════════

class PositionsPage(QWidget):
    """Shows only net current open positions (not transaction list)."""

    def __init__(self, parent_window: "MainWindow"):
        super().__init__()
        self.main_win = parent_window
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        # Header with title + buttons
        header = QHBoxLayout()
        title = QLabel("Posições Abertas")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px;")
        header.addWidget(title)
        header.addStretch()

        self.detail_btn = QPushButton("📋 Detalhar Custódia")
        self.detail_btn.setStyleSheet(
            "QPushButton { padding: 6px 14px; font-size: 13px; }"
        )
        self.detail_btn.setCheckable(True)
        self.detail_btn.clicked.connect(self._toggle_detail)
        header.addWidget(self.detail_btn)

        self.refresh_btn = QPushButton("🔄 Atualizar Cotações")
        self.refresh_btn.setStyleSheet(
            "QPushButton { padding: 6px 14px; font-size: 13px; }"
        )
        self.refresh_btn.clicked.connect(self.refresh)
        header.addWidget(self.refresh_btn)

        btn_pdf = QPushButton("📄 PDF")
        btn_pdf.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_pdf.clicked.connect(self._export_pdf)
        header.addWidget(btn_pdf)

        btn_csv = QPushButton("📊 CSV")
        btn_csv.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_csv.clicked.connect(self._export_csv)
        header.addWidget(btn_csv)

        layout.addLayout(header)

        self.table = QTableView()
        self.table.setAlternatingRowColors(True)
        self.table.setSelectionBehavior(QTableView.SelectRows)
        self.table.horizontalHeader().setStretchLastSection(True)
        self.table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        self.table.verticalHeader().setDefaultSectionSize(26)
        self._model = PositionTableModel()
        self.table.setModel(self._model)
        layout.addWidget(self.table)

    def _toggle_detail(self) -> None:
        """Toggle between consolidated and detailed (per-institution) view."""
        is_detailed = self.detail_btn.isChecked()
        self._model.set_consolidated(not is_detailed)
        if is_detailed:
            self.detail_btn.setText("📊 Consolidar Posições")
        else:
            self.detail_btn.setText("📋 Detalhar Custódia")

    def refresh(self) -> None:
        session = self.main_win.read_session()
        # Only open positions (qty > 0)
        positions = PositionRepository.get_open(session)
        session.close()

        # Fetch market prices for all unique tickers
        prices: dict[str, Decimal] = {}
        provider = self.main_win._price_provider
        tickers = list({p.ticker for p in positions})
        for ticker in tickers:
            price = provider.get_last_price(ticker)
            if price is not None:
                prices[ticker] = price
                log.info("Market price for %s: %s", ticker, price)
            else:
                log.warning("Could not fetch price for %s", ticker)

        self._model.set_data(positions, prices)

    def _get_table_data(self) -> tuple[list[str], list[list[str]]]:
        model = self._model
        headers = list(model.headers)
        rows = []
        for r in range(len(model._data)):
            row = [model._display(model._data[r], c) for c in range(len(headers))]
            rows.append(row)
        return headers, rows

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", "posicoes_abertas.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        headers, rows = self._get_table_data()
        export_pdf(path, "Posições Abertas", headers, rows, landscape_mode=True)
        QMessageBox.information(self, "Exportado", f"PDF salvo em:\n{path}")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar CSV", "posicoes_abertas.csv", "CSV (*.csv)"
        )
        if not path:
            return
        headers, rows = self._get_table_data()
        export_csv(path, headers, rows)
        QMessageBox.information(self, "Exportado", f"CSV salvo em:\n{path}")


# ═══════════════════════════════════════════════════════════════════════════
# Tax Calculation Page
# ═══════════════════════════════════════════════════════════════════════════

class TaxCalculationPage(QWidget):
    """Apuração de resultado + IRRF calculation screen."""

    def __init__(self, parent_window: "MainWindow"):
        super().__init__()
        self.main_win = parent_window
        self._build_ui()

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        title = QLabel("Apuração de Resultado / IRRF")
        title.setStyleSheet("font-size: 18px; font-weight: bold; padding: 4px;")
        layout.addWidget(title)

        # Controls
        controls = QHBoxLayout()
        controls.addWidget(QLabel("Mês de referência:"))

        self.month_combo = QComboBox()
        now = datetime.now()
        for offset in range(12):
            m = now.month - offset
            y = now.year
            while m <= 0:
                m += 12
                y -= 1
            ref = f"{y:04d}-{m:02d}"
            self.month_combo.addItem(ref)
        controls.addWidget(self.month_combo)

        btn_calc = QPushButton("📊 Calcular")
        btn_calc.setObjectName("primaryBtn")
        btn_calc.clicked.connect(self._calculate)
        controls.addWidget(btn_calc)

        btn_rebuild = QPushButton("🔄 Reconstruir Tudo e Calcular")
        btn_rebuild.clicked.connect(self._rebuild_and_calculate)
        controls.addWidget(btn_rebuild)

        btn_pdf = QPushButton("📄 PDF")
        btn_pdf.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_pdf.clicked.connect(self._export_pdf)
        controls.addWidget(btn_pdf)

        btn_csv = QPushButton("📊 CSV")
        btn_csv.setStyleSheet("QPushButton { padding: 6px 12px; font-size: 13px; }")
        btn_csv.clicked.connect(self._export_csv)
        controls.addWidget(btn_csv)

        controls.addStretch()
        layout.addLayout(controls)

        # Result display
        self.result_display = QTextBrowser()
        self.result_display.setOpenExternalLinks(False)
        self.result_display.setStyleSheet(
            "font-family: 'Segoe UI', sans-serif; font-size: 12px;"
        )
        layout.addWidget(self.result_display)

    def _calculate(self) -> None:
        """Calculate tax for the selected month."""
        month_ref = self.month_combo.currentText()
        session = self.main_win.read_session()

        try:
            # Get all transactions and recompute sales for the month
            all_txs = TransactionRepository.get_all(session)
            calc = PositionCalculator()
            sale_results: list[SaleResult] = []
            for tx in all_txs:
                sr = calc.process(tx)
                if sr is not None:
                    sale_results.append(sr)

            # Filter sales for this month
            monthly_sales = [
                sr for sr in sale_results
                if sr.date.strftime("%Y-%m") == month_ref
            ]

            if not monthly_sales:
                self.result_display.setHtml(
                    f"<h3>Mês: {month_ref}</h3>"
                    "<p>Nenhuma venda realizada neste mês.</p>"
                )
                session.close()
                return

            # Calculate tax with accumulated losses
            tax_calc = TaxCalculatorBR()
            acc_losses: dict = defaultdict(lambda: ZERO)

            # Build accumulated losses from prior months
            prior_sales = [
                sr for sr in sale_results
                if sr.date.strftime("%Y-%m") < month_ref
            ]
            prior_by_month: dict[str, list] = defaultdict(list)
            for sr in prior_sales:
                prior_by_month[sr.date.strftime("%Y-%m")].append(sr)
            for m in sorted(prior_by_month.keys()):
                tax_calc.calculate_monthly_tax(prior_by_month[m], acc_losses, m)

            # Now calculate for the target month
            results = tax_calc.calculate_monthly_tax(
                monthly_sales, acc_losses, month_ref
            )

            # Build HTML report
            html = self._build_html(month_ref, monthly_sales, results)
            self.result_display.setHtml(html)

        except Exception as e:
            self.result_display.setHtml(f"<p style='color:red;'>Erro: {e}</p>")
        finally:
            session.close()

    def _rebuild_and_calculate(self) -> None:
        """Run rebuild_all first, then calculate."""
        wq = self.main_win.write_queue
        uc = RebuildAllUseCase()
        try:
            def do_rebuild(session):
                return uc.execute(session)

            wq.submit_and_wait(do_rebuild, timeout=120)
            self.main_win.refresh_all()
            self._calculate()
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    @staticmethod
    def _build_html(
        month_ref: str,
        sales: list[SaleResult],
        results: list,
    ) -> str:
        html = f"<h2>Apuração de Resultado — {month_ref}</h2>"

        # Summary of sales
        total_proceeds = sum(s.proceeds_brl for s in sales)
        total_gains = sum(s.gain_loss_brl for s in sales if s.gain_loss_brl > ZERO)
        total_losses = sum(s.gain_loss_brl for s in sales if s.gain_loss_brl < ZERO)
        net_result = sum(s.gain_loss_brl for s in sales)

        color = "#009600" if net_result >= ZERO else "#C80000"
        html += (
            "<div style='background:#F0F6FF; border:1px solid #B0D0FF; "
            "border-radius:6px; padding:12px; margin:8px 0;'>"
            f"<b>Volume de Vendas:</b> R$ {float(total_proceeds):,.2f}<br>"
            f"<b>Ganhos:</b> <span style='color:#009600;'>R$ {float(total_gains):,.2f}</span><br>"
            f"<b>Perdas:</b> <span style='color:#C80000;'>R$ {float(total_losses):,.2f}</span><br>"
            f"<b>Resultado Líquido:</b> <span style='color:{color};font-size:14px;'>"
            f"R$ {float(net_result):,.2f}</span>"
            "</div>"
        )

        # Detail per sale
        html += "<h3>Detalhamento das Vendas</h3>"
        html += (
            "<table border='1' cellpadding='4' cellspacing='0' "
            "style='border-collapse:collapse; width:100%;'>"
            "<tr style='background:#E0E0E0;'>"
            "<th>Ticker</th><th>Data</th><th>Tipo</th>"
            "<th>Qtd</th><th>Preço Venda</th><th>PM</th>"
            "<th>Resultado</th>"
            "</tr>"
        )
        for s in sales:
            gl_color = "#009600" if s.gain_loss_brl >= ZERO else "#C80000"
            trade = "DT" if s.trade_type == TradeType.DAY_TRADE else "ST"
            html += (
                f"<tr>"
                f"<td>{s.ticker}</td>"
                f"<td>{s.date.strftime('%d/%m/%Y')}</td>"
                f"<td>{trade}</td>"
                f"<td style='text-align:right;'>{int(s.sell_qty)}</td>"
                f"<td style='text-align:right;'>R$ {float(s.sell_price):,.2f}</td>"
                f"<td style='text-align:right;'>R$ {float(s.avg_cost):,.2f}</td>"
                f"<td style='text-align:right; color:{gl_color};'>"
                f"R$ {float(s.gain_loss_brl):,.2f}</td>"
                f"</tr>"
            )
        html += "</table>"

        # Tax results
        html += "<h3>Cálculo de IR / IRRF</h3>"
        html += (
            "<table border='1' cellpadding='4' cellspacing='0' "
            "style='border-collapse:collapse; width:100%;'>"
            "<tr style='background:#E0E0E0;'>"
            "<th>Classe</th><th>Tipo</th><th>Base Tributável</th>"
            "<th>Alíquota</th><th>IR Devido</th><th>IRRF (dedo-duro)</th>"
            "<th>DARF a Pagar</th><th>Prejuízo Acumulado</th>"
            "</tr>"
        )
        total_darf = ZERO
        for r in results:
            total_darf += r.darf_to_pay
            trade = "Day Trade" if r.trade_type == TradeType.DAY_TRADE else "Swing Trade"
            html += (
                f"<tr>"
                f"<td>{r.asset_class.label}</td>"
                f"<td>{trade}</td>"
                f"<td style='text-align:right;'>R$ {float(r.taxable_gain):,.2f}</td>"
                f"<td style='text-align:right;'>{float(r.tax_rate)*100:.0f}%</td>"
                f"<td style='text-align:right;'>R$ {float(r.tax_due):,.2f}</td>"
                f"<td style='text-align:right;'>R$ {float(r.irrf_withheld):,.2f}</td>"
                f"<td style='text-align:right; font-weight:bold;'>"
                f"R$ {float(r.darf_to_pay):,.2f}</td>"
                f"<td style='text-align:right;'>"
                f"R$ {float(r.accumulated_loss_after):,.2f}</td>"
                f"</tr>"
            )
        html += "</table>"

        if total_darf > ZERO:
            html += (
                f"<div style='background:#FFF3F3; border:1px solid #FFB0B0; "
                f"border-radius:6px; padding:12px; margin:8px 0;'>"
                f"<b>💰 DARF Total a Pagar:</b> "
                f"<span style='font-size:16px; color:#C80000;'>"
                f"R$ {float(total_darf):,.2f}</span>"
                f"</div>"
            )
        else:
            html += (
                "<div style='background:#F0FFF0; border:1px solid #B0FFB0; "
                "border-radius:6px; padding:12px; margin:8px 0;'>"
                "<b>✅ Sem DARF a pagar neste mês.</b>"
                "</div>"
            )

        return html

    def _get_tax_table_data(self) -> tuple[str, list[str], list[list[str]]]:
        """Extract sale data for export."""
        month_ref = self.month_combo.currentText()
        session = self.main_win.read_session()
        try:
            all_txs = TransactionRepository.get_all(session)
            calc = PositionCalculator()
            sale_results: list[SaleResult] = []
            for tx in all_txs:
                sr = calc.process(tx)
                if sr is not None:
                    sale_results.append(sr)
            monthly_sales = [
                sr for sr in sale_results
                if sr.date.strftime("%Y-%m") == month_ref
            ]
        finally:
            session.close()

        headers = ["Ticker", "Data", "Tipo", "Qtd", "Preço Venda", "PM", "Resultado"]
        rows = []
        for s in monthly_sales:
            trade = "DT" if s.trade_type == TradeType.DAY_TRADE else "ST"
            rows.append([
                s.ticker,
                s.date.strftime("%d/%m/%Y"),
                trade,
                str(int(s.sell_qty)),
                f"R$ {float(s.sell_price):,.2f}",
                f"R$ {float(s.avg_cost):,.2f}",
                f"R$ {float(s.gain_loss_brl):,.2f}",
            ])
        return month_ref, headers, rows

    def _export_pdf(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar PDF", "apuracao_resultado.pdf", "PDF (*.pdf)"
        )
        if not path:
            return
        month_ref, headers, rows = self._get_tax_table_data()
        export_pdf(path, f"Apuração de Resultado — {month_ref}", headers, rows)
        QMessageBox.information(self, "Exportado", f"PDF salvo em:\n{path}")

    def _export_csv(self) -> None:
        path, _ = QFileDialog.getSaveFileName(
            self, "Salvar CSV", "apuracao_resultado.csv", "CSV (*.csv)"
        )
        if not path:
            return
        _, headers, rows = self._get_tax_table_data()
        export_csv(path, headers, rows)
        QMessageBox.information(self, "Exportado", f"CSV salvo em:\n{path}")


# ═══════════════════════════════════════════════════════════════════════════
# MainWindow
# ═══════════════════════════════════════════════════════════════════════════

class MainWindow(QMainWindow):
    """Application main window with sidebar navigation."""

    NAV_ITEMS = [
        ("💼 Posições", 0),
        ("📊 Dashboard", 1),
        ("📝 Transações", 2),
        ("📒 Razão Auxiliar", 3),
        ("🏦 Custódia", 4),
        ("📥 Reconciliação B3", 5),
        ("💰 IR / DARF", 6),
    ]

    def __init__(self, session_factory, write_queue):
        super().__init__()
        self._session_factory = session_factory
        self.write_queue = write_queue
        self.tax_strict_mode = False
        self._price_provider = YahooFinanceProvider()

        self.setWindowTitle("Portfolio Control System 0.0.1")
        self.setMinimumSize(1100, 700)
        self.resize(1280, 800)

        self._build_ui()
        self._build_menu()
        self._build_statusbar()

        # Seed default institutions
        self._seed_institutions()

        # Initial data load
        QTimer.singleShot(200, self.refresh_all)

    def read_session(self):
        """Create a read-only session (caller must close)."""
        return self._session_factory()

    def _seed_institutions(self) -> None:
        """Seed default institutions on first run."""
        try:
            def do_seed(session):
                InstitutionRepository.seed_defaults(session)
            self.write_queue.submit_and_wait(do_seed)
        except Exception:
            log.exception("Failed to seed institutions")

    # ── UI building ────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        central = QWidget()
        self.setCentralWidget(central)
        main_layout = QHBoxLayout(central)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.setSpacing(0)

        # Sidebar
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar_layout = QVBoxLayout(sidebar)
        sidebar_layout.setContentsMargins(0, 10, 0, 0)

        app_label = QLabel("  💰 Portfólio V.1.0")
        app_label.setStyleSheet(
            "color: white; font-size: 15px; font-weight: bold; padding: 10px 10px 2px 10px;"
        )
        sidebar_layout.addWidget(app_label)

        author_label = QLabel("     by Marcus Aleks")
        author_label.setStyleSheet(
            "color: #cccccc; font-size: 11px; padding: 0px 10px 8px 10px;"
        )
        sidebar_layout.addWidget(author_label)

        self.nav_list = QListWidget()
        self.nav_list.setObjectName("navList")
        for label, _ in self.NAV_ITEMS:
            self.nav_list.addItem(label)
        self.nav_list.currentRowChanged.connect(self._on_nav_changed)
        sidebar_layout.addWidget(self.nav_list)
        sidebar_layout.addStretch()

        main_layout.addWidget(sidebar)

        # Content stack
        self.stack = QStackedWidget()

        self.dashboard = DashboardWidget()
        self.transactions_page = TransactionsPage(self)
        self.positions_page = PositionsPage(self)
        self.asset_ledger = AssetLedgerWidget()
        self.custody_view = CustodyView(parent_window=self)
        self.b3_reconciliation = B3ReconciliationWidget()
        self.tax_page = TaxCalculationPage(self)

        # Set up B3 import
        import_uc = ImportB3CsvUseCase()
        self.b3_reconciliation.set_parse_function(import_uc.parse_preview)
        self.b3_reconciliation.import_confirmed.connect(self._on_b3_import)

        # Price sync: Positions ↔ Custody
        self.positions_page._model.price_changed.connect(
            self._on_position_price_changed
        )
        self.custody_view.price_changed.connect(
            self._on_custody_price_changed
        )

        self.stack.addWidget(self.positions_page)     # 0
        self.stack.addWidget(self.dashboard)           # 1
        self.stack.addWidget(self.transactions_page)   # 2
        self.stack.addWidget(self.asset_ledger)        # 3
        self.stack.addWidget(self.custody_view)        # 4
        self.stack.addWidget(self.b3_reconciliation)   # 5
        self.stack.addWidget(self.tax_page)            # 6

        main_layout.addWidget(self.stack, 1)

        # Default selection: Posições
        self.nav_list.setCurrentRow(0)

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()

        # File menu
        file_menu = menu_bar.addMenu("&Arquivo")
        file_menu.addAction("Sair", self.close)

        # Tools menu
        tools_menu = menu_bar.addMenu("&Ferramentas")
        tools_menu.addAction("🔄 Reconstruir Tudo (rebuild_all)", self._rebuild_all)
        tools_menu.addAction(
            "🔍 Verificar Ações Corporativas", self._check_corporate_actions
        )
        tools_menu.addAction(
            "📈 Atualizar Cotações", self._refresh_market_prices
        )
        tools_menu.addSeparator()

        self._strict_action = tools_menu.addAction("Tax Strict Mode")
        self._strict_action.setCheckable(True)
        self._strict_action.setChecked(False)
        self._strict_action.toggled.connect(self._toggle_strict_mode)

        # Tax menu
        tax_menu = menu_bar.addMenu("&Impostos")
        tax_menu.addAction("💰 Apuração de Resultado / IRRF", self._goto_tax_page)
        tax_menu.addAction("📊 Calcular IR do Mês Atual", self._calc_current_month)

    def _build_statusbar(self) -> None:
        sb = self.statusBar()
        sb.showMessage(f"DB: {get_db_path()}")

    # ── navigation ─────────────────────────────────────────────────────

    def _on_nav_changed(self, row: int) -> None:
        self.stack.setCurrentIndex(row)

    def _goto_tax_page(self) -> None:
        self.nav_list.setCurrentRow(6)

    def _calc_current_month(self) -> None:
        self.nav_list.setCurrentRow(6)
        self.tax_page._calculate()

    # ── data refresh ───────────────────────────────────────────────────

    def refresh_all(self) -> None:
        """Reload all views from the database."""
        try:
            session = self.read_session()

            # Transactions
            txs = TransactionRepository.get_all(session)
            self.transactions_page._model.set_data(txs)

            # Positions — delegate to page (fetches market prices)
            positions = PositionRepository.get_open(session)
            self.positions_page.refresh()

            # Dashboard — pass prices from positions model
            prices = self.positions_page._model._prices
            self.dashboard.refresh(positions, prices=prices)

            # Asset ledger
            self.asset_ledger.set_transactions(txs)

            # Custody — built from open positions
            custodians = CustodianRepository.get_all(session)
            # Build avg_prices lookup from positions
            avg_prices = {p.ticker: p.avg_price for p in positions if p.avg_price > ZERO}
            self.custody_view.refresh(custodians, avg_prices=avg_prices)

            session.close()
        except Exception:
            log.exception("Error refreshing data")

    # ── price sync ──────────────────────────────────────────────────────

    def _on_position_price_changed(self, ticker: str, new_price) -> None:
        """Sync a price edit in Posições Abertas to Custódia."""
        from decimal import Decimal as D
        price = D(str(new_price))
        # Update custody view's internal prices and rebuild
        self.custody_view._prices[ticker] = price
        self.custody_view._rebuild_tree()
        log.info("Price sync Positions→Custody for %s: %s", ticker, price)

    def _on_custody_price_changed(self, ticker: str, new_price) -> None:
        """Sync a price edit in Custódia to Posições Abertas."""
        from decimal import Decimal as D
        price = D(str(new_price))
        model = self.positions_page._model
        model._prices[ticker] = price
        # Refresh the entire positions table
        top_left = model.index(0, 0)
        bottom_right = model.index(model.rowCount() - 1, model.columnCount() - 1)
        model.dataChanged.emit(top_left, bottom_right)
        log.info("Price sync Custody→Positions for %s: %s", ticker, price)

    # ── actions ────────────────────────────────────────────────────────

    def _rebuild_all(self) -> None:
        reply = QMessageBox.question(
            self, "Reconstruir",
            "Apagar o cache de posições e recalcular tudo a partir das "
            "transações?\n\nIsso pode demorar para grandes volumes.",
            QMessageBox.Yes | QMessageBox.No,
        )
        if reply != QMessageBox.Yes:
            return

        uc = RebuildAllUseCase()
        try:
            def do_rebuild(session):
                return uc.execute(session)

            result = self.write_queue.submit_and_wait(do_rebuild, timeout=120)
            self.refresh_all()
            QMessageBox.information(
                self, "Reconstrução Completa",
                f"✅ Processadas:\n"
                f"• {result['transactions']} transações\n"
                f"• {result['positions']} posições\n"
                f"• {result['tax_results']} resultados fiscais",
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))

    def _check_corporate_actions(self) -> None:
        session = self.read_session()
        uc = DetectCorporateActionUseCase(self._price_provider)
        warnings = uc.check_all(session)
        session.close()

        if warnings:
            dlg = CorporateActionDialog(warnings, self)
            dlg.exec()
        else:
            QMessageBox.information(
                self, "Ações Corporativas",
                "Nenhuma variação anormal de preço detectada.",
            )

    def _refresh_market_prices(self) -> None:
        """Navigate to Positions page and refresh market prices."""
        self.nav_list.setCurrentRow(0)  # Posições
        self.positions_page.refresh()
        self.statusBar().showMessage("Cotações atualizadas!", 5000)

    def _toggle_strict_mode(self, checked: bool) -> None:
        self.tax_strict_mode = checked
        mode = "ATIVADO" if checked else "DESATIVADO"
        self.statusBar().showMessage(
            f"Tax Strict Mode {mode} | DB: {get_db_path()}"
        )

    def _on_b3_import(self, transactions: list[Transaction]) -> None:
        import_uc = ImportB3CsvUseCase()
        try:
            def do_import(session):
                return import_uc.persist(session, transactions)

            count = self.write_queue.submit_and_wait(do_import)

            # Rebuild positions after import
            uc = RebuildAllUseCase()

            def do_rebuild(session):
                return uc.execute(session)

            self.write_queue.submit_and_wait(do_rebuild, timeout=120)
            self.refresh_all()

            QMessageBox.information(
                self, "Importação Concluída",
                f"✅ {count} transação(ões) importada(s) e posições recalculadas.",
            )
        except Exception as e:
            QMessageBox.critical(self, "Erro", str(e))
