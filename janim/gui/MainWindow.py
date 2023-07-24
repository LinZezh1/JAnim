from typing import Optional

from PySide6.QtGui import QCloseEvent
from PySide6.QtWidgets import QWidget, QMainWindow

from janim.gui.GLWidget import GLWidget
from janim.gl.texture import Texture
from janim.gl.render import ShaderProgram

class MainWindow(GLWidget):
    def closeEvent(self, event: QCloseEvent) -> None:
        Texture.release_all()
        ShaderProgram.release_all()
        super().closeEvent(event)

    
