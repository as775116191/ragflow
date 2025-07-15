import asyncio
import logging
import os
import time
from datetime import datetime
import configparser
from typing import List, Dict, Any, Optional
import base64
import tempfile

from api.db.services.document_service import DocumentService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.file_service import FileService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.task_service import queue_tasks
from api.utils import get_uuid
from api.utils.file_utils import get_project_base_directory
from api.db import TaskStatus, FileSource
from api.db.db_models import File
from rag.utils.storage_factory import STORAGE_IMPL

# 导入Graph服务
from api.db.services.graph_server import Graph

logger = logging.getLogger(__name__)

class OutlookSyncService:
    """Outlook同步服务，处理知识库与Outlook邮箱的邮件同步"""
    
    @classmethod
    async def sync_all_enabled_kbs(cls):
        """同步所有启用了Outlook同步的知识库"""
        try:
            logger.info("开始同步所有启用Outlook同步的知识库")
            
            # 获取配置
            config = cls._get_outlook_config()
            if not config:
                logger.error("无法获取Outlook配置，同步取消")
                return
                
            # 创建Graph实例
            graph = Graph(config['azure'])
            
            # 获取所有启用了Outlook同步的知识库
            enabled_kbs = cls._get_enabled_kbs()
            logger.info(f"找到 {len(enabled_kbs)} 个启用了Outlook同步的知识库")
            
            for kb in enabled_kbs:
                try:
                    await cls.sync_single_kb(kb.id)
                except Exception as e:
                    logger.error(f"同步知识库 {kb.id} 时发生错误: {str(e)}")
                    continue
                    
        except Exception as e:
            logger.error(f"同步所有知识库时发生错误: {str(e)}")
    
    @classmethod
    async def reset_sync_time(cls, kb_id: str):
        """重置知识库的同步时间，下次同步时会从头开始"""
        try:
            logger.info(f"重置知识库 {kb_id} 的同步时间")
            
            # 获取知识库信息
            e, kb = KnowledgebaseService.get_by_id(kb_id)
            if not e or kb is None:
                logger.error(f"知识库 {kb_id} 不存在")
                return False
                
            # 重置同步时间
            parser_config = kb.parser_config or {}
            if 'outlook_last_sync' in parser_config:
                del parser_config['outlook_last_sync']
                
                # 保存配置
                KnowledgebaseService.update_by_id(kb_id, {
                    'parser_config': parser_config
                })
                logger.info(f"已重置知识库 {kb_id} 的同步时间")
                return True
            else:
                logger.info(f"知识库 {kb_id} 没有同步时间记录")
                return True
                
        except Exception as e:
            logger.error(f"重置同步时间时发生错误: {str(e)}")
            return False
    
    @classmethod
    async def sync_single_kb(cls, kb_id: str, force_sync: bool = False, email: Optional[str] = None, folder_name: Optional[str] = None):
        """同步单个知识库的Outlook邮件
        
        Args:
            kb_id: 知识库ID
            force_sync: 是否强制同步（跳过同步开关检查）
            email: 可选的邮箱地址，用于"立即同步"时直接传递参数
            folder_name: 可选的文件夹名称，用于"立即同步"时直接传递参数
        """
        try:
            logger.info(f"开始同步知识库 {kb_id} 的Outlook邮件")
            
            # 获取知识库信息
            e, kb = KnowledgebaseService.get_by_id(kb_id)
            if not e or kb is None:
                logger.error(f"知识库 {kb_id} 不存在")
                return
                
            # 检查是否启用了Outlook同步（除非强制同步）
            parser_config = kb.parser_config or {}
            if not force_sync and not parser_config.get('outlook_sync_enabled'):
                logger.info(f"知识库 {kb_id} 未启用Outlook同步")
                return
                
            # 获取邮箱和文件夹配置
            # 优先使用直接传递的参数（用于"立即同步"），否则从配置读取（用于定时同步）
            sync_email = email or parser_config.get('outlook_email')
            sync_folder_name = folder_name or parser_config.get('outlook_folder')
            
            if not sync_email or not sync_folder_name:
                if force_sync:
                    logger.error(f"知识库 {kb_id} 缺少邮箱或文件夹配置，请先配置邮箱和文件夹后再进行同步")
                else:
                    logger.error(f"知识库 {kb_id} 缺少邮箱或文件夹配置")
                return
                
            # 获取配置
            config = cls._get_outlook_config()
            if not config:
                logger.error("无法获取Outlook配置，同步取消")
                return
                
            # 创建Graph实例
            try:
                logger.info(f"尝试创建Graph实例，配置: {dict(config['azure'])}")
                # 确保传递的是SectionProxy对象，而不是字典
                azure_config = config['azure']
                logger.info(f"Azure配置类型: {type(azure_config)}")
                graph = Graph(azure_config)
                logger.info("Graph实例创建成功")
            except Exception as e:
                logger.error(f"创建Graph实例失败: {str(e)}")
                logger.error(f"Azure配置详情: {dict(config['azure'])}")
                logger.error(f"配置类型: {type(config['azure'])}")
                raise
            
            # 获取上次同步时间
            last_sync = parser_config.get('outlook_last_sync')
            since_datetime = None
            if last_sync:
                since_datetime = last_sync
                
            logger.info(f"获取 {sync_email} 文件夹 {sync_folder_name} 的邮件")
            if since_datetime:
                logger.info(f"只获取 {since_datetime} 之后的邮件")
                
            # 获取邮件EML数据
            result = await graph.get_messages_as_eml_by_email_and_folder(
                sync_email, sync_folder_name, since_datetime
            )
            
            if result.get('error'):
                logger.error(f"获取邮件失败: {result['error']}")
                return
                
            eml_messages = result.get('eml_messages', [])
            if eml_messages is None:
                eml_messages = []
                
            logger.info(f"获取到 {len(eml_messages)} 封邮件")
            
            # 处理每封邮件
            processed_count = 0
            failed_count = 0
            for msg in eml_messages:
                try:
                    await cls._process_email_message(kb_id, msg)
                    processed_count += 1
                except Exception as e:
                    logger.error(f"处理邮件 {msg.get('id')} 时发生错误: {str(e)}")
                    failed_count += 1
                    continue
                    
            # 只有当所有邮件都成功处理时才更新同步时间
            if failed_count == 0 and len(eml_messages) > 0:
                current_time = datetime.utcnow().strftime('%Y-%m-%dT%H:%M:%S.%fZ')
                parser_config['outlook_last_sync'] = current_time
                
                # 保存配置
                KnowledgebaseService.update_by_id(kb_id, {
                    'parser_config': parser_config
                })
                logger.info(f"成功处理 {processed_count} 封邮件，更新同步时间为: {current_time}")
            elif failed_count > 0:
                logger.warning(f"有 {failed_count} 封邮件处理失败，不更新同步时间，下次同步时会重新处理")
            else:
                logger.info("没有新邮件需要处理")
            
            logger.info(f"知识库 {kb_id} 的Outlook邮件同步完成")
            
        except Exception as e:
            logger.error(f"同步知识库 {kb_id} 时发生错误: {str(e)}")
            raise
    
    @classmethod
    async def _process_email_message(cls, kb_id: str, msg: Dict[str, Any]):
        """处理单封邮件，将其保存为文档"""
        try:
            message_id = msg.get('id')
            eml_base64 = msg.get('eml_base64')
            subject = msg.get('subject', 'No Subject')
            from_addr = msg.get('from', 'Unknown')
            received_date = msg.get('received_date', '')
            
            if not eml_base64:
                logger.warning(f"邮件 {message_id} 没有EML内容")
                return
                
            # 检查是否已存在该邮件
            existing_docs = DocumentService.query(
                kb_id=kb_id,
                name=f"{subject}_{message_id}.eml"
            )
            
            if existing_docs:
                logger.info(f"邮件 {message_id} 已存在，跳过")
                return
                
            # 解码EML内容
            eml_content = base64.b64decode(eml_base64)
            
            # 创建临时文件
            with tempfile.NamedTemporaryFile(suffix='.eml', delete=False) as tmp_file:
                tmp_file.write(eml_content)
                tmp_file_path = tmp_file.name
                
            try:
                # 创建文件记录
                file_id = get_uuid()
                file_name = f"{subject}_{message_id}.eml"
                
                # 获取知识库信息
                e, kb = KnowledgebaseService.get_by_id(kb_id)
                if not e or kb is None:
                    logger.error(f"知识库 {kb_id} 不存在")
                    return
                    
                # 创建File记录
                file_record = {
                    'id': file_id,
                    'parent_id': kb.id,
                    'tenant_id': kb.tenant_id,
                    'created_by': kb.tenant_id,
                    'type': 'file',
                    'name': file_name,
                    'location': tmp_file_path,
                    'size': len(eml_content),
                    'source_type': FileSource.KNOWLEDGEBASE,
                }
                
                # 保存文件记录
                if not FileService.save(**file_record):
                    logger.error(f"保存文件记录失败: {file_name}")
                    return
                    
                # 创建文档记录
                doc_id = get_uuid()
                doc_record = {
                    'id': doc_id,
                    'kb_id': kb_id,
                    'parser_id': 'email',  # 使用email解析器
                    'parser_config': {},
                    'name': file_name,
                    'type': 'eml',
                    'created_by': kb.tenant_id,
                    'size': len(eml_content),
                    'run': TaskStatus.UNSTART.value,
                    'source_type': 'outlook',
                    'location': tmp_file_path,
                }
                
                # 保存文档记录
                try:
                    DocumentService.insert(doc_record)
                    logger.info(f"成功创建文档记录: {file_name}")
                except Exception as e:
                    logger.error(f"保存文档记录失败: {file_name}, 错误: {str(e)}")
                    return
                    
                # 创建文件-文档关联
                file2doc_id = get_uuid()
                file2doc_record = {
                    'id': file2doc_id,
                    'file_id': file_id,
                    'document_id': doc_id,
                    'kb_id': kb_id,
                }
                
                if not File2DocumentService.save(**file2doc_record):
                    logger.error(f"保存文件-文档关联失败: {file_name}")
                    return
                    
                # 创建解析任务
                try:
                    # 获取存储地址
                    bucket, name = File2DocumentService.get_storage_address(doc_id=doc_id)
                    
                    # 上传文件到 MinIO
                    STORAGE_IMPL.put(bucket, name, eml_content)
                    
                    # 创建解析任务
                    queue_tasks(doc_record, bucket, name, 0)
                    logger.info(f"成功创建邮件文档并启动解析任务: {file_name}")
                except Exception as e:
                    logger.error(f"启动解析任务失败: {str(e)}")
                    logger.info(f"成功创建邮件文档: {file_name}")
                
            finally:
                # 清理临时文件
                try:
                    os.unlink(tmp_file_path)
                except:
                    pass
                    
        except Exception as e:
            logger.error(f"处理邮件时发生错误: {str(e)}")
            raise
    
    @classmethod
    def _get_outlook_config(cls):
        """获取Outlook配置"""
        try:
            # 尝试从现有的定时任务脚本中获取配置方式
            config_path = os.path.join(get_project_base_directory(), 'api', 'config.cfg')
            alt_config_path = os.path.join(get_project_base_directory(), 'api', 'config.dev.cfg')
            
            config = configparser.ConfigParser()
            if os.path.exists(config_path):
                config.read(config_path)
            elif os.path.exists(alt_config_path):
                config.read(alt_config_path)
            else:
                # 使用环境变量
                logger.info("配置文件不存在，尝试使用环境变量")
                # 确保创建一个section而不是直接赋值字典
                config.add_section('azure')
                config['azure']['clientId'] = os.environ.get('AZURE_CLIENT_ID', '')
                config['azure']['tenantId'] = os.environ.get('AZURE_TENANT_ID', '')
                config['azure']['clientSecret'] = os.environ.get('AZURE_CLIENT_SECRET', '')
            
            if 'azure' not in config:
                config.add_section('azure')
                logger.warning("Azure配置不存在，将使用空配置")
            
            return config
            
        except Exception as e:
            logger.error(f"读取配置文件时发生错误: {str(e)}")
            return None
    
    @classmethod
    def _get_enabled_kbs(cls):
        """获取所有启用了Outlook同步的知识库"""
        try:
            from api.db import StatusEnum
            all_kbs = KnowledgebaseService.query(status=StatusEnum.VALID.value)
            enabled_kbs = []
            
            for kb in all_kbs:
                parser_config = kb.parser_config or {}
                if parser_config.get('outlook_sync_enabled'):
                    enabled_kbs.append(kb)
                    
            return enabled_kbs
            
        except Exception as e:
            logger.error(f"获取启用Outlook同步的知识库时发生错误: {str(e)}")
            return []