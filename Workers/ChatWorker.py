import requests
from Workers.BaseWorker import BaseWorker
from Config.Config import MOONSHOT_API
from PyQt5.QtCore import pyqtSignal

class ChatWorker(BaseWorker):
    response_received = pyqtSignal(dict)  # 发送{'role': str, 'content': str}
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key, content_path, question, is_translation=False):
        super().__init__()
        self.api_key = api_key
        self.content_path = content_path
        self.question = question
        self.is_translation = is_translation  # 新增翻译标识

    def run(self):
        try:
            if not self.is_running():
                return
            headers = {
                'Authorization': f'Bearer {self.api_key}',
                'Content-Type': 'application/json'
            }

            # 修改此处开始 
            if self.is_translation:
                # 构造翻译专用消息结构
                messages = [
                    {
                        "role": "system",
                        "content": "你是一个专业的学术翻译助手，专注于准确翻译英文学术内容到中文。"
                                "请严格遵循以下规则："
                                "1. 保留专业术语的英文原文（括号内添加中文翻译）"
                                "2. 保持原有格式符号（如标号、Markdown标记等）"
                                "3. 使用学术书面语言"
                                "4. 禁止添加额外解释或内容"
                                "5. 严格保持原有标号结构，不得自动延续或添加新标号"
                                "6. 当遇到数字标号时，仅翻译对应内容，不要修改标号本身"
                    },
                    {
                        "role": "user",
                        "content": self.question  # 包含待翻译的文本
                    }
                ]
            else:
                # 原有逻辑：读取文献内容
                with open(self.content_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                messages = [
                    {"role": "system", "content": content},
                    {"role": "user", "content": self.question}
                ]
            # 修改结束

            response = requests.post(
                f"{MOONSHOT_API}/chat/completions",
                headers=headers,
                json={
                    "model": "moonshot-v1-128k",
                    "messages": messages,
                    "temperature": 0.0,  # 更确定性的输出
                    "top_p": 0.1,
                    "max_tokens": 4096  # 限制最大输出长度
                },
                timeout=60
            )

            if response.status_code == 200:
                answer = response.json()['choices'][0]['message']['content']
                self.response_received.emit({
                    'role': 'assistant',
                    'content': answer
                })
            else:
                self.error_occurred.emit(f"API请求失败: {response.text}")

        except requests.exceptions.Timeout:
            self.error_occurred.emit("请求超时，请检查网络连接")
        except Exception as e:
            self.error_occurred.emit(f"发生未知错误: {str(e)}")