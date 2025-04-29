import re
import time
import requests
from Workers.BaseWorker import BaseWorker
from Config.Config import MOONSHOT_API
from PyQt5.QtCore import pyqtSignal

class AnalysisWorker(BaseWorker):
    analysis_complete = pyqtSignal(str, str, str)  # (result, paper_name, paper_path)
    error_occurred = pyqtSignal(str)

    def __init__(self, api_key, file_content, paper_name, paper_path):
        super().__init__()
        self.api_key = api_key
        self.file_content = file_content
        self.paper_name = paper_name
        self.paper_path = paper_path
        self.max_retries = 10  # 最大重试次数
        self.retry_delay = 2  # 初始重试延迟(秒)
        self.timeout = 30  # 请求超时时间

    def run(self):
        attempt = 0
        last_error = ""
        
        while attempt < self.max_retries:
            try:
                if not self.is_running():
                    return
                # 确保请求间隔
                if attempt > 0:
                    time.sleep(self.retry_delay * (2 ** (attempt-1)))

                response = self._make_api_request()
                
                # 处理速率限制错误
                if response.status_code == 429:
                    raise requests.exceptions.RequestException(
                        f"Rate limit exceeded. Retry after {response.headers.get('Retry-After', 60)} seconds"
                    )
                
                # 处理其他错误状态码
                if response.status_code != 200:
                    error_msg = f"API Error [{response.status_code}]: {response.text[:200]}"
                    raise requests.exceptions.HTTPError(error_msg)

                # 成功处理
                result = response.json()['choices'][0]['message']['content']
                self.analysis_complete.emit(result, self.paper_name, self.paper_path)
                return

            except requests.exceptions.RequestException as e:
                last_error = str(e)
                attempt += 1
                if 'Rate limit' in last_error and 'Retry-After' in last_error:
                    # 从错误信息中提取建议等待时间
                    retry_after = int(re.search(r'(\d+) seconds', last_error).group(1))
                    time.sleep(retry_after + 10)  # 比建议时间多10秒
                continue
                
            except Exception as e:
                last_error = str(e)
                self.error_occurred.emit(f"Unexpected error: {last_error}")
                break

        # 所有重试失败后
        self.error_occurred.emit(f"Analysis failed after {self.max_retries} attempts. Final error: {last_error}")

    def _make_api_request(self):
        """封装API请求逻辑"""
        headers = {
            'Authorization': f'Bearer {self.api_key}',
            'Content-Type': 'application/json'
        }

        messages = [
            {
                "role": "system",
                "content": "你是一个专业的学术研究助理，请严格按照以下结构分析文献：\n"
                           "1. 研究背景（200字）\n2. 研究方法（300字）\n"
                           "3. 主要发现（300字）\n4. 创新点（200字）\n"
                           "5. 局限性与展望（200字）"
            },
            {
                "role": "system",
                "content": self.file_content
            },
            {
                "role": "user",
                "content": "请用中文分点详细分析这篇文献，使用Markdown格式"
            }
        ]

        return requests.post(
            f"{MOONSHOT_API}/chat/completions",
            headers=headers,
            json={
                "model": "moonshot-v1-128k",
                "messages": messages,
                "temperature": 0.3,
                "max_tokens": 1000
            },
            timeout=self.timeout
        )