from PyQt5.QtCore import QThread

class BaseWorker(QThread):
    def __init__(self):
        super().__init__()
        self._is_running = True  # 运行状态标志
        
    def stop(self):
        """设置停止标志并等待线程结束"""
        self._is_running = False
        self.quit()

    def is_running(self):
        """中断检查核心方法"""
        return self._is_running