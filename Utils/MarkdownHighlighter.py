from PyQt5.QtGui import QFont, QColor, QTextCharFormat, QSyntaxHighlighter

class MarkdownHighlighter(QSyntaxHighlighter):
    # 修改高亮规则适应亮色主题
    def __init__(self, document):
        super().__init__(document)
        self._rules = []
        
        # 标题样式
        heading_format = QTextCharFormat()
        heading_format.setForeground(QColor("#007ACC"))  # VSCode蓝
        heading_format.setFontWeight(QFont.Bold)
        self._rules.append((r'^#+\s+(.+)$', heading_format))
        
        # 列表样式
        list_format = QTextCharFormat()
        list_format.setForeground(QColor("#616161"))
        self._rules.append((r'^[\*\-\+] .+$', list_format))
        
        # 代码块样式
        code_format = QTextCharFormat()
        code_format.setForeground(QColor("#D18305"))
        code_format.setBackground(QColor("#F3F3F3"))  # 添加背景色
        self._rules.append((r'`[^`]+`', code_format))
        
        # 加粗样式
        bold_format = QTextCharFormat()
        bold_format.setFontWeight(QFont.Bold)
        self._rules.append((r'\*\*(.+?)\*\*', bold_format))
        
        # 斜体样式
        italic_format = QTextCharFormat()
        italic_format.setFontItalic(True)
        self._rules.append((r'\*(.+?)\*', italic_format))