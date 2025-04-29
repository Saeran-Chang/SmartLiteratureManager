import time
import fitz  # PyMuPDF
from PyQt5.QtWidgets import (QWidget, QVBoxLayout, QHBoxLayout,
                            QPushButton, QTextEdit, QListWidget,
                            QListWidgetItem)
from PyQt5.QtCore import Qt

class NoteManagementWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.parent = parent  # LiteratureManager实例
        self.current_paper = None
        self.current_rect = None
        self.current_page = -1
        self.init_ui()

    def init_ui(self):
        layout = QVBoxLayout(self)
        
        # 笔记列表
        self.notes_list = QListWidget()
        self.notes_list.itemDoubleClicked.connect(self.edit_note)
        layout.addWidget(self.notes_list)
        
        # 编辑区域
        self.note_edit = QTextEdit()
        self.note_edit.setPlaceholderText("输入笔记内容...")
        layout.addWidget(self.note_edit)
        
        # 按钮布局
        btn_layout = QHBoxLayout()
        self.save_btn = QPushButton("保存")
        self.save_btn.clicked.connect(self.save_note)
        self.delete_btn = QPushButton("删除")
        self.delete_btn.clicked.connect(self.delete_note)
        btn_layout.addWidget(self.delete_btn)
        btn_layout.addWidget(self.save_btn)
        
        layout.addLayout(btn_layout)
    
    def set_paper(self, paper):
        self.current_paper = paper
        self.load_notes()
    
    def load_notes(self):
        self.notes_list.clear()
        if self.current_paper:
            self.parent.load_notes(self.current_paper)  # 加载笔记数据
            for note in self.current_paper.get('notes', []):
                item = QListWidgetItem(f"P{note['page']+1}: {note['content'][:30]}")
                item.setData(Qt.UserRole, note)
                self.notes_list.addItem(item)
    
    def create_new_note(self, page, pdf_rect):
        self.current_page = page
        self.current_rect = pdf_rect
        self.note_edit.clear()
        self.note_edit.setFocus()
    
    def save_note(self):
        content = self.note_edit.toPlainText().strip()
        if not content or not self.current_paper:
            return
        
        new_note = {
            'id': str(time.time()),
            'page': self.current_page,
            'rect': {
                'x0': self.current_rect.x0,
                'y0': self.current_rect.y0,
                'x1': self.current_rect.x1,
                'y1': self.current_rect.y1
            },
            'content': content
        }
        
        # 更新或添加笔记
        self.current_paper['notes'].append(new_note)
        self.parent.save_notes(self.current_paper)
        self.load_notes()
    
    def delete_note(self):
        selected = self.notes_list.currentItem()
        if not selected or not self.current_paper:
            return
        note = selected.data(Qt.UserRole)
        self.current_paper['notes'] = [n for n in self.current_paper['notes'] if n['id'] != note['id']]
        self.parent.save_notes(self.current_paper)
        self.load_notes()
    
    def edit_note(self, item):
        note = item.data(Qt.UserRole)
        self.current_page = note['page']
        self.current_rect = fitz.Rect(note['rect']['x0'], note['rect']['y0'], note['rect']['x1'], note['rect']['y1'])
        self.note_edit.setPlainText(note['content'])