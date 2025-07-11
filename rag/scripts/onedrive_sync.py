#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
OneDrive同步脚本
用于定时同步OneDrive文件到知识库
"""

import os
import sys
import logging
import time
from datetime import datetime

# 添加项目根目录到Python路径
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(os.path.dirname(current_dir))
sys.path.insert(0, project_root)

from api.db.services.onedrive_sync_service import run_onedrive_sync

# 确保日志目录存在
log_dir = "/var/log/ragflow"
if not os.path.exists(log_dir):
    try:
        os.makedirs(log_dir)
    except Exception:
        log_dir = current_dir

# 设置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(os.path.join(log_dir, "onedrive_sync.log")),
        logging.StreamHandler()
    ]
)

logger = logging.getLogger(__name__)

def main():
    """主函数，执行OneDrive同步"""
    try:
        logger.info("开始执行OneDrive同步任务")
        
        # 记录开始时间
        start_time = time.time()
        
        # 执行同步
        run_onedrive_sync()
        
        # 计算执行时间
        duration = time.time() - start_time
        logger.info(f"OneDrive同步任务完成，耗时 {duration:.2f} 秒")
        
    except Exception as e:
        logger.exception(f"OneDrive同步任务执行失败: {str(e)}")

if __name__ == "__main__":
    main() 