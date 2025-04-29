from PyQt5.QtWidgets import QTextEdit
from PyQt5.QtCore import Qt, pyqtSignal

class ChatTextEdit(QTextEdit):
    ctrlEnterPressed = pyqtSignal()  # 定义自定义信号
    
    def __init__(self, parent=None):
        super().__init__(parent)
    
    def keyPressEvent(self, event):
        if event.key() == Qt.Key_Return and (event.modifiers() & Qt.ControlModifier):
            self.ctrlEnterPressed.emit()
            event.accept()
        else:
            super().keyPressEvent(event)