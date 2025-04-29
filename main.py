import sys
from PyQt5.QtWidgets import QApplication
from PyQt5.QtGui import QFont
from Components.LiteratureManager import LiteratureManager

if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 10))
    window = LiteratureManager()
    window.show()
    sys.exit(app.exec_())