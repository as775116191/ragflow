#!/usr/bin/env python3
# -*- coding: utf-8 -*-
#
#  Copyright 2025 The InfiniFlow Authors. All Rights Reserved.
#
#  Licensed under the Apache License, Version 2.0 (the "License");
#  you may not use this file except in compliance with the License.
#  You may obtain a copy of the License at
#
#      http://www.apache.org/licenses/LICENSE-2.0
#
#  Unless required by applicable law or agreed to in writing, software
#  distributed under the License is distributed on an "AS IS" BASIS,
#  WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
#  See the License for the specific language governing permissions and
#  limitations under the License.
#

import os
import sys
import asyncio
import base64
import logging
import tempfile
from datetime import datetime, timedelta
import configparser

# 设置日志格式
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("outlook_sync")

# 添加项目根目录到路径
current_dir = os.path.dirname(os.path.abspath(__file__))
root_dir = os.path.abspath(os.path.join(current_dir, '..', '..'))
sys.path.append(root_dir)

from api.db.db_models import Knowledgebase
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.file_service import FileService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.task_service import queue_tasks
from api.db import StatusEnum, FileSource, TaskStatus
from api.utils import get_uuid
from api.db.services.document_service import DocumentService
from rag.utils.storage_factory import STORAGE_IMPL
from api.db.services.user_service import UserService
from api.db.services import graph_server

def load_azure_config():
    """加载Microsoft Graph API的配置"""
    config_path = os.path.join(root_dir, 'config.cfg')
    alt_config_path = os.path.join(root_dir, 'config.dev.cfg')
    
    config = configparser.ConfigParser()
    if os.path.exists(config_path):
        config.read(config_path)
    elif os.path.exists(alt_config_path):
        config.read(alt_config_path)
    else:
        # 使用环境变量
        logger.info("配置文件不存在，尝试使用环境变量")
        config['azure'] = {
            'clientId': os.environ.get('AZURE_CLIENT_ID', ''),
            'tenantId': os.environ.get('AZURE_TENANT_ID', ''),
            'clientSecret': os.environ.get('AZURE_CLIENT_SECRET', '')
        }
    
    if 'azure' not in config:
        config['azure'] = {}
        logger.warning("Azure配置不存在，将使用空配置")
    
    return config['azure']

def get_kb_to_sync():
    """获取所有启用了Outlook同步的知识库"""
    try:
        # 获取所有有效的知识库
        kbs = KnowledgebaseService.query(status=StatusEnum.VALID.value)
        
        # 筛选出启用了Outlook同步的知识库
        sync_enabled_kbs = []
        for kb in kbs:
            parser_config = kb.parser_config or {}
            if parser_config.get("outlook_sync_enabled", False):
                sync_enabled_kbs.append(kb)
        
        return sync_enabled_kbs
    except Exception as e:
        logger.error(f"获取知识库时出错: {str(e)}")
        return []

async def sync_kb_emails(kb, graph):
    """同步特定知识库的邮件"""
    try:
        parser_config = kb.parser_config or {}
        
        # 获取邮箱和文件夹
        outlook_email = parser_config.get("outlook_email")
        outlook_folder = parser_config.get("outlook_folder")
        
        if not outlook_email or not outlook_folder:
            logger.error(f"知识库 '{kb.name}' (ID: {kb.id}) 的Outlook配置不完整")
            return 0
        
        # 获取上次同步时间
        last_sync_str = parser_config.get("outlook_last_sync")
        since_datetime = None
        
        if last_sync_str:
            try:
                # 尝试将ISO格式字符串转换为datetime对象
                last_sync = datetime.fromisoformat(last_sync_str.replace('Z', '+00:00'))
                # 格式化为ISO 8601格式
                since_datetime = last_sync.strftime("%Y-%m-%dT%H:%M:%SZ")
                logger.info(f"开始同步知识库 '{kb.name}' (ID: {kb.id})，获取 {since_datetime} 之后的邮件")
            except Exception as e:
                logger.error(f"解析上次同步时间出错: {str(e)}，将获取所有邮件")
                since_datetime = None
        else:
            logger.info(f"开始同步知识库 '{kb.name}' (ID: {kb.id})，首次同步，将获取所有邮件")
        
        # 获取用户信息
        e, user = UserService.get_by_id(kb.created_by)
        if not e or not user:
            logger.error(f"找不到知识库创建者 (ID: {kb.created_by})")
            return 0
        
        # 获取邮件
        result = await graph.get_messages_as_eml_by_email_and_folder(
            outlook_email, 
            outlook_folder,
            since_datetime  # 如果为None，将获取所有邮件
        )
        
        if result.get("error"):
            logger.error(f"获取邮件时出错: {result['error']}")
            return 0
        
        eml_messages = result.get("eml_messages", [])
        logger.info(f"获取到 {len(eml_messages)} 封{'' if since_datetime else '所有'}邮件")
        
        if not eml_messages:
            # 更新同步时间
            parser_config["outlook_last_sync"] = datetime.utcnow().isoformat()
            KnowledgebaseService.update_by_id(kb.id, {
                "parser_config": parser_config
            })
            return 0
        
        # 处理所有邮件
        email_count = 0
        for message in eml_messages:
            try:
                # 提取邮件信息
                subject = message.get("subject", "无主题")
                received_date = message.get("received_date", "")
                message_id = message.get("id", "")
                eml_base64 = message.get("eml_base64", "")
                
                if not eml_base64:
                    logger.warning(f"邮件 '{subject}' 没有内容，跳过")
                    continue
                
                # 生成文件名
                date_str = ""
                if received_date:
                    try:
                        # 尝试将ISO格式日期转换为更友好的格式
                        dt = datetime.fromisoformat(received_date.replace('Z', '+00:00'))
                        date_str = dt.strftime("%Y%m%d")
                    except:
                        pass
                
                if date_str:
                    filename = f"{date_str}_{subject}.eml"
                else:
                    filename = f"{subject}.eml"
                
                # 限制文件名长度
                if len(filename) > 200:
                    filename = filename[:196] + ".eml"
                
                # 过滤非法字符
                filename = ''.join(c for c in filename if c.isalnum() or c in '._- ')
                
                logger.info(f"处理邮件: {filename}")
                
                # 解码EML内容
                eml_data = base64.b64decode(eml_base64)
                
                # 创建临时文件
                with tempfile.NamedTemporaryFile(suffix='.eml', delete=False) as temp_file:
                    temp_path = temp_file.name
                    temp_file.write(eml_data)
                
                try:
                    # 上传文件到存储
                    file_id = get_uuid()
                    storage_path = f"file/{kb.tenant_id}/{file_id}.eml"
                    STORAGE_IMPL.write(storage_path, eml_data)
                    
                    # 添加文件记录
                    file_data = {
                        "id": file_id,
                        "parent_id": "0",
                        "tenant_id": kb.tenant_id,
                        "created_by": kb.created_by,
                        "name": filename,
                        "location": storage_path,
                        "size": len(eml_data),
                        "type": "eml",
                        "source_type": FileSource.KNOWLEDGEBASE.value
                    }
                    FileService.save(**file_data)
                    
                    # 创建文档记录
                    doc_id = get_uuid()
                    doc_data = {
                        "id": doc_id,
                        "kb_id": kb.id,
                        "parser_id": "email",  # 使用email解析器
                        "parser_config": kb.parser_config,
                        "source_type": "outlook",
                        "type": "eml",
                        "created_by": kb.created_by,
                        "name": filename,
                        "location": storage_path,
                        "size": len(eml_data),
                        "run": TaskStatus.UNSTART.value  # 设置为未开始状态
                    }
                    DocumentService.save(**doc_data)
                    
                    # 关联文件和文档
                    f2d_data = {
                        "id": get_uuid(),
                        "file_id": file_id,
                        "document_id": doc_id,
                        "kb_id": kb.id
                    }
                    File2DocumentService.save(**f2d_data)
                    
                    # 创建解析任务
                    try:
                        # 获取存储地址
                        bucket, name = File2DocumentService.get_storage_address(doc_id=doc_id)
                        
                        # 创建解析任务
                        queue_tasks(doc_data, bucket, name, 0)
                        logger.info(f"成功创建解析任务: {filename}")
                    except Exception as e:
                        logger.error(f"创建解析任务失败: {str(e)}")
                    
                    email_count += 1
                    logger.info(f"成功添加邮件: {filename}")
                    
                finally:
                    # 删除临时文件
                    try:
                        if os.path.exists(temp_path):
                            os.unlink(temp_path)
                    except:
                        pass
                
            except Exception as e:
                logger.error(f"处理邮件 '{message.get('subject', '')}' 时出错: {str(e)}")
        
        # 更新同步时间
        parser_config["outlook_last_sync"] = datetime.utcnow().isoformat()
        KnowledgebaseService.update_by_id(kb.id, {
            "parser_config": parser_config
        })
        
        logger.info(f"知识库 '{kb.name}' 同步完成，成功导入 {email_count} 封邮件")
        return email_count
    
    except Exception as e:
        logger.error(f"同步知识库 '{kb.name}' 时出错: {str(e)}")
        return 0

async def main():
    """主函数，同步所有启用了Outlook同步的知识库"""
    try:
        logger.info("开始Outlook邮箱同步任务")
        
        # 加载Azure配置
        azure_settings = load_azure_config()
        if not azure_settings.get('clientId') or not azure_settings.get('tenantId') or not azure_settings.get('clientSecret'):
            logger.error("Azure配置不完整，无法继续")
            return
        
        # 创建Graph客户端
        graph_client = graph_server.Graph(azure_settings)
        
        # 获取所有需要同步的知识库
        kbs = get_kb_to_sync()
        logger.info(f"找到 {len(kbs)} 个启用了Outlook同步的知识库")
        
        # 同步每个知识库
        total_emails = 0
        for kb in kbs:
            email_count = await sync_kb_emails(kb, graph_client)
            total_emails += email_count
        
        logger.info(f"所有知识库同步完成，总共导入 {total_emails} 封邮件")
    
    except Exception as e:
        logger.error(f"同步过程中发生错误: {str(e)}")

if __name__ == "__main__":
    asyncio.run(main()) 