from PyQt5.QtWidgets import QVBoxLayout, QDialog, QDialogButtonBox, QFormLayout, QLineEdit

class SettingsDialog(QDialog):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("API设置")
        self.setFixedSize(400, 150)
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout()
        form_layout = QFormLayout()
        
        self.api_key_input = QLineEdit()
        self.api_key_input.setPlaceholderText("输入Kimi API密钥")
        self.api_key_input.setEchoMode(QLineEdit.Password)
        form_layout.addRow("API密钥:", self.api_key_input)
        
        layout.addLayout(form_layout)
        
        button_box = QDialogButtonBox(QDialogButtonBox.Save | QDialogButtonBox.Cancel)
        button_box.accepted.connect(self.accept)
        button_box.rejected.connect(self.reject)
        layout.addWidget(button_box)
        
        self.setLayout(layout)

    def get_api_key(self):
        return self.api_key_input.text().strip()

    def set_api_key(self, key):
        self.api_key_input.setText(key)