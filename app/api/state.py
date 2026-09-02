"""API 层共享运行时状态：模块级 API Key 与自动化工作线程单例。"""

from ..automation import AutomationWorker

RUNTIME_API_KEY = ""

AUTOMATION_WORKER = AutomationWorker(lambda: RUNTIME_API_KEY)
