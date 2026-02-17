"""Transaction create/edit dialog with institution dropdown."""

from __future__ import annotations

from datetime import date
from decimal import Decimal, InvalidOperation

from PySide6.QtCore import Qt, Signal
from PySide6.QtWidgets import (
    QComboBox, QDateEdit, QDialog, QDialogButtonBox, QFormLayout,
    QGroupBox, QHBoxLayout, QLabel, QLineEdit, QMessageBox,
    QPushButton, QTextEdit, QVBoxLayout, QInputDialog,
)

from domain.entities import Transaction
from domain.enums import AssetClass, Currency, TradeType, TransactionType


class TransactionDialog(QDialog):
    """Modal dialog for creating or editing a transaction."""

    saved = Signal(object)  # emits Transaction

    def __init__(
        self,
        parent=None,
        transaction: Transaction | None = None,
        institutions: list[str] | None = None,
        add_institution_callback=None,
    ):
        super().__init__(parent)
        self._tx = transaction
        self._institutions = institutions or []
        self._add_institution_callback = add_institution_callback
        self.setWindowTitle(
            "Editar Transação" if transaction else "Nova Transação"
        )
        self.setMinimumWidth(520)
        self._build_ui()
        if transaction:
            self._populate(transaction)

    # ── UI ─────────────────────────────────────────────────────────────

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        form = QFormLayout()
        form.setLabelAlignment(Qt.AlignRight)

        # Ticker (auto uppercase)
        self.ticker_edit = QLineEdit()
        self.ticker_edit.setPlaceholderText("Ex: PETR4")
        self.ticker_edit.setMaxLength(20)
        self.ticker_edit.textChanged.connect(self._force_upper)
        form.addRow("Ticker:", self.ticker_edit)

        # Asset class
        self.asset_class_combo = QComboBox()
        for ac in AssetClass:
            self.asset_class_combo.addItem(ac.label, ac.value)
        form.addRow("Classe:", self.asset_class_combo)

        # Type — with labels
        self.type_combo = QComboBox()
        for tt in TransactionType:
            self.type_combo.addItem(tt.label, tt.value)
        form.addRow("Tipo:", self.type_combo)

        # Trade type
        self.trade_type_combo = QComboBox()
        for tt in TradeType:
            label = "Day Trade" if tt == TradeType.DAY_TRADE else "Swing Trade"
            self.trade_type_combo.addItem(label, tt.value)
        form.addRow("Operação:", self.trade_type_combo)

        # Date
        self.date_edit = QDateEdit()
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDate(date.today())
        self.date_edit.setDisplayFormat("dd/MM/yyyy")
        form.addRow("Data:", self.date_edit)

        # Quantity
        self.qty_edit = QLineEdit()
        self.qty_edit.setPlaceholderText("0")
        form.addRow("Quantidade:", self.qty_edit)

        # Price
        self.price_edit = QLineEdit()
        self.price_edit.setPlaceholderText("0.00")
        form.addRow("Preço Unitário:", self.price_edit)

        # Currency
        self.currency_combo = QComboBox()
        for c in Currency:
            self.currency_combo.addItem(f"{c.symbol} ({c.value})", c.value)
        self.currency_combo.currentIndexChanged.connect(self._on_currency_changed)
        form.addRow("Moeda:", self.currency_combo)

        # FX Rate
        self.fx_edit = QLineEdit("1.0")
        self.fx_label = QLabel("Taxa FX (PTAX):")
        form.addRow(self.fx_label, self.fx_edit)
        self.fx_edit.setEnabled(False)

        # Institution — dropdown + add button
        inst_row = QHBoxLayout()
        self.inst_combo = QComboBox()
        self.inst_combo.setMinimumWidth(250)
        for inst in self._institutions:
            self.inst_combo.addItem(inst)
        inst_row.addWidget(self.inst_combo, 1)

        btn_add_inst = QPushButton("➕")
        btn_add_inst.setToolTip("Cadastrar nova instituição")
        btn_add_inst.setFixedWidth(40)
        btn_add_inst.clicked.connect(self._add_institution)
        inst_row.addWidget(btn_add_inst)

        form.addRow("Instituição:", inst_row)

        # Notes
        self.notes_edit = QTextEdit()
        self.notes_edit.setMaximumHeight(60)
        self.notes_edit.setPlaceholderText("Observações...")
        form.addRow("Notas:", self.notes_edit)

        group = QGroupBox("Dados da Transação")
        group.setLayout(form)
        layout.addWidget(group)

        # Buttons
        btn_box = QDialogButtonBox(
            QDialogButtonBox.Save | QDialogButtonBox.Cancel
        )
        btn_box.accepted.connect(self._on_save)
        btn_box.rejected.connect(self.reject)
        layout.addWidget(btn_box)

    # ── events ─────────────────────────────────────────────────────────

    def _force_upper(self, text: str) -> None:
        upper = text.upper()
        if upper != text:
            pos = self.ticker_edit.cursorPosition()
            self.ticker_edit.setText(upper)
            self.ticker_edit.setCursorPosition(pos)

    def _on_currency_changed(self, index: int) -> None:
        is_usd = self.currency_combo.currentData() == Currency.USD.value
        self.fx_edit.setEnabled(is_usd)
        if not is_usd:
            self.fx_edit.setText("1.0")

    def _add_institution(self) -> None:
        name, ok = QInputDialog.getText(
            self, "Nova Instituição", "Nome da instituição:"
        )
        if ok and name.strip():
            name = name.strip()
            # Persist via callback to DB
            if self._add_institution_callback:
                try:
                    self._add_institution_callback(name)
                except Exception as e:
                    QMessageBox.warning(self, "Erro", str(e))
                    return
            # Refresh list: add, re-sort, and select
            if self.inst_combo.findText(name) < 0:
                self._institutions.append(name)
            self._institutions.sort()
            self.inst_combo.clear()
            for inst in self._institutions:
                self.inst_combo.addItem(inst)
            self.inst_combo.setCurrentText(name)

    def _on_save(self) -> None:
        try:
            tx = self._build_transaction()
        except ValueError as e:
            QMessageBox.warning(self, "Validação", str(e))
            return

        # Date check: if date ≠ today, ask for confirmation
        if tx.date != date.today():
            reply = QMessageBox.question(
                self,
                "Confirmar Data",
                f"A data da transação ({tx.date.strftime('%d/%m/%Y')}) é "
                f"diferente da data atual.\n\n"
                f"Deseja incluir a transação com esta data?",
                QMessageBox.Yes | QMessageBox.No,
                QMessageBox.No,
            )
            if reply != QMessageBox.Yes:
                return

            # Inform about rebuild
            QMessageBox.information(
                self,
                "Reconstrução Necessária",
                "Como a data da transação é diferente da data atual, "
                "o sistema deverá ser reconstruído e recalculado.\n\n"
                "Isso será feito automaticamente ao salvar.",
            )
            self._needs_rebuild = True
        else:
            self._needs_rebuild = False

        self.saved.emit(tx)
        self.accept()

    # ── builders ───────────────────────────────────────────────────────

    def _build_transaction(self) -> Transaction:
        ticker = self.ticker_edit.text().strip().upper()
        if not ticker:
            raise ValueError("Ticker é obrigatório.")

        try:
            qty = Decimal(self.qty_edit.text().strip().replace(",", "."))
            if qty <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise ValueError("Quantidade deve ser um número positivo.")

        try:
            price = Decimal(self.price_edit.text().strip().replace(",", "."))
            if price < 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise ValueError("Preço deve ser um número >= 0.")

        try:
            fx = Decimal(self.fx_edit.text().strip().replace(",", "."))
            if fx <= 0:
                raise ValueError()
        except (InvalidOperation, ValueError):
            raise ValueError("Taxa FX deve ser um número positivo.")

        institution = self.inst_combo.currentText().strip()
        if not institution:
            raise ValueError("Instituição é obrigatória. Selecione ou cadastre uma.")

        return Transaction(
            id=self._tx.id if self._tx else None,
            ticker=ticker,
            asset_class=AssetClass(self.asset_class_combo.currentData()),
            type=TransactionType(self.type_combo.currentData()),
            trade_type=TradeType(self.trade_type_combo.currentData()),
            date=self.date_edit.date().toPython(),
            quantity=qty,
            price=price,
            currency=Currency(self.currency_combo.currentData()),
            fx_rate=fx,
            institution=institution,
            notes=self.notes_edit.toPlainText().strip(),
        )

    def _populate(self, tx: Transaction) -> None:
        self.ticker_edit.setText(tx.ticker)
        idx = self.asset_class_combo.findData(tx.asset_class.value)
        if idx >= 0:
            self.asset_class_combo.setCurrentIndex(idx)
        idx = self.type_combo.findData(tx.type.value)
        if idx >= 0:
            self.type_combo.setCurrentIndex(idx)
        idx = self.trade_type_combo.findData(tx.trade_type.value)
        if idx >= 0:
            self.trade_type_combo.setCurrentIndex(idx)
        self.date_edit.setDate(tx.date)
        self.qty_edit.setText(str(tx.quantity))
        self.price_edit.setText(str(tx.price))
        idx = self.currency_combo.findData(tx.currency.value)
        if idx >= 0:
            self.currency_combo.setCurrentIndex(idx)
        self.fx_edit.setText(str(tx.fx_rate))
        # Set institution in combo
        inst_idx = self.inst_combo.findText(tx.institution)
        if inst_idx >= 0:
            self.inst_combo.setCurrentIndex(inst_idx)
        else:
            self.inst_combo.addItem(tx.institution)
            self.inst_combo.setCurrentText(tx.institution)
        self.notes_edit.setPlainText(tx.notes)
