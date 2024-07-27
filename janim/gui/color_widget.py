from enum import Enum

# from PySide6.QtCore import QRegularExpression
# from PySide6.QtGui import QRegularExpressionValidator
from PySide6.QtWidgets import QColorDialog, QLineEdit, QWidget

from janim.gui.ui_ColorWidget import Ui_ColorWidget
from janim.locale.i18n import get_local_strings
from janim.utils.simple_functions import clip

_ = get_local_strings('color_widget')


class ColorWidget(QWidget):
    class EditSource(Enum):
        RGB = 0
        Hex = 1
        Other = 2

    def __init__(self, parent: QWidget | None = None):
        super().__init__(parent)

        self.ui = Ui_ColorWidget()
        self.ui.setupUi(self)
        self.rgb_editors = (self.ui.edit_R, self.ui.edit_G, self.ui.edit_B)
        self.ui.cbb_norm.stateChanged.connect(self.norm_state_changed)

        # 不知道为什么无效
        # self.regex = QRegularExpression(r'#[A-Za-z]{0,6}')
        # self.validator = QRegularExpressionValidator(self.regex, self.ui.edit_hex)
        # self.ui.edit_hex.setValidator(self.validator)

        self.set_color(0, 0, 0)

        for editor in self.rgb_editors:
            editor.textChanged.connect(self.rgb_edited)
            editor.editingFinished.connect(self.rgb_finished)

        self.ui.edit_hex.textChanged.connect(self.hex_edited)
        self.ui.edit_hex.editingFinished.connect(self.hex_finished)

        self.ui.btn_picker.clicked.connect(self.btn_picker_clicked)

        self.ui.cbb_norm.setText(_('normalized form'))
        self.ui.label_picker.setText(_('Color picker'))
        self.ui.label_builtins.setText(_('Builtins'))

    def rgb_edited(self, text: str) -> None:
        editor: QLineEdit = self.sender()

        norm = self.ui.cbb_norm.isChecked()
        try:
            value = (float if norm else int)(text)
        except ValueError:
            return

        maximum = 1 if norm else 255
        if value < 0 or value > maximum:
            value = clip(value, 0, maximum)
            editor.blockSignals(True)
            editor.setText(str(value))
            editor.blockSignals(False)

        self.set_color(
            *[
                (
                    round(float(editor.text()) * 255)
                    if norm
                    else int(editor.text())
                )
                for editor in self.rgb_editors
            ],
            source=ColorWidget.EditSource.RGB
        )

    def rgb_finished(self) -> None:
        editor: QLineEdit = self.sender()
        norm = self.ui.cbb_norm.isChecked()
        try:
            (float if norm else int)(editor.text())
        except ValueError:
            editor.setText('0')

    def norm_state_changed(self, stat: bool) -> None:
        for editor in self.rgb_editors:
            editor.blockSignals(True)
            if stat:
                editor.setText(f'{int(editor.text()) / 255:.2f}')
            else:
                editor.setText(f'{float(editor.text()) * 255:.0f}')
            editor.blockSignals(False)
        self.update_display_label()

    def hex_edited(self, text: str) -> None:
        rgb = self.parse_hex(text)
        if rgb is None:
            return

        self.set_color(*rgb, source=ColorWidget.EditSource.Hex)

    def hex_finished(self) -> None:
        rgb = self.parse_hex(self.ui.edit_hex.text())
        if rgb is None:
            self.ui.edit_hex.setText('#000000')

    @staticmethod
    def parse_hex(hex: str) -> tuple[int, int, int] | None:
        if not hex.startswith('#'):
            return None

        if len(hex) != 4 and len(hex) != 7:
            return None

        if len(hex) == 4:
            parts = (hex[1] * 2, hex[2] * 2, hex[3] * 2)
        else:
            parts = (hex[1:3], hex[3:5], hex[5:7])

        try:
            return tuple(int(s, 16) for s in parts)
        except ValueError:
            return None

    def btn_picker_clicked(self) -> None:
        dialog = QColorDialog(self)
        if not dialog.exec():
            return

        color = dialog.currentColor()
        self.set_color(color.red(), color.green(), color.blue())

    def set_color(self, r: int, g: int, b: int, source=EditSource.Other) -> None:
        assert r <= 255 and g <= 255 and b <= 255

        self.ui.widget.setStyleSheet(
            'border: 2px solid white;\n'
            f'background: rgb({r}, {g}, {b});\n'
            'border-radius: 8px;'
        )

        if source is not ColorWidget.EditSource.RGB:
            if self.ui.cbb_norm.isChecked():
                txts = [f'{r / 255:.2f}', f'{g / 255:.2f}', f'{b / 255:.2f}']
            else:
                txts = [str(r), str(g), str(b)]

            for editor, txt in zip(self.rgb_editors, txts):
                editor.blockSignals(True)
                editor.setText(txt)
                editor.blockSignals(False)

        if source is not ColorWidget.EditSource.Hex:
            self.ui.edit_hex.blockSignals(True)
            self.ui.edit_hex.setText(f'#{r:0=2X}{g:0=2X}{b:0=2X}')
            self.ui.edit_hex.blockSignals(False)

        self.update_display_label()

    def update_display_label(self):
        txt = ', '.join([editor.text() for editor in self.rgb_editors])
        self.ui.display_label.setText(f'[{txt}]')
