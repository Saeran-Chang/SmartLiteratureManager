import os
import re
import requests
import fitz  # PyMuPDF
from Workers.BaseWorker import BaseWorker
from Config.Config import MOONSHOT_API, ANALYSIS_DIR
from PyQt5.QtCore import pyqtSignal

class FileUploadWorker(BaseWorker):
    upload_complete = pyqtSignal(dict, str, bool)  # (file_data, paper_name, is_local)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key, file_path):
        super().__init__()
        self.api_key = api_key
        self.file_path = file_path
        self.paper_name = os.path.basename(file_path)

    def refine_content(self, content):
        """调用Kimi API进行内容精简（保留API调用）"""
        try:
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }
            messages = [
                {
                    "role": "system",
                    "content": "你是一个学术助手，请帮助处理以下内容："
                               "1. 移除参考文献、致谢、附录等非核心内容\n"
                               "2. 保留摘要、方法、结果等核心部分\n"
                               "3. 保持原文格式中的标题结构\n"
                               "4. 确保关键数据和研究内容的完整性\n"
                               "5. 用简洁的语言输出处理后的内容，语言与原论文保持一致"
                },
                {
                    "role": "user",
                    "content": content
                }
            ]
            response = requests.post(
                f"{MOONSHOT_API}/chat/completions",
                headers=headers,
                json={
                    "model": "moonshot-v1-128k",
                    "messages": messages,
                    "temperature": 0.3,
                    "max_tokens": 2000
                },
                timeout=60
            )
            if response.status_code == 200:
                return response.json()['choices'][0]['message']['content']
            return content[:2000]  # 失败时返回原始内容的前两千字符
        except Exception as e:
            return content[:2000]

    def run(self):
        try:
            # 直接进行本地文件解析，跳过API上传
            self.handle_upload_failure()
        except Exception as e:
            # 本地处理失败时发送错误信号
            self.error_occurred.emit(f"文件处理错误: {str(e)}")

    def handle_upload_failure(self):
        """处理本地PDF解析"""
        try:
            # 使用PyMuPDF提取文本
            doc = fitz.open(self.file_path)
            text = ""
            for page in doc:
                text += page.get_text()
            processed_content = self.refine_content(text)
            
            # 生成保存路径
            safe_name = re.sub(r'[\\/*?:"<>|]', '_', self.paper_name)
            content_path = os.path.join(ANALYSIS_DIR, f"{safe_name}_content.txt")
            
            # 保存处理后的内容
            with open(content_path, 'w', encoding='utf-8-sig') as f:
                f.write(processed_content)
            
            # 构造与API成功时相同结构的数据
            file_data = {
                'id': 'local_processed',  # 标识为本地处理
                'content': processed_content,
                'path': self.file_path,
                'filename': self.paper_name,
                'content_path': content_path
            }
            self.upload_complete.emit(file_data, self.paper_name, True)
        except Exception as e:
            self.error_occurred.emit(f"本地处理失败: {str(e)}")