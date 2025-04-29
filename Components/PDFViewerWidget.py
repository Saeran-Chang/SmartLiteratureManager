import time
import fitz  # PyMuPDF
from PyQt5.QtGui import QImage, QPixmap, QCursor, QPalette
from PyQt5.QtWidgets import (QApplication, QWidget, QVBoxLayout, QHBoxLayout, 
                             QStyle, QLabel, QPushButton, QScrollArea, QMessageBox,
                            QLineEdit, QMenu)
from PyQt5.QtCore import Qt, pyqtSignal, QPoint, QRect, QTimer
from PyQt5.QtGui import QColor, QPixmap
from Components.PDFDisplayLable import PDFDisplayLabel

class PDFViewerWidget(QWidget):
    page_changed = pyqtSignal(int)
    text_selected = pyqtSignal(str)
    selection_cleared = pyqtSignal()
    note_add_requested = pyqtSignal(int, object)  # 页码和fitz.Rect
    translate_requested = pyqtSignal(str)  # 翻译信号

    def __init__(self, parent=None):
        super().__init__(parent)
        self.doc = None
        self.current_page = 0
        self.scale = 1.0
        self.selected_rects = []
        self.active_selection = None
        self.hovered_selection = None
        self.last_hover_time = 0

        # 初始化核心显示组件
        self.image_label = PDFDisplayLabel(self)
        self.image_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        
        self.scroll_area = QScrollArea()
        self.scroll_area.setWidget(self.image_label)
        self.scroll_area.setWidgetResizable(True)

        # 搜索功能组件
        self.search_bar = QWidget()
        self.search_bar.setObjectName("searchBar")
        self.search_bar.setFixedHeight(40)
        search_layout = QHBoxLayout(self.search_bar)
        search_layout.setContentsMargins(8, 4, 8, 4)
        search_layout.setSpacing(6)

        # 搜索输入框
        self.search_input = QLineEdit()
        self.search_input.setPlaceholderText("搜索内容 (Ctrl+F)")
        self.search_input.setFixedWidth(280)
        self.search_input.setObjectName("searchInput")
        
        # 搜索按钮组
        self.prev_btn = QPushButton("↑")
        self.prev_btn.setToolTip("上一个匹配项 (Shift+Enter)")
        self.prev_btn.setObjectName("searchNavBtn")

        self.next_btn = QPushButton("↓")
        self.next_btn.setToolTip("下一个匹配项 (Enter)")
        self.next_btn.setObjectName("searchNavBtn")

        # 匹配计数器
        self.match_label = QLabel("0/0")
        self.match_label.setObjectName("matchCounter")
        self.match_label.setAlignment(Qt.AlignCenter)
        self.match_label.setFixedWidth(80)

        # 关闭按钮
        self.close_btn = QPushButton("×")
        self.close_btn.setToolTip("关闭搜索 (Esc)")
        self.close_btn.setObjectName("closeSearchBtn")

        # 创建标题栏
        self.title_bar = QWidget()
        self.title_bar.setObjectName("titleBar")
        title_layout = QHBoxLayout(self.title_bar)
        title_layout.setContentsMargins(8, 4, 8, 4)
        title_layout.setSpacing(6)

        # 标题标签
        self.title_label = QLabel("")
        self.title_label.setObjectName("titleLabel")

        # 放大镜按钮
        self.search_icon = QPushButton()
        self.search_icon.setObjectName("searchIcon")
        self.search_icon.setCursor(Qt.PointingHandCursor)
        self.search_icon.setToolTip("打开搜索栏 (Ctrl+F)")
        self.search_icon.clicked.connect(self.toggle_search_bar)
        
        # 设置图标（使用系统图标或自定义图标）
        search_icon = self.style().standardIcon(QStyle.SP_FileDialogContentsView)
        self.search_icon.setIcon(search_icon)

        # 标题栏布局组装
        title_layout.addWidget(self.title_label)
        title_layout.addStretch()
        title_layout.addWidget(self.search_icon)

        # 搜索框布局组装
        search_layout.addWidget(self.search_input)
        search_layout.addWidget(self.prev_btn)
        search_layout.addWidget(self.next_btn)
        search_layout.addWidget(self.match_label)
        search_layout.addWidget(self.close_btn)

        self.search_timer = QTimer()
        self.search_timer.setSingleShot(True)
        self.search_timer.setInterval(300)  # 300毫秒延迟
        self.search_timer.timeout.connect(self.perform_search)

        # 主布局
        main_layout = QVBoxLayout(self)
        main_layout.setContentsMargins(0, 0, 0, 0)
        main_layout.addWidget(self.title_bar)    # 新增标题栏
        main_layout.addWidget(self.search_bar)
        main_layout.addWidget(self.scroll_area)
        self.search_bar.setVisible(False)

        # 加载样式表
        self.load_stylesheet()

        # 上下文菜单
        self.context_menu = QMenu(self)
        self.context_menu.setObjectName("SelectionMenu")
        self.ask_action = self.context_menu.addAction("📝 提问选中内容")
        self.translate_action = self.context_menu.addAction("🌐 翻译选中内容")
        self.copy_action = self.context_menu.addAction("📋 复制文本")
        self.note_action = self.context_menu.addAction("📝 添加笔记")
        self.clear_action = self.context_menu.addAction("🧹 清除所有选择")
        self.ask_action.triggered.connect(self.emit_selection)
        self.translate_action.triggered.connect(self.emit_translation_request)
        self.copy_action.triggered.connect(self.copy_selection)
        self.note_action.triggered.connect(self.trigger_add_note)
        self.clear_action.triggered.connect(self.clear_selections)

        # 悬停检测定时器
        self.hover_timer = QTimer(self)
        self.hover_timer.setInterval(50)
        self.hover_timer.timeout.connect(self.check_hover)
        self.hover_timer.start()

        self.search_results = []
        self.current_search_index = -1

        # 信号连接
        self.search_input.textChanged.connect(self.start_search_timer)
        self.prev_btn.clicked.connect(self.prev_search_result)
        self.next_btn.clicked.connect(self.next_search_result)
        self.close_btn.clicked.connect(self.close_search)

        # 添加自动缩放标志位
        self.auto_scale = True

        # 设置标签对齐方式
        self.match_label.setAlignment(Qt.AlignCenter)

    # 应用 VSCode 风格样式表
    def load_stylesheet(self):
        try:
            with open("style/PDFViewerStyle.qss", "r", encoding="utf-8") as f:
                self.setStyleSheet(f.read())
        except Exception as e:
            print(f"无法加载样式表: {str(e)}")
            # 使用备用样式
            self.setStyleSheet("""
                QScrollArea { background: white; border: 1px solid #e0e0e0; }
                #titleBar { background: #f3f3f3; border-bottom: 1px solid #e0e0e0; }
            """)

    def start_search_timer(self):
        self.search_timer.stop()  # 每次输入都重置定时器
        self.search_timer.start()

    def emit_translation_request(self):
        """发送翻译请求"""
        if self.selected_rects:
            self.translate_requested.emit(self.selected_rects[-1]["text"])
            self.clear_selections()

    def trigger_add_note(self):
        if self.selected_rects:
            selection = self.selected_rects[-1]
            page = self.current_page
            pdf_rect = self.screen_to_pdf(selection['rect'])
            self.note_add_requested.emit(page, pdf_rect)
            self.clear_selections()

    def toggle_search_bar(self):
        visible = not self.search_bar.isVisible()
        self.search_bar.setVisible(visible)
        
        # 更新图标颜色指示状态
        palette = self.search_icon.palette()
        if visible:
            palette.setColor(QPalette.Button, QColor(224, 224, 224))
        else:
            palette.setColor(QPalette.Button, QColor(243, 243, 243))
        self.search_icon.setPalette(palette)
        
        if visible:
            self.search_input.setFocus()
            self.search_input.selectAll()
        else:
            self.clear_search()
            
        # 自动滚动到可视区域
        if visible and self.doc:
            self.scroll_area.ensureVisible(0, 0)

    def keyPressEvent(self, event):
        if event.key() == Qt.Key_F and event.modifiers() == Qt.ControlModifier:
            self.toggle_search_bar()
            event.accept()
        elif event.key() == Qt.Key_Escape and self.search_bar.isVisible():
            self.close_search()
            event.accept()
        else:
            super().keyPressEvent(event)

    def perform_search(self):
        # 停止定时器防止重复触发
        self.search_timer.stop()

        search_text = self.search_input.text().strip()
        if not search_text:
            self.clear_search()
            return

        self.search_results.clear()
        self.current_search_index = -1
        
        for page_num in range(len(self.doc)):
            page = self.doc.load_page(page_num)
            text_instances = page.search_for(search_text)
            
            for rect in text_instances:
                self.search_results.append({
                    "page": page_num,
                    "rect": rect,
                    "screen_rect": self.pdf_rect_to_screen(rect, page_num)
                })
        
        if self.search_results:
            self.current_search_index = 0
            self.highlight_current_search()
        self.update_match_label()
        self.image_label.update()

    def pdf_rect_to_screen(self, rect, page_num):
        """将PDF坐标转换为当前屏幕坐标"""
        if page_num != self.current_page:
            return QRect()
            
        zoom = self.scale * 2
        return QRect(
            int(rect.x0 * zoom),
            int(rect.y0 * zoom),
            int((rect.x1 - rect.x0) * zoom),
            int((rect.y1 - rect.y0) * zoom)
        )
    
    def highlight_current_search(self):
        if not self.search_results:
            return
            
        result = self.search_results[self.current_search_index]
        
        # 切换到对应页面
        if result["page"] != self.current_page:
            self.current_page = result["page"]
            self.show_page()
            self.page_changed.emit(self.current_page)
            
        # 滚动到可见区域
        screen_rect = self.pdf_rect_to_screen(result["rect"], result["page"])
        self.scroll_area.ensureVisible(
            screen_rect.center().x(), 
            screen_rect.center().y(),
            screen_rect.width(),
            screen_rect.height()
        )
        self.image_label.update()

    def prev_search_result(self):
        if self.search_results:
            self.current_search_index = (self.current_search_index - 1) % len(self.search_results)
            self.highlight_current_search()
            self.update_match_label()

    def next_search_result(self):
        if self.search_results:
            self.current_search_index = (self.current_search_index + 1) % len(self.search_results)
            self.highlight_current_search()
            self.update_match_label()

    def update_match_label(self):
        count = len(self.search_results)
        if count == 0:
            self.match_label.setText("无匹配")
        else:
            self.match_label.setText(f"{self.current_search_index+1}/{count}")

    def clear_search(self):
        """清空搜索内容"""
        self.search_input.clear()
        self.search_results.clear()
        self.current_search_index = -1
        self.match_label.setText("0/0")
        self.image_label.update()

    def close_search(self):
        """关闭搜索栏"""
        self.search_bar.hide()
        self.clear_search()  # 调用统一清理方法

    def load_pdf(self, file_path):
        """加载PDF文档"""
        try:
            self.doc = fitz.open(file_path)
            self.current_page = 0
            self.page_count = len(self.doc)  # 新增总页数保存
            self.selected_rects.clear()
            self.show_page()
        except Exception as e:
            QMessageBox.critical(self, "错误", f"无法打开PDF文件：{str(e)}")
            self.doc = None  # 确保加载失败时重置doc
            self.current_page = 0
            self.selected_rects.clear()
            self.image_label.clear()

    def show_page(self):
        """精确渲染页面"""
        if not self.doc:
            return

        page = self.doc.load_page(self.current_page)
        page_rect = page.rect
        
        # 仅在自动缩放模式下计算缩放比例
        if self.auto_scale:  # 新增条件判断
            scale_x = self.scroll_area.width() / page_rect.width
            scale_y = self.scroll_area.height() / page_rect.height
            self.scale = min(scale_x, scale_y) / 2  # 保持高清渲染
        
        # 生成高质量图像
        mat = fitz.Matrix(self.scale * 2, self.scale * 2)
        pix = page.get_pixmap(matrix=mat, alpha=False)
        
        # 转换为Qt图像并居中显示
        img = QImage(
            pix.samples, pix.width, pix.height,
            pix.stride, QImage.Format_RGB888
        ).rgbSwapped()
        
        self.image_label.setPixmap(QPixmap.fromImage(img))
        self.image_label.adjustSize()

    # 事件处理逻辑
    def mousePressEvent(self, event):
        if not self.doc:
            return
        if event.button() == Qt.LeftButton:
            self.start_selection(event.pos())
        elif event.button() == Qt.RightButton:
            self.show_context_menu(event.pos())

    def mouseMoveEvent(self, event):
        if self.active_selection and self.doc:
            self.update_selection(event.pos())

    def mouseReleaseEvent(self, event):
        if self.doc and event.button() == Qt.LeftButton and self.active_selection:
            self.finalize_selection()

    # 选区管理逻辑
    def start_selection(self, pos):
        """开始新的选区"""
        self.active_selection = {
            "start": self.map_to_label(pos),
            "current": self.map_to_label(pos),
            "page": self.current_page
        }
        self.image_label.update()

    def update_selection(self, pos):
        """更新选区范围"""
        if self.active_selection:
            self.active_selection["current"] = self.map_to_label(pos)
            self.image_label.update()

    def finalize_selection(self):
        try:
            # 检查文档和页码有效性
            if not self.doc or self.current_page < 0 or self.current_page >= len(self.doc):
                print("文档未加载或当前页码无效")
                self.active_selection = None
                return

            start = self.active_selection["start"]
            end = self.active_selection["current"]
            
            # 计算规范化矩形
            rect = self.normalize_rect(start, end)
            pdf_rect = self.screen_to_pdf(rect)
            
            # 提取文本
            page = self.doc[self.current_page]
            # 使用"words"模式获取选区内的单词列表
            words = page.get_text("words", clip=pdf_rect)
            # 拼接所有单词的文本内容
            text = ' '.join(word[4] for word in words).strip()
            if text:
                self.selected_rects = [{
                    "rect": rect,
                    "text": text,
                    "timestamp": time.time()
                }]
            
            self.active_selection = None
            self.image_label.update()
        except Exception as e:
            print(f"选区处理失败：{str(e)}")

    # 坐标转换方法
    def map_to_label(self, pos):
        """转换坐标到标签坐标系（考虑滚动偏移）"""
        # 将窗口坐标转换为视口坐标
        pos_in_viewport = self.scroll_area.viewport().mapFrom(self, pos)
        # 获取当前滚动条位置
        h_scroll = self.scroll_area.horizontalScrollBar().value()
        v_scroll = self.scroll_area.verticalScrollBar().value()
        # 计算实际标签坐标
        return QPoint(pos_in_viewport.x() + h_scroll, pos_in_viewport.y() + v_scroll)

    def screen_to_pdf(self, rect):
        """屏幕坐标转PDF坐标"""
        scale = self.scale * 2
        return fitz.Rect(
            rect.left() / scale,
            rect.top() / scale,
            rect.right() / scale,
            rect.bottom() / scale
        )

    @staticmethod
    def normalize_rect(start, end):
        """确保矩形坐标有序"""
        return QRect(
            min(start.x(), end.x()),
            min(start.y(), end.y()),
            abs(end.x() - start.x()),
            abs(end.y() - start.y())
        )

    # 交互功能
    def check_hover(self):
        """检测鼠标悬停状态"""
        pos = self.map_to_label(self.mapFromGlobal(QCursor.pos()))
        for rect in reversed(self.selected_rects):
            if rect["rect"].contains(pos):
                if self.hovered_selection != rect:
                    self.hovered_selection = rect
                    self.image_label.update()
                return
        if self.hovered_selection:
            self.hovered_selection = None
            self.image_label.update()

    def show_context_menu(self, pos):
        """显示上下文菜单"""
        self.check_hover()  # 手动触发悬停状态检查
        if self.hovered_selection:  # 检查当前是否有悬停的选区
            menu_pos = self.mapToGlobal(pos)
            self.context_menu.exec_(menu_pos)

    def copy_selection(self):
        """复制选中文本到剪贴板"""
        if self.selected_rects:  # 直接访问最新选区
            QApplication.clipboard().setText(self.selected_rects[-1]["text"])
            self.clear_selections()

    def clear_selections(self):
        """清除所有选区"""
        self.selected_rects.clear()
        self.hovered_selection = None
        self.image_label.update()
        self.selection_cleared.emit()

    def emit_selection(self):
        """发送选中文本信号"""
        if self.selected_rects:
            # 添加两个换行符
            modified_text = "\n\n" + self.selected_rects[-1]["text"]
            self.text_selected.emit(modified_text)
            
            # 跳转到智能问答窗口
            main_window = self.window()
            from Components.LiteratureManager import LiteratureManager
            if isinstance(main_window, LiteratureManager):
                main_window.right_tabs.setCurrentIndex(0)  # 智能问答是第一个标签页
                
            self.clear_selections()

    # 缩放和翻页
    def wheelEvent(self, event):
        """实现滚轮翻页功能"""
        if event.modifiers() == Qt.ControlModifier:
            # 处理缩放时禁用自动缩放
            self.auto_scale = False  # 新增标志位设置
            delta = event.angleDelta().y()
            self.scale *= 1.1 if delta > 0 else 0.9
            self.scale = max(0.5, min(self.scale, 5.0))
            self.show_page()
            event.accept()
        else:
            # 翻页时保持当前缩放模式
            delta = event.angleDelta().y()
            if delta < 0 and self.current_page < len(self.doc) - 1:
                self.current_page += 1
                self.show_page()
                self.page_changed.emit(self.current_page)
            elif delta > 0 and self.current_page > 0:
                self.current_page -= 1
                self.show_page()
                self.page_changed.emit(self.current_page)
            event.accept()

    def resizeEvent(self, event):
        """窗口大小改变时恢复自动缩放"""
        self.auto_scale = True  # 新增resize事件处理
        self.show_page()
        super().resizeEvent(event)