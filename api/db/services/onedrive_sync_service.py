import asyncio
import logging
import os
import time
from datetime import datetime
import configparser
from typing import List, Dict, Any

from api.db.services.document_service import DocumentService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.file_service import FileService
from api.db.services.file2document_service import File2DocumentService
from api.utils import get_uuid
from api.utils.file_utils import get_project_base_directory
from api.db import TaskStatus

# 导入OneDriveAccess类
from api.db.services.onedrive_service import OneDriveAccess

logger = logging.getLogger(__name__)

class OneDriveSyncService:
    """OneDrive同步服务，处理知识库与OneDrive的文件同步"""
    
    @classmethod
    async def sync_all_enabled_kbs(cls):
        """同步所有启用了OneDrive同步的知识库"""
        try:
            logger.info("开始同步所有启用OneDrive同步的知识库")
            
            # 获取配置
            config = cls._get_onedrive_config()
            if not config:
                logger.error("无法获取OneDrive配置，同步取消")
                return
                
            # 创建OneDriveAccess实例
            onedrive = OneDriveAccess(config['azure'])
            
            # 获取所有启用了OneDrive同步的知识库
            enabled_kbs = cls._get_enabled_kbs()
            logger.info(f"找到 {len(enabled_kbs)} 个启用了OneDrive同步的知识库")
            
            for kb in enabled_kbs:
                try:
                    # 获取知识库的OneDrive配置
                    kb_id = kb.id
                    email = kb.parser_config.get('onedrive_email')
                    delta_link = kb.delta_link
                    
                    if not email:
                        logger.warning(f"知识库 {kb_id} 启用了OneDrive同步但未设置email，跳过")
                        continue
                    
                    logger.info(f"开始同步知识库 {kb_id} 的OneDrive文件，用户邮箱: {email}")
                    
                    # 获取变更
                    changes = await onedrive.get_drive_delta_by_email(email, delta_link)
                    
                    if changes.get('error'):
                        logger.error(f"获取OneDrive变更失败: {changes['error']}")
                        continue
                    
                    # 处理变更
                    await cls._process_changes(kb, changes, onedrive)
                    
                    # 更新delta_link
                    new_delta_link = changes.get('delta_link')
                    if new_delta_link:
                        KnowledgebaseService.update_by_id(kb_id, {"delta_link": new_delta_link})
                        logger.info(f"知识库 {kb_id} 的delta_link已更新")
                    
                except Exception as e:
                    logger.exception(f"同步知识库 {kb.id} 时发生错误: {str(e)}")
            
            logger.info("所有知识库同步完成")
            
        except Exception as e:
            logger.exception(f"同步过程中发生错误: {str(e)}")
    
    @classmethod
    def _get_onedrive_config(cls) -> dict:
        """获取OneDrive配置"""
        try:
            config = configparser.ConfigParser()
            config_paths = [
                os.path.join(get_project_base_directory(), 'config.cfg'),
                os.path.join(get_project_base_directory(), 'config.dev.cfg')
            ]
            
            # 尝试读取配置文件
            found = False
            for path in config_paths:
                if os.path.exists(path):
                    config.read(path)
                    found = True
                    break
            
            if not found or 'azure' not in config:
                logger.error("未找到有效的Azure配置")
                return None
                
            return config
            
        except Exception as e:
            logger.exception(f"读取OneDrive配置时发生错误: {str(e)}")
            return None
    
    @classmethod
    def _get_enabled_kbs(cls) -> List:
        """获取所有启用了OneDrive同步的知识库"""
        try:
            # 查询所有知识库
            all_kbs = KnowledgebaseService.query()
            
            # 过滤出启用了OneDrive同步的知识库
            enabled_kbs = []
            for kb in all_kbs:
                parser_config = kb.parser_config or {}
                if parser_config.get('onedrive_sync_enabled'):
                    enabled_kbs.append(kb)
            
            return enabled_kbs
            
        except Exception as e:
            logger.exception(f"获取启用OneDrive同步的知识库时发生错误: {str(e)}")
            return []
    
    @classmethod
    async def _process_changes(cls, kb, changes: Dict[str, Any], onedrive: OneDriveAccess, check_cancelled=False):
        """处理OneDrive变更
        
        Args:
            kb: 知识库对象
            changes: OneDrive变更信息
            onedrive: OneDriveAccess实例
            check_cancelled: 是否检查任务是否被取消
        """
        kb_id = kb.id
        email = kb.parser_config.get('onedrive_email')
        tenant_id = kb.tenant_id
        user_id = kb.created_by
        
        # 处理新增文件
        added_files = [item for item in changes.get('added', []) if item.get('type') == 'file']
        logger.info(f"知识库 {kb_id} 有 {len(added_files)} 个新增文件需要处理")
        
        for file_item in added_files:
            try:
                # 检查是否被取消
                if check_cancelled:
                    from api.apps.kb_app import SYNCING_KNOWLEDGE_BASES
                    if kb_id in SYNCING_KNOWLEDGE_BASES and SYNCING_KNOWLEDGE_BASES[kb_id].get("cancelled"):
                        logger.info(f"知识库 {kb_id} 的同步任务被取消，停止处理")
                        return
                
                file_path = file_item.get('path')
                if not file_path:
                    continue
                    
                # 下载文件
                file_data = await onedrive.download_file(file_item.get('id'), file_path)
                if file_data.get('error'):
                    logger.error(f"下载文件 {file_path} 失败: {file_data.get('error')}")
                    continue
                
                # 解码文件内容
                file_content = file_data.get('content_base64')
                if not file_content:
                    logger.error(f"文件 {file_path} 内容为空")
                    continue
                    
                # 创建文件对象
                file_obj = cls._create_file_obj(file_item.get('name'), file_content)
                
                # 上传文件到知识库
                await cls._upload_file_to_kb(kb, file_obj, file_path, user_id)
                
            except Exception as e:
                logger.exception(f"处理新增文件 {file_item.get('name')} 时发生错误: {str(e)}")
        
        # 处理修改文件
        modified_files = [item for item in changes.get('modified', []) if item.get('type') == 'file']
        logger.info(f"知识库 {kb_id} 有 {len(modified_files)} 个修改文件需要处理")
        
        for file_item in modified_files:
            try:
                # 检查是否被取消
                if check_cancelled:
                    from api.apps.kb_app import SYNCING_KNOWLEDGE_BASES
                    if kb_id in SYNCING_KNOWLEDGE_BASES and SYNCING_KNOWLEDGE_BASES[kb_id].get("cancelled"):
                        logger.info(f"知识库 {kb_id} 的同步任务被取消，停止处理")
                        return
                
                file_path = file_item.get('path')
                if not file_path:
                    continue
                
                # 查找对应的文档
                doc = cls._find_document_by_onedrive_path(kb_id, file_path)
                if doc:
                    # 删除旧文档
                    logger.info(f"删除已修改的文档: {doc.name}, ID: {doc.id}")
                    DocumentService.remove_document(doc, tenant_id)
                
                # 下载新文件
                file_data = await onedrive.download_file(file_item.get('id'), file_path)
                if file_data.get('error'):
                    logger.error(f"下载文件 {file_path} 失败: {file_data.get('error')}")
                    continue
                
                # 解码文件内容
                file_content = file_data.get('content_base64')
                if not file_content:
                    logger.error(f"文件 {file_path} 内容为空")
                    continue
                    
                # 创建文件对象
                file_obj = cls._create_file_obj(file_item.get('name'), file_content)
                
                # 上传文件到知识库
                await cls._upload_file_to_kb(kb, file_obj, file_path, user_id)
                
            except Exception as e:
                logger.exception(f"处理修改文件 {file_item.get('name')} 时发生错误: {str(e)}")
        
        # 处理删除文件
        deleted_items = changes.get('deleted', [])
        logger.info(f"知识库 {kb_id} 有 {len(deleted_items)} 个删除项目需要处理")
        
        for item in deleted_items:
            try:
                # 检查是否被取消
                if check_cancelled:
                    from api.apps.kb_app import SYNCING_KNOWLEDGE_BASES
                    if kb_id in SYNCING_KNOWLEDGE_BASES and SYNCING_KNOWLEDGE_BASES[kb_id].get("cancelled"):
                        logger.info(f"知识库 {kb_id} 的同步任务被取消，停止处理")
                        return
                
                item_path = item.get('path')
                if not item_path:
                    continue
                
                # 查找对应的文档
                doc = cls._find_document_by_onedrive_path(kb_id, item_path)
                if doc:
                    # 删除文档
                    logger.info(f"删除已从OneDrive移除的文档: {doc.name}, ID: {doc.id}")
                    DocumentService.remove_document(doc, tenant_id)
                
            except Exception as e:
                logger.exception(f"处理删除项目 {item.get('name')} 时发生错误: {str(e)}")
    
    @classmethod
    def _find_document_by_onedrive_path(cls, kb_id, onedrive_path):
        """根据OneDrive路径查找文档"""
        try:
            # 查询所有文档
            docs = DocumentService.query(kb_id=kb_id)
            
            # 查找匹配onedrive_path的文档
            for doc in docs:
                if doc.onedrive_path == onedrive_path:
                    return doc
            
            return None
            
        except Exception as e:
            logger.exception(f"查找文档时发生错误: {str(e)}")
            return None
    
    @classmethod
    def _create_file_obj(cls, filename, content_base64):
        """创建文件对象"""
        class FileObj:
            def __init__(self, name, content):
                self.filename = name
                self._content = content
            
            def read(self):
                import base64
                return base64.b64decode(self._content)
        
        return FileObj(filename, content_base64)
    
    @classmethod
    async def _upload_file_to_kb(cls, kb, file_obj, onedrive_path, user_id):
        """上传文件到知识库并设置OneDrive路径"""
        try:
            kb_id = kb.id
            
            # 上传文件
            err, files = FileService.upload_document(kb, [file_obj], user_id)
            if err:
                logger.error(f"上传文件失败: {err}")
                return
            
            # 获取文档ID
            if not files or len(files) == 0:
                logger.error("上传成功但未返回文件信息")
                return
                
            doc_id = files[0][0]["id"]
            
            # 设置OneDrive路径
            DocumentService.update_by_id(doc_id, {"onedrive_path": onedrive_path})
            
            # 设置文档状态为待处理
            DocumentService.update_by_id(doc_id, {"run": TaskStatus.UNSTART.value})
            
            logger.info(f"文件 {file_obj.filename} 已上传到知识库 {kb_id}，文档ID: {doc_id}")
            
        except Exception as e:
            logger.exception(f"上传文件到知识库时发生错误: {str(e)}")

    @classmethod
    async def sync_single_kb(cls, kb_id):
        """同步单个知识库
        
        Args:
            kb_id: 知识库ID
            
        Returns:
            同步结果
        """
        try:
            logger.info(f"开始同步单个知识库 {kb_id} 的OneDrive文件")
            
            # 检查知识库是否存在
            e, kb = KnowledgebaseService.get_by_id(kb_id)
            if not e:
                logger.error(f"知识库 {kb_id} 不存在")
                return {"success": False, "error": "知识库不存在"}
            
            # 检查知识库是否启用OneDrive同步
            parser_config = kb.parser_config or {}
            if not parser_config.get('onedrive_sync_enabled'):
                logger.error(f"知识库 {kb_id} 未启用OneDrive同步")
                return {"success": False, "error": "知识库未启用OneDrive同步"}
            
            # 获取邮箱和delta_link
            email = parser_config.get('onedrive_email')
            delta_link = kb.delta_link
            
            if not email:
                logger.error(f"知识库 {kb_id} 未设置OneDrive邮箱")
                return {"success": False, "error": "未设置OneDrive邮箱"}
            
            # 获取OneDrive配置
            config = cls._get_onedrive_config()
            if not config:
                logger.error("无法获取OneDrive配置")
                return {"success": False, "error": "无法获取OneDrive配置"}
            
            # 创建OneDriveAccess实例
            onedrive = OneDriveAccess(config['azure'])
            
            # 获取变更
            logger.info(f"开始获取知识库 {kb_id} 的OneDrive变更，用户邮箱: {email}")
            changes = await onedrive.get_drive_delta_by_email(email, delta_link)
            
            if changes.get('error'):
                logger.error(f"获取OneDrive变更失败: {changes['error']}")
                return {"success": False, "error": f"获取OneDrive变更失败: {changes['error']}"}
            
            # 处理变更
            await cls._process_changes(kb, changes, onedrive, check_cancelled=True)
            
            # 检查是否被取消
            from api.apps.kb_app import SYNCING_KNOWLEDGE_BASES
            if kb_id in SYNCING_KNOWLEDGE_BASES and SYNCING_KNOWLEDGE_BASES[kb_id].get("cancelled"):
                logger.info(f"知识库 {kb_id} 的同步任务被取消")
                return {"success": False, "error": "同步任务被取消"}
            
            # 更新delta_link
            new_delta_link = changes.get('delta_link')
            if new_delta_link:
                KnowledgebaseService.update_by_id(kb_id, {"delta_link": new_delta_link})
                logger.info(f"知识库 {kb_id} 的delta_link已更新")
            
            logger.info(f"知识库 {kb_id} 同步完成")
            return {"success": True}
            
        except Exception as e:
            logger.exception(f"同步知识库 {kb_id} 时发生错误: {str(e)}")
            return {"success": False, "error": str(e)}


def run_onedrive_sync():
    """运行OneDrive同步任务"""
    try:
        logger.info("开始OneDrive同步定时任务")
        asyncio.run(OneDriveSyncService.sync_all_enabled_kbs())
        logger.info("OneDrive同步定时任务完成")
    except Exception as e:
        logger.exception(f"OneDrive同步定时任务发生错误: {str(e)}")


if __name__ == "__main__":
    # 设置日志
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # 运行同步
    run_onedrive_sync() 