# 同步状态管理模块
# 用于避免循环导入问题

# 存储正在同步的知识库ID及其同步类型
SYNCING_KNOWLEDGE_BASES = {}  # {kb_id: {"type": "onedrive|outlook", "task": thread_obj}}