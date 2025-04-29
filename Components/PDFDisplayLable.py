import fitz  # PyMuPDF
from PyQt5.QtGui import QPainter, QPen, QBrush
from PyQt5.QtWidgets import QLabel, QStyle
from PyQt5.QtCore import Qt, QRect
from PyQt5.QtGui import QColor

class PDFDisplayLabel(QLabel):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent_viewer = parent

    def paintEvent(self, event):
        super().paintEvent(event)
        painter = QPainter(self)
        painter.setRenderHint(QPainter.Antialiasing)

        # 绘制搜索高亮
        viewer = self.parent_viewer
        if viewer.search_bar.isVisible():
            for idx, result in enumerate(viewer.search_results):
                if result["page"] == viewer.current_page:
                    screen_rect = viewer.pdf_rect_to_screen(result["rect"], result["page"])
                    if screen_rect.isValid():
                        is_current = idx == viewer.current_search_index
                        self.draw_search_highlight(painter, screen_rect, is_current)
        
        # 绘制所有历史选区（不再调整坐标）
        for selection in self.parent_viewer.selected_rects:
            rect = selection["rect"]
            self.draw_selection(painter, rect, is_active=False)

        # 绘制当前活跃选区（直接使用原始坐标）
        if self.parent_viewer.active_selection:
            start = self.parent_viewer.active_selection["start"]
            current = self.parent_viewer.active_selection["current"]
            rect = QRect(
                min(start.x(), current.x()),
                min(start.y(), current.y()),
                abs(current.x() - start.x()),
                abs(current.y() - start.y())
            )
            self.draw_selection(painter, rect, is_active=True)

        # 获取主窗口实例
        main_window = self.parent_viewer.window()
    
        # 安全校验
        if hasattr(main_window, 'current_paper') and main_window.current_paper:
            notes = main_window.current_paper.get('notes', [])
            current_page = self.parent_viewer.current_page
            h_scroll = self.parent_viewer.scroll_area.horizontalScrollBar().value()
            v_scroll = self.parent_viewer.scroll_area.verticalScrollBar().value()
            
            for note in notes:
                if note['page'] == current_page:
                    rect = fitz.Rect(note['rect']['x0'], note['rect']['y0'],
                                    note['rect']['x1'], note['rect']['y1'])
                    screen_rect = self.parent_viewer.pdf_rect_to_screen(rect, current_page)
                    if screen_rect.isValid():
                        # 调整滚动偏移
                        adj_rect = screen_rect.translated(-h_scroll, -v_scroll)
                        # 绘制黄色高亮
                        painter.setBrush(QBrush(QColor(255, 255, 0, 100)))
                        painter.setPen(Qt.NoPen)
                        painter.drawRect(adj_rect)
                        # 绘制笔记图标
                        icon = self.style().standardIcon(QStyle.SP_FileDialogDetailedView)
                        pixmap = icon.pixmap(16, 16)
                        painter.drawPixmap(adj_rect.topLeft(), pixmap)

    def draw_search_highlight(self, painter, rect, is_current):
        # 当前结果使用更明显的样式
        if is_current:
            fill_color = QColor(255, 255, 0, 120)  # 半透明黄色
            border_color = QColor(255, 165, 0)     # 橙色边框
        else:
            fill_color = QColor(255, 255, 0, 60)   # 更透明的黄色
            border_color = QColor(255, 255, 0, 150)
        
        painter.setBrush(QBrush(fill_color))
        painter.setPen(QPen(border_color, 1, Qt.SolidLine))
        painter.drawRoundedRect(rect, 2, 2)

    def draw_selection(self, painter, rect, is_active=True):
        """绘制选区（使用原始坐标）"""
        fill_color = QColor(101, 147, 245)
        fill_color.setAlpha(60 if is_active else 20)
        
        painter.setPen(Qt.NoPen)
        painter.setBrush(QBrush(fill_color))
        painter.drawRoundedRect(rect, 3, 3)

        border_color = QColor(33, 150, 243)
        painter.setPen(QPen(border_color, 1, Qt.DashLine if is_active else Qt.SolidLine))
        painter.setBrush(Qt.NoBrush)
        painter.drawRoundedRect(rect, 3, 3)