import os
import json
import re
import time
import html
from markdown import markdown
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
                            QLabel, QPushButton, QTextEdit, QListWidget, QTabWidget,
                            QSplitter, QFileDialog, QMessageBox, QDialog, QAbstractItemView,
                            QStatusBar, QMenu, QListWidgetItem, QTextBrowser)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtCore import QFile, QTextStream
from PyQt5.QtGui import QTextCursor, QIcon, QTextBlockFormat
from Config.Config import ANALYSIS_DIR, CONTENT_FILE
from Dailog.SettingDialog import SettingsDialog
from Components.NoteManagementWidget import NoteManagementWidget
from Components.PDFViewerWidget import PDFViewerWidget
from Utils.ChatTextEdit import ChatTextEdit
from Utils.MarkdownHighlighter import MarkdownHighlighter
from Workers.AnalysisWorker import AnalysisWorker
from Workers.ChatWorker import ChatWorker
from Workers.FileUploadWorder import FileUploadWorker


class LiteratureManager(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("智能文献分析系统")
        self.setGeometry(100, 100, 1200, 800)
        self.showMaximized()
        self.content = self.load_content()
        self.api_key = self.content.get('api_key', '')
        self.papers = []
        self.current_paper = None
        self.workers = []
        self.setWindowIcon(QIcon('assets/logo.png'))  # 设置窗口图标

        self.chat_processing = False  # 新增聊天处理状态
        
        os.makedirs(ANALYSIS_DIR, exist_ok=True)
        self.init_ui()
        self.apply_styles()
        self.load_papers()
        self.pdf_viewer.note_add_requested.connect(self.handle_note_add_request)
        self.pdf_viewer.translate_requested.connect(self.handle_translation_request)  # 连接翻译信号

        # 添加上传和分析队列
        self.upload_queue = []
        self.upload_processing = False
        self.analysis_queue = []
        self.analysis_processing = False

        self.request_queue = []
        self.active_requests = 0
        self.MAX_CONCURRENT = 4  # 最大并发请求数
        self.last_request_time = 0

    def enqueue_request(self, worker, request_type):
        """将请求加入队列"""
        self.request_queue.append((worker, request_type))
        self.process_queue()

    def process_queue(self):
        """处理队列中的请求"""
        while self.active_requests < self.MAX_CONCURRENT and self.request_queue:
            # 确保请求间隔至少1秒
            elapsed = time.time() - self.last_request_time
            if elapsed < 1.2:
                QTimer.singleShot(int((1.2 - elapsed)*1000), self.process_queue)
                return

            worker, req_type = self.request_queue.pop(0)
            self.active_requests += 1
            self.last_request_time = time.time()
            
            # 连接信号
            if req_type == 'chat':
                worker.response_received.connect(self._handle_success_response)
            elif req_type == 'analysis':
                worker.analysis_complete.connect(self.save_analysis_result)
            elif req_type == 'file':
                worker.upload_complete.connect(lambda data, name, is_local: self.handle_upload_success(data, name, is_local))
            
            worker.error_occurred.connect(self.handle_error)
            worker.finished.connect(lambda: self.request_finished())
            worker.start()

    def request_finished(self):
        self.active_requests -= 1
        self.process_queue()

    def apply_styles(self):
        """从外部文件加载样式"""
        style_file = QFile("style/LiteratureStyle.qss")
        if style_file.open(QFile.ReadOnly | QFile.Text):
            stream = QTextStream(style_file)
            self.setStyleSheet(stream.readAll())
            style_file.close()

    def load_content(self):
        """加载配置文件内容，若不存在则创建并返回默认配置"""
        # 确保配置文件目录存在
        config_dir = os.path.dirname(CONTENT_FILE)
        if config_dir:
            os.makedirs(config_dir, exist_ok=True)

        # 如果文件不存在则初始化
        if not os.path.isfile(CONTENT_FILE):
            default_config = {
                'api_key': '',
                'papers': []
            }
            with open(CONTENT_FILE, 'w', encoding='utf-8') as f:
                json.dump(default_config, f, ensure_ascii=False, indent=2)
            return default_config

        # 加载现有配置（添加异常处理）
        try:
            with open(CONTENT_FILE, 'r', encoding='utf-8') as f:
                return json.load(f)
        except (json.JSONDecodeError, IOError) as e:
            raise RuntimeError(f"Failed to load config: {str(e)}")

    def save_content(self):
        papers_content = []
        for paper in self.papers:
            papers_content.append({
                'name': paper['name'],
                'path': paper['path'],
                'content_path': paper['content_path'],
                'analysis_path': paper['analysis_path'],
                'chat_history_path': paper['chat_history_path'],
                'notes_path': paper['notes_path']  # 新增此行
            })
        self.content['papers'] = papers_content
        with open(CONTENT_FILE, 'w', encoding='utf-8') as f:
            json.dump(self.content, f, ensure_ascii=False, indent=2)

    def load_papers(self):
        """从配置文件加载已有文献数据"""
        try:
            for p in self.content.get('papers', []):
                # 生成安全名称用于路径
                safe_name = re.sub(r'[\\/*?:"<>|]', '_', p['name'])
                # 动态生成notes_path（如果配置中不存在）
                notes_path = p.get('notes_path', os.path.join(ANALYSIS_DIR, f"{safe_name}_notes.json"))
                
                paper = {
                    'name': p['name'],
                    'path': p['path'],
                    'content_path': p['content_path'],
                    'analysis_path': p['analysis_path'],
                    'chat_history_path': p['chat_history_path'],
                    'notes_path': notes_path,  # 确保存在该键
                    'analysis': None,
                    'chat_history': [],
                    'notes': []
                }
                
                # 加载分析结果
                need_analysis = False
                if os.path.exists(paper['analysis_path']):
                    try:
                        with open(paper['analysis_path'], 'r', encoding='utf-8') as f:
                            paper['analysis'] = f.read()
                    except Exception as e:
                        print(f"读取分析结果失败: {e}")
                        need_analysis = True
                else:
                    need_analysis = True
                    
                if need_analysis:
                    self.start_analysis(paper)

                # 加载笔记文件
                if os.path.exists(paper['notes_path']):
                    try:
                        with open(paper['notes_path'], 'r', encoding='utf-8') as f:
                            paper['notes'] = json.load(f)
                    except Exception as e:
                        print(f"加载笔记失败: {e}")

                # 创建带路径标识的列表项
                item = QListWidgetItem(paper['name'])
                item.setData(Qt.UserRole, paper['path'])
                self.paper_list.addItem(item)
                
                self.papers.append(paper)
            
            if self.papers:
                self.update_status(f"已加载 {len(self.papers)} 篇文献")
            else:
                self.update_status("文献库为空")
                
        except Exception as e:
            QMessageBox.critical(self, "加载错误", f"加载文献失败: {str(e)}")

    def handle_note_add_request(self, page, pdf_rect):
        if not self.current_paper:
            return
        self.right_tabs.setCurrentIndex(1)  # 切换到笔记标签
        self.note_manager.create_new_note(page, pdf_rect)

    def handle_translation_request(self, text):
        """处理翻译请求"""
        if not self.check_api_key() or not self.current_paper:
            return
        
        # 禁用按钮
        self.chat_processing = True
        self._set_ui_interactive()

        # 构建翻译提示词
        prompt = f"请将以下学术文本翻译为中文，保持专业术语准确，保留格式符号，不要添加额外内容：\n\n{text}"
        
        # 使用新的角色标识翻译消息
        self.append_chat_message("user", prompt, role_tag="翻译请求")
        
        # 显示正在翻译提示
        self._append_translating_message()
        
        # 启动翻译工作线程
        worker = ChatWorker(
            self.api_key,
            "",  # 不需要文献内容
            prompt,
            is_translation=True
        )
        worker.response_received.connect(self.handle_translation_response)
        worker.error_occurred.connect(self.handle_translation_error)
        worker.finished.connect(self.on_translation_finished)  # 新增完成信号连接
        worker.start()
        self.workers.append(worker)

    def on_translation_finished(self):
        self.chat_processing = False
        self._set_ui_interactive()

    def handle_translation_response(self, response):
        """处理翻译响应"""
        # 删除正在翻译提示
        self._remove_thinking_message()
        translated_text = response['content']
        # 使用不同的样式显示翻译结果
        self.append_chat_message("assistant", translated_text, role_tag="翻译结果")

    def handle_translation_error(self, error):
        """处理翻译错误"""
        # 删除正在翻译提示
        self._remove_thinking_message()
        self.append_chat_message("system", f"翻译失败：{error}")

    def init_ui(self):
        # 主窗口初始化
        self.setWindowTitle("智能文献分析系统")
        self.setGeometry(100, 100, 1200, 800)
        
        # 创建主控件
        main_widget = QWidget()
        main_layout = QVBoxLayout()
        main_widget.setLayout(main_layout)
        self.setCentralWidget(main_widget)

        # 创建菜单栏
        menubar = self.menuBar()
        file_menu = menubar.addMenu("文件")
        file_menu.addAction("导入文献", self.import_papers)
        file_menu.addAction("设置", self.show_settings)
        file_menu.addAction("退出", self.close)

        # 主界面分割布局
        main_splitter = QSplitter(Qt.Horizontal)

        # ================== 左侧面板（文献列表 + 分析结果） ==================
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        left_layout.setContentsMargins(5, 5, 5, 5)
        
        # 文献列表
        left_layout.addWidget(QLabel("文献列表"))
        self.paper_list = QListWidget()
        self.paper_list.setSelectionMode(QAbstractItemView.ExtendedSelection)  # 启用多选模式
        self.paper_list.setMinimumWidth(250)
        self.paper_list.itemClicked.connect(self.show_paper_details)
        self.paper_list.setContextMenuPolicy(Qt.CustomContextMenu)
        self.paper_list.customContextMenuRequested.connect(self.show_paper_list_context_menu)
        left_layout.addWidget(self.paper_list)
        
        # 分析结果
        left_layout.addWidget(QLabel("文献概览"))
        self.analysis_display = QTextBrowser()
        self.analysis_display.setMinimumHeight(300)
        MarkdownHighlighter(self.analysis_display.document())
        left_layout.addWidget(self.analysis_display)

        # ================== 中间列（PDF阅读器） ==================
        center_panel = QWidget()
        center_layout = QVBoxLayout(center_panel)
        center_layout.setContentsMargins(5, 5, 5, 5)
        
        # PDF阅读器
        center_layout.addWidget(QLabel("文献内容"))
        self.pdf_viewer = PDFViewerWidget()
        self.pdf_viewer.text_selected.connect(self.handle_selected_text)
        center_layout.addWidget(self.pdf_viewer)

        # ================== 右侧面板（智能问答） ==================
        self.right_tabs = QTabWidget()
        self.right_tabs.addTab(self.create_chat_tab(), "智能问答")
        self.note_manager = NoteManagementWidget(self)
        self.right_tabs.addTab(self.note_manager, "文献笔记")

        # ================== 布局比例设置 ==================
        main_splitter.addWidget(left_panel)
        main_splitter.addWidget(center_panel)
        main_splitter.addWidget(self.right_tabs)
        main_splitter.setSizes([300, 600, 400])  # 初始宽度比例 3:6:4

        # 在PDFViewerWidget之后添加页码标签
        self.page_label = QLabel("第 1 页")
        center_layout.addWidget(self.page_label)

        # 连接页码变化信号
        self.pdf_viewer.page_changed.connect(self.update_page_label)

        # 组装主界面
        main_layout.addWidget(main_splitter)

        # 初始化状态栏
        self.status_bar = QStatusBar()
        self.setStatusBar(self.status_bar)
        self.update_status("就绪")

        # 应用样式
        self.apply_styles()

    def update_page_label(self, page_num):
        """更新页码显示"""
        if self.pdf_viewer.doc:
            total = len(self.pdf_viewer.doc)
            self.page_label.setText(f"第 {page_num + 1} 页 / 共 {total} 页")

    def show_paper_list_context_menu(self, pos):
        # 获取所有选中的项目
        selected_items = self.paper_list.selectedItems()
        if not selected_items:
            return
        
        # 获取对应的文献对象
        selected_papers = []
        for item in selected_items:
            paper_path = item.data(Qt.UserRole)
            paper = next((p for p in self.papers if p['path'] == paper_path), None)
            if paper:
                selected_papers.append(paper)
        
        if not selected_papers:
            return
        
        # 创建右键菜单
        menu = QMenu()
        action_text = f"删除选中的 {len(selected_papers)} 篇文献" if len(selected_papers) > 1 else "删除文献"
        delete_action = menu.addAction(action_text)
        delete_action.triggered.connect(lambda: self.delete_papers(selected_papers))
        menu.exec_(self.paper_list.viewport().mapToGlobal(pos))

    def delete_papers(self, papers_to_delete):
        # 确认对话框
        paper_names = [p['name'] for p in papers_to_delete]
        confirm_msg = f"确定要删除以下 {len(paper_names)} 篇文献吗？\n此操作将删除所有相关数据！\n\n" + "\n".join(paper_names)
        reply = QMessageBox.question(
            self, '确认删除', confirm_msg,
            QMessageBox.Yes | QMessageBox.No, QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        
        errors = []
        # 遍历删除每个文献
        for paper in papers_to_delete:
            try:
                # 删除本地文件
                files_to_delete = [
                    paper['content_path'],
                    paper['analysis_path'],
                    paper['chat_history_path'],
                    paper['notes_path']
                ]
                for file_path in files_to_delete:
                    if os.path.exists(file_path):
                        os.remove(file_path)
                
                # 从内存中移除
                if paper in self.papers:
                    self.papers.remove(paper)
                
                # 从列表控件中移除
                items = self.paper_list.findItems(paper['name'], Qt.MatchExactly)
                for item in items:
                    if item.data(Qt.UserRole) == paper['path']:
                        self.paper_list.takeItem(self.paper_list.row(item))
                        
            except Exception as e:
                errors.append(f"删除文献 {paper['name']} 失败：{str(e)}")
        
        # 检查当前显示的文献是否被删除
        deleted_paths = [p['path'] for p in papers_to_delete]
        if self.current_paper and self.current_paper['path'] in deleted_paths:
            self.current_paper = None
            self.pdf_viewer.load_pdf(None)
            self.analysis_display.clear()
            self.chat_history.clear()
            self.note_manager.set_paper(None)
        
        # 更新配置文件
        self.save_content()
        
        # 显示操作结果
        if errors:
            QMessageBox.warning(self, "删除完成", "删除过程中发生以下错误：\n" + "\n".join(errors))
        else:
            self.update_status(f"已成功删除 {len(papers_to_delete)} 篇文献")

    def create_detail_tab(self):
        tab = QWidget()
        layout = QVBoxLayout()
        
        self.content_display = QTextEdit()
        self.content_display.setReadOnly(True)
        # 启用Markdown高亮
        MarkdownHighlighter(self.content_display.document())
        layout.addWidget(QLabel("文献内容:"))
        layout.addWidget(self.content_display)
        
        self.analysis_display = QTextEdit()
        self.analysis_display.setReadOnly(True)
        # 应用Markdown渲染
        self.analysis_display.setAcceptRichText(True)
        MarkdownHighlighter(self.analysis_display.document())
        layout.addWidget(QLabel("分析结果:"))
        layout.addWidget(self.analysis_display)
        
        tab.setLayout(layout)
        return tab

    def handle_selected_text(self, text):
        """将选中文本填入输入框，并自动聚焦"""
        if text and self.current_paper:
            self.chat_input.setPlainText(text)
            self.chat_input.setFocus()
            # 确保滚动到输入框底部
            self.chat_input.ensureCursorVisible()
            # 自动滚动聊天历史到底部
            self.chat_history.ensureCursorVisible()

    def create_chat_tab(self):
        """完整的智能问答区域创建方法"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        
        # 聊天历史区域
        self.chat_history = QTextBrowser()

        
        # 输入区域容器
        input_container = QWidget()
        input_layout = QVBoxLayout(input_container)
        input_layout.setContentsMargins(16, 16, 16, 16)
        
        # 输入框
        self.chat_input = ChatTextEdit()  # 修改此处使用自定义控件
        self.chat_input.setPlaceholderText("输入您的问题（支持Markdown格式）...")
        # 连接自定义信号到发送方法
        self.chat_input.ctrlEnterPressed.connect(self.send_chat_message)
        
        # 按钮区域
        btn_layout = QHBoxLayout()
        self.clear_btn = QPushButton("清空记录")
        self.clear_btn.clicked.connect(self.clear_chat_history)
        self.send_btn = QPushButton("发送问题")
        self.send_btn.clicked.connect(self.send_chat_message)

        self.send_btn.setObjectName("send_btn")
        self.clear_btn.setObjectName("clear_btn")
        
        btn_layout.addWidget(self.clear_btn)
        btn_layout.addStretch()
        btn_layout.addWidget(self.send_btn)
        
        # 组装布局
        input_layout.addWidget(self.chat_input)
        input_layout.addLayout(btn_layout)
        
        # 最终布局
        layout.addWidget(self.chat_history)
        layout.addWidget(input_container)
        
        return tab
    
    def chat_input_key_press_event(self, event):
        """处理输入框的快捷键"""
        if event.key() == Qt.Key_Return and (event.modifiers() & Qt.ControlModifier):
            self.send_chat_message()
            event.accept()  # 确保事件被处理
        else:
            # 调用原有的事件处理
            QTextEdit.keyPressEvent(self.chat_input, event)
    
    # 新增清空聊天记录方法
    def clear_chat_history(self):
        if not self.current_paper:
            return
        
        reply = QMessageBox.question(
            self, '确认清空',
            '确定要清空当前聊天记录吗？此操作不可恢复。',
            QMessageBox.Yes | QMessageBox.No
        )
        if reply == QMessageBox.No:
            return
        
        # 清空界面显示
        self.chat_history.clear()
        
        # 清空内存数据
        self.current_paper['chat_history'] = []
        
        # 清空本地存储
        try:
            with open(self.current_paper['chat_history_path'], 'w', encoding='utf-8') as f:
                json.dump([], f, ensure_ascii=False, indent=2)
        except Exception as e:
            QMessageBox.critical(self, "保存错误", f"清空聊天记录失败: {str(e)}")
        
        self.update_status("聊天记录已清空")

    def import_papers(self):
        """优化的文献导入方法，支持快速去重和批量处理"""
        if not self.check_api_key():
            QMessageBox.warning(self, "警告", "请先在设置中配置API密钥")
            self.show_settings()
            return

        # 获取系统支持的所有PDF路径（自动过滤重复）
        files, _ = QFileDialog.getOpenFileNames(
            self, "选择文献文件", "",
            "PDF文件 (*.pdf);;文本文件 (*.txt);;所有文件 (*)"
        )

        if not files:
            return

        # 获取所有现有文献路径（内存级快速比对）
        existing_paths = {p['path'] for p in self.papers}  # 使用集合加速查找
        queued_paths = set(self.upload_queue)  # 当前队列中的路径
        
        # 快速过滤新文件（O(1)时间复杂度查找）
        new_files = [
            f for f in files 
            if f not in existing_paths and f not in queued_paths
        ]
        
        # 即时反馈过滤结果
        dup_count = len(files) - len(new_files)
        if dup_count > 0:
            self.update_status(f"自动跳过 {dup_count} 个重复文件")
            QApplication.processEvents()  # 强制刷新UI

        if not new_files:
            self.update_status("没有需要添加的新文献")
            return

        # 批量添加新文件到上传队列
        self.upload_queue.extend(new_files)
        
        # 可视化队列状态（优化大量文件时的显示）
        MAX_DISPLAY = 5  # 最多显示前5个文件名
        display_files = [os.path.basename(f) for f in new_files[:MAX_DISPLAY]]
        if len(new_files) > MAX_DISPLAY:
            display_files.append(f"等 {len(new_files)-MAX_DISPLAY} 个文件...")
        
        self.update_status(
            f"已添加 {len(new_files)} 个文件到处理队列：\n" + 
            "\n".join(f"· {name}" for name in display_files)
        )

        # 智能延迟处理（在主线程空闲时启动）
        if not self.upload_processing:
            QTimer.singleShot(100, self.process_next_upload)  # 100ms后启动
        else:
            # 实时更新队列进度
            self.status_bar.showMessage(
                f"队列运行中，新增 {len(new_files)} 个待处理文件...", 
                3000  # 3秒后自动清除
            )

        # 即时释放文件列表内存
        del files  
        del existing_paths
        del queued_paths

    def process_next_upload(self):
        """ 处理上传队列中的下一个文件 """
        if not self.upload_queue:
            self.upload_processing = False
            self._set_ui_interactive()
            return

        self.upload_processing = True
        self._set_ui_interactive()
        file_path = self.upload_queue.pop(0)

        # 跳过已存在的文件
        if any(p['path'] == file_path for p in self.papers):
            self.update_status(f"跳过重复文件: {os.path.basename(file_path)}")
            QTimer.singleShot(0, self.process_next_upload)  # 立即处理下一个
            return

        worker = FileUploadWorker(self.api_key, file_path)
        worker.upload_complete.connect(lambda data, name, is_local: self.handle_upload_success(data, name, is_local))
        worker.error_occurred.connect(self.handle_upload_error)
        worker.finished.connect(self.process_next_upload)
        worker.start()
        self.workers.append(worker)
        self.update_status(f"正在上传 {os.path.basename(file_path)}...")

    def handle_upload_success(self, file_data, paper_name, is_local):
        try:
            # 生成安全文件名用于本地存储
            safe_name = re.sub(r'[\\/*?:"<>|]', '_', paper_name)
            content_path = file_data['content_path']

            # 构建文献数据对象
            paper = {
                'name': paper_name,
                'path': file_data['path'],
                'content_path': content_path,
                'analysis_path': os.path.join(ANALYSIS_DIR, f"{safe_name}.txt"),
                'chat_history_path': os.path.join(ANALYSIS_DIR, f"{safe_name}_chat.json"),
                'notes_path': os.path.join(ANALYSIS_DIR, f"{safe_name}_notes.json"),
                'analysis': None,
                'chat_history': [],
                'notes': []
            }

            # 检查重复文献
            if any(p['path'] == paper['path'] for p in self.papers):
                self.update_status(f"⚠️ {paper_name} 已存在，跳过添加")
                return

            # 创建列表项
            item = QListWidgetItem(paper_name)
            item.setData(Qt.UserRole, paper['path'])
            self.paper_list.addItem(item)
            self.papers.append(paper)
            self.save_content()

            # 将分析任务加入队列
            self.analysis_queue.append(paper)
            if not self.analysis_processing:
                self.process_next_analysis()  # 此方法内部会更新状态
            status_msg = "本地解析完成，已加入分析队列" if is_local else "上传完成，已加入分析队列"
            self.update_status(f"✅ {paper_name} {status_msg}")
            
            # 如果没有正在进行的分析任务，启动队列处理
            if not self.analysis_processing:
                self.process_next_analysis()

        except Exception as e:
            error_msg = f"文献处理失败: {str(e)}"
            self.error_occurred.emit(error_msg)
            self.update_status(f"❌ {error_msg}")

    def process_next_analysis(self):
        """ 处理分析队列中的下一个任务 """
        if not self.analysis_queue:
            self.analysis_processing = False
            self._set_ui_interactive()
            return

        self.analysis_processing = True
        self._set_ui_interactive()
        paper = self.analysis_queue.pop(0)

        with open(paper['content_path'], 'r', encoding='utf-8') as f:
            content = f.read()

        worker = AnalysisWorker(self.api_key, content, paper['name'], paper['path'])
        worker.analysis_complete.connect(self.save_analysis_result)
        worker.error_occurred.connect(self.handle_analysis_error)
        worker.finished.connect(self.process_next_analysis)
        worker.start()
        self.workers.append(worker)
        self.update_status(f"开始分析 {paper['name']}...")

    def handle_upload_error(self, error):
        QMessageBox.critical(self, "上传错误", error)
        self.update_status("上传失败")
        # 新增以下两行
        self.upload_processing = False
        self._set_ui_interactive()

    def handle_analysis_error(self, error):
        QMessageBox.critical(self, "分析错误", error)
        self.update_status("分析失败")
        # 新增以下两行
        self.analysis_processing = False
        self._set_ui_interactive()

    def start_analysis(self, paper):
        with open(paper['content_path'], 'r', encoding='utf-8') as f:
            content = f.read()
        # 添加paper['path']作为第四个参数
        worker = AnalysisWorker(self.api_key, content, paper['name'], paper['path'])
        worker.analysis_complete.connect(self.save_analysis_result)
        worker.error_occurred.connect(self.handle_analysis_error)
        worker.start()
        self.workers.append(worker)
        self.update_status(f"开始分析 {paper['name']}...")

    def save_analysis_result(self, result, paper_name, paper_path):
        # 根据路径和名称查找文献
        target_paper = next((p for p in self.papers if p['name'] == paper_name and p['path'] == paper_path), None)
        if not target_paper:
            return
        
        # 写入分析结果到指定路径
        with open(target_paper['analysis_path'], 'w', encoding='utf-8') as f:
            f.write(result)
        target_paper['analysis'] = result
        
        # 更新当前显示
        if self.current_paper and self.current_paper['path'] == paper_path:
            self.analysis_display.setHtml(self._format_markdown(result))
        self.save_content()
        self.update_status(f"{paper_name} 分析完成")
        if not self.analysis_processing:
            self.process_next_analysis()  # 此方法内部会更新状态

    def show_paper_details(self, item):
        paper_path = item.data(Qt.UserRole)  # 获取存储的路径
        self.current_paper = next(p for p in self.papers if p['path'] == paper_path)
            
        # 加载PDF文件到阅读器
        self.pdf_viewer.load_pdf(self.current_paper['path'])
        
        # 确保分析结果已加载
        if os.path.exists(self.current_paper['analysis_path']):
            try:
                with open(self.current_paper['analysis_path'], 'r', encoding='utf-8') as f:
                    self.current_paper['analysis'] = f.read()
            except Exception as e:
                self.current_paper['analysis'] = f"分析结果加载失败：{str(e)}"
        
        # 确保分析结果已加载（新增自动生成逻辑）
        if not self.current_paper.get('analysis') or not os.path.exists(self.current_paper['analysis_path']):
            self.start_analysis(self.current_paper)
            self.analysis_display.setPlainText("分析加载中...")
        else:
            self.analysis_display.setHtml(self._format_markdown(self.current_paper['analysis']))
        
        # 加载聊天记录
        self.chat_history.clear()
        if os.path.exists(self.current_paper['chat_history_path']):
            try:
                with open(self.current_paper['chat_history_path'], 'r', encoding='utf-8') as f:
                    self.current_paper['chat_history'] = json.load(f)
                    for msg in self.current_paper['chat_history']:
                        role_tag = msg.get('type')  # 获取保存的消息类型
                        if role_tag == '翻译结果':
                            self.append_chat_message(msg['role'], msg['content'], save=False, role_tag=role_tag)
                        elif role_tag == '翻译请求':
                            self.append_chat_message(msg['role'], msg['content'], save=False, role_tag=role_tag)
                        else:
                            self.append_chat_message(msg['role'], msg['content'], save=False)
            except Exception as e:
                print(f"加载聊天记录失败: {e}")

        self.note_manager.set_paper(self.current_paper)
        # 加载笔记数据
        self.load_notes(self.current_paper)
        # 刷新PDF显示
        self.pdf_viewer.update()

    # 添加保存和加载笔记的方法
    def save_notes(self, paper):
        try:
            with open(paper['notes_path'], 'w', encoding='utf-8') as f:
                json.dump(paper['notes'], f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"保存笔记失败: {e}")

    def load_notes(self, paper):
        if os.path.exists(paper['notes_path']):
            try:
                with open(paper['notes_path'], 'r', encoding='utf-8') as f:
                    paper['notes'] = json.load(f)
            except Exception as e:
                print(f"加载笔记失败: {e}")

    def _format_markdown(self, text):
        # 去除代码块标记
        text = re.sub(r'^```markdown\s*', '', text, flags=re.MULTILINE | re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text, flags=re.MULTILINE | re.IGNORECASE)
        # 转换Markdown为HTML并转义特殊字符
        html_text = markdown(html.escape(text))
        # 添加自定义样式
        return html_text.replace('<code>', '<code style="background-color: #F3F3F3; padding: 2px 4px; border-radius: 3px;">">')

    def _role_bg_color(self, role):
        return {
            "user": "#E3F2FD",
            "assistant": "#E8F5E9",
            "system": "#F5F5F5"
        }[role]
    
    def _append_translating_message(self):
        """添加翻译中的动画消息"""
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # 创建动画容器
        animation_html = """
        <div style='margin: 16px 0; padding: 12px; 
            background: #F8F9FA; border-radius: 8px;
            display: flex; align-items: center;'>
            <div class="dot-flashing"></div>
            <span style='color: #666; margin-left: 12px;'>正在翻译...</span>
        </div>
        """
        cursor.insertHtml(animation_html)
        
        # 确保动画样式存在
        self.chat_history.document().setDefaultStyleSheet("""
            .dot-flashing {
                position: relative;
                width: 10px;
                height: 10px;
                border-radius: 5px;
                background-color: #007ACC;
                color: #007ACC;
                animation: dotFlashing 1s infinite linear;
            }
            @keyframes dotFlashing {
                0% { opacity: 0.2; }
                50% { opacity: 1; }
                100% { opacity: 0.2; }
            }
        """)
        self.chat_history.ensureCursorVisible()

    def append_chat_message(self, role, content, save=True, role_tag=None):
        """增强的消息显示方法，支持翻译标识和样式"""
        # 内容预处理
        content = html.escape(content).encode('utf-8', 'ignore').decode('utf-8')
        
        # 角色特征配置（新增translator角色）
        role_settings = {
            "user": {
                "color": "#1976D2",
                "icon": "👤",
                "bg": "#E3F2FD",
                "border": "#BBDEFB"
            },
            "assistant": {
                "color": "#388E3C",
                "icon": "🤖",
                "bg": "#E8F5E9",
                "border": "#C8E6C9"
            },
            "system": {
                "color": "#6D6D6D",
                "icon": "⚙️",
                "bg": "#F5F5F5",
                "border": "#EEEEEE"
            },
            "translator": {
                "color": "#1A237E",
                "icon": "🌐",
                "bg": "#E8EAF6",
                "border": "#9FA8DA"
            }
        }

        # 动态调整角色显示
        display_role = role
        if role_tag == "翻译请求":
            cfg = role_settings["user"].copy()
            cfg.update({
                "icon": "🔤",
                "color": "#0D47A1",
                "border": "#BBDEFB"
            })
            display_role = "翻译请求"
        elif role_tag == "翻译结果":
            cfg = role_settings["translator"]
            display_role = "翻译结果"
        else:
            cfg = role_settings.get(role, role_settings["assistant"])

        # 构建消息模板（优化样式细节）
        message_html = f"""
        <div style='
            box-sizing: border-box;
            margin: 16px 0;
            position: relative;
            width: 100%;
            max-width: 100%;
            left: 0;
            right: 0;
        '>
            <!-- 角色标识容器 -->
            <div style='
                box-sizing: border-box;
                margin: 0 0 4px 0;
                padding: 0;
                display: flex;
                align-items: center;
                gap: 8px;
                width: 100%;
                max-width: 100%;
                justify-content: flex-start;
            '>
            <hr style='visibility: hidden;'>
                <span style='
                    box-sizing: border-box;
                    display: inline-block;
                    background: {cfg['bg']};
                    border-radius: 16px;
                    padding: 4px 12px;
                    color: {cfg['color']};
                    font-weight: 500;
                    font-size: 0.9em;
                    border: 1px solid {cfg['border']};
                    box-shadow: 0 2px 3px rgba(0,0,0,0.05);
                    width: max-content;
                    max-width: 100%;
                '>
                    {cfg['icon']} {display_role}
                </span>
            </div>

            <!-- 内容容器 -->
            <div style='
                box-sizing: border-box;
                background: {cfg['bg']};
                border-radius: 8px;
                padding: 16px;
                margin: 0;
                width: 100%;
                box-sizing: border-box;
                position: relative;
                box-shadow: 0 2px 4px rgba(0,0,0,0.05);
                border-left: 3px solid {cfg['color']};
            '>
                <!-- 内容边界控制 -->
                <div style='
                    box-sizing: border-box;
                    color: #263238;
                    line-height: 1.6;
                    font-size: 15px;
                    white-space: pre-wrap;
                    word-break: break-word;
                    overflow-wrap: anywhere;
                    font-family: "Microsoft YaHei", sans-serif;
                    width: 100%;
                    max-width: 100%;
                '>
                    {markdown(content)}
                </div>
            </div>
        </div>
        """

        # 插入消息
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        cursor.insertHtml(message_html)
        cursor.insertHtml("<hr style='visibility: hidden;'>")

        # 保存逻辑
        if save and self.current_paper:
            self.current_paper['chat_history'].append({
                'role': role,
                'content': content,
                'type': role_tag or 'normal'  # 记录消息类型
            })
            try:
                with open(self.current_paper['chat_history_path'], 'w', encoding='utf-8') as f:
                    json.dump(self.current_paper['chat_history'], f, ensure_ascii=False, indent=2)
            except Exception as e:
                print(f"保存聊天记录失败: {e}")

        # 自动滚动并刷新界面
        self.chat_history.ensureCursorVisible()
        QApplication.processEvents()

    def _append_thinking_message(self):
        """添加思考中的动画消息"""
        cursor = self.chat_history.textCursor()
        cursor.movePosition(QTextCursor.End)
        
        # 创建动画容器
        animation_html = """
        <div style='margin: 16px 0; padding: 12px; 
            background: #F8F9FA; border-radius: 8px;
            display: flex; align-items: center;'>
            <div class="dot-flashing"></div>
            <span style='color: #666; margin-left: 12px;'>正在思考中...</span>
        </div>
        """
        cursor.insertHtml(animation_html)
        
        # 添加自定义CSS动画
        self.chat_history.document().setDefaultStyleSheet("""
            .dot-flashing {
                position: relative;
                width: 10px;
                height: 10px;
                border-radius: 5px;
                background-color: #007ACC;
                color: #007ACC;
                animation: dotFlashing 1s infinite linear;
            }
            @keyframes dotFlashing {
                0% { opacity: 0.2; }
                50% { opacity: 1; }
                100% { opacity: 0.2; }
            }
        """)
        self.chat_history.ensureCursorVisible()
        return cursor.position()

    def send_chat_message(self):
        # 状态检测（防止重复提交）
        if not self.send_btn.isEnabled():
            QMessageBox.warning(self, "操作提示", "已有请求正在处理，请稍后")
            return

        # 基础校验
        if not self.check_api_key():
            self.show_settings()
            return
        if not self.current_paper or not self.chat_input.toPlainText().strip():
            return
        
        # 校验逻辑
        self.chat_processing = True
        self._set_ui_interactive()
        
        try:
            # 消息处理流程
            question = self.chat_input.toPlainText().strip()
            self._append_user_message(question)
            self.chat_input.clear()
            
            # 启动工作线程
            worker = ChatWorker(
                self.api_key,
                self.current_paper['content_path'],
                question
            )
            worker.response_received.connect(self._handle_success_response)
            worker.error_occurred.connect(self._handle_error_response)
            worker.finished.connect(self.on_chat_worker_finished)
            worker.start()
            self.workers.append(worker)
            
            # 更新界面状态
            self._append_thinking_message()  # 在聊天历史中添加思考提示
            
        except Exception as e:
            self.chat_processing = False  # 处理完成后重置状态
            self._set_ui_interactive()
            self._handle_error_response(str(e))

    def on_chat_worker_finished(self):
        self.chat_processing = False
        self._set_ui_interactive()

    def _append_user_message(self, content):
        """专用方法：添加用户消息到聊天记录"""
        self.append_chat_message(
            role="user",
            content=content,
            save=True
        )
        
        # 自动滚动到底部
        self.chat_history.ensureCursorVisible()
        
        # 更新界面状态
        self.send_btn.setEnabled(False)
        self.clear_btn.setEnabled(False)
        QApplication.processEvents()  # 强制刷新界面

    def _append_assistant_message(self, content):
        """添加AI回复的专用方法"""
        self.append_chat_message(
            role="assistant",
            content=content,
            save=True
        )

    def _append_system_message(self, content):
        """添加系统消息的专用方法""" 
        self.append_chat_message(
            role="system",
            content=content,
            save=True
        )

    def enable_buttons(self):
        """统一恢复按钮状态"""
        self.send_btn.setEnabled(True)
        self.clear_btn.setEnabled(True)
        self.update_status("就绪")  # 使用状态栏显示状态

    def _set_ui_interactive(self):
        """统一管理界面交互状态，考虑上传、分析和聊天三种状态"""
        enable = not (self.upload_processing or self.analysis_processing or self.chat_processing)
        
        # 设置控件可用性
        self.send_btn.setEnabled(enable)
        self.clear_btn.setEnabled(enable)
        self.chat_input.setReadOnly(not enable)

    def _handle_success_response(self, result):
        """成功响应处理"""
        try:
            # 删除加载动画
            self._remove_thinking_message()
            
            # 添加AI回复
            self._append_assistant_message(result['content'])
            
            # 滚动到底部
            self.chat_history.ensureCursorVisible()
            
        finally:
            self.update_status("请求处理完成")  # 使用状态栏显示状态

    def _handle_error_response(self, error_msg):
        """错误处理"""
        try:
            self._remove_thinking_message()
            self._append_system_message(f"请求失败：{error_msg}")
            QMessageBox.critical(self, "操作异常", error_msg)
        finally:
            self.update_status("请求处理失败")  # 使用状态栏显示状态
            self.chat_processing = False  # 重置状态变量
            self._set_ui_interactive()

    def _remove_thinking_message(self):
        """改进的提示消息清除方法（主动添加换行）"""
        cursor = self.chat_history.textCursor()
        
        # 定位到文档末尾
        cursor.movePosition(QTextCursor.End)
        
        # 删除整个提示块（保留原换行符）
        cursor.movePosition(QTextCursor.PreviousBlock, QTextCursor.KeepAnchor)
        cursor.removeSelectedText()
        
        # 主动插入换行符（使用段落分隔更可靠）
        cursor.insertHtml("<hr style='visibility: hidden;'>")

    def show_settings(self):
        dialog = SettingsDialog(self)
        dialog.set_api_key(self.api_key)
        if dialog.exec_() == QDialog.Accepted:
            self.api_key = dialog.get_api_key()
            self.content['api_key'] = self.api_key
            self.save_content()
            self.update_status("API密钥已更新")

    def check_api_key(self):
        return bool(self.api_key)

    def update_status(self, message):
        self.status_bar.showMessage(message)

    def closeEvent(self, event):
        # 先停止接受新请求
        self.upload_queue.clear()
        self.analysis_queue.clear()
        
        # 终止所有工作线程
        for worker in self.workers:
            if worker.isRunning():
                worker.stop()  # 使用改进的stop方法
                
        # 等待所有线程结束（最多3秒）
        start_time = time.time()
        while any(w.isRunning() for w in self.workers) and time.time()-start_time < 3:
            QApplication.processEvents()
        
        # 强制终止残留线程
        for worker in self.workers:
            if worker.isRunning():
                worker.terminate()
                
        self.save_content()
        event.accept()