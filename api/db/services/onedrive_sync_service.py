import asyncio
import logging
import os
import time
from datetime import datetime
import configparser
from typing import List, Dict, Any, Optional

from api.db.services.document_service import DocumentService
from api.db.services.knowledgebase_service import KnowledgebaseService
from api.db.services.file_service import FileService
from api.db.services.file2document_service import File2DocumentService
from api.db.services.task_service import queue_tasks
from api.utils import get_uuid
from api.utils.file_utils import get_project_base_directory, filename_type
from api.db import TaskStatus, FileType

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
                    parser_config = kb.parser_config or {}
                    email = parser_config.get('onedrive_email')
                    folder_path = parser_config.get('onedrive_folder_path')
                    delta_link = kb.delta_link
                    
                    if not email:
                        logger.warning(f"知识库 {kb_id} 启用了OneDrive同步但未设置email，跳过")
                        continue
                    
                    logger.info(f"开始同步知识库 {kb_id} 的OneDrive文件，用户邮箱: {email}")
                    if folder_path:
                        logger.info(f"知识库 {kb_id} 配置了文件夹路径: {folder_path}")
                    
                    # 获取变更
                    changes = await onedrive.get_drive_delta_by_email(email, delta_link or "")
                    
                    if changes.get('error'):
                        logger.error(f"获取OneDrive变更失败: {changes['error']}")
                        continue
                    
                    # 如果配置了文件夹路径，过滤出该文件夹下的文件
                    if folder_path:
                        changes = cls._filter_changes_by_folder_path(changes, folder_path)
                        logger.info(f"过滤后的变更: 新增 {len(changes.get('added', []))} 个文件，修改 {len(changes.get('modified', []))} 个文件，删除 {len(changes.get('deleted', []))} 个项目")
                    
                    # 处理变更
                    await cls._process_changes(kb, changes, onedrive, email=email)
                    
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
    def _filter_changes_by_folder_path(cls, changes: Dict[str, Any], folder_path: str) -> Dict[str, Any]:
        """根据文件夹路径过滤变更
        
        Args:
            changes: 原始变更数据
            folder_path: 要过滤的文件夹路径
            
        Returns:
            过滤后的变更数据
        """
        def is_in_folder(item_path: str, target_folder: str) -> bool:
            """检查文件是否在指定文件夹内"""
            if not item_path or not target_folder:
                return False
            
            # 规范化路径
            item_path = item_path.strip('/')
            target_folder = target_folder.strip('/')
            
            # 检查是否在目标文件夹内
            return item_path.startswith(target_folder + '/') or item_path == target_folder
        
        filtered_changes = {
            'added': [],
            'modified': [],
            'deleted': [],
            'delta_link': changes.get('delta_link'),
            'total_changes': 0
        }
        
        # 过滤新增文件
        for item in changes.get('added', []):
            if is_in_folder(item.get('path', ''), folder_path):
                filtered_changes['added'].append(item)
        
        # 过滤修改文件
        for item in changes.get('modified', []):
            if is_in_folder(item.get('path', ''), folder_path):
                filtered_changes['modified'].append(item)
        
        # 过滤删除文件
        for item in changes.get('deleted', []):
            if is_in_folder(item.get('path', ''), folder_path):
                filtered_changes['deleted'].append(item)
        
        # 更新总变更数
        filtered_changes['total_changes'] = (
            len(filtered_changes['added']) + 
            len(filtered_changes['modified']) + 
            len(filtered_changes['deleted'])
        )
        
        return filtered_changes
    
    @classmethod
    def _get_onedrive_config(cls) -> Optional[configparser.ConfigParser]:
        """获取OneDrive配置"""
        try:
            # 使用与Outlook同步服务相同的配置读取方式
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
            logger.error(f"读取OneDrive配置时发生错误: {str(e)}")
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
    def _is_supported_file_type(cls, filename: str) -> bool:
        """检查文件类型是否受支持"""
        try:
            file_type = filename_type(filename)
            # 排除不支持的文件类型
            if file_type == FileType.OTHER.value:
                return False
            
            # 虽然VISUAL和AURAL类型在技术上支持，但用户可能希望跳过某些大型媒体文件
            # 这里可以根据具体需求进行调整
            filename_lower = filename.lower()
            
            # 跳过视频文件（虽然在VISUAL类型中，但通常不适合解析）
            video_extensions = ['.mpg', '.mpeg', '.avi', '.rm', '.rmvb', '.mov', '.wmv', '.asf', '.dat', '.asx', '.wvx', '.mpe', '.mpa', '.mp4']
            for ext in video_extensions:
                if filename_lower.endswith(ext):
                    logger.info(f"跳过视频文件: {filename}")
                    return False
            
            # 跳过音频文件（用户可能不希望解析音频文件）
            if file_type == FileType.AURAL.value:
                logger.info(f"跳过音频文件: {filename}")
                return False
            
            return True
            
        except Exception as e:
            logger.exception(f"检查文件类型时发生错误: {str(e)}")
            return False
    
    @classmethod
    async def _process_changes(cls, kb, changes: Dict[str, Any], onedrive: OneDriveAccess, check_cancelled=False, email: Optional[str] = None):
        """处理OneDrive变更
        
        Args:
            kb: 知识库对象
            changes: OneDrive变更信息
            onedrive: OneDriveAccess实例
            check_cancelled: 是否检查任务是否被取消
            email: 可选的邮箱地址，用于"立即同步"时直接传递参数
        """
        kb_id = kb.id
        parser_config = getattr(kb, 'parser_config', {}) or {}
        # 优先使用传入的email参数，否则从配置中获取
        sync_email = email or parser_config.get('onedrive_email')
        tenant_id = kb.tenant_id
        user_id = kb.created_by
        
        # 获取OneDrive用户ID
        if not sync_email:
            logger.error("知识库未设置OneDrive邮箱")
            return
            
        onedrive_user_id = await onedrive.get_user_id_by_email(sync_email)
        if not onedrive_user_id:
            logger.error(f"无法获取邮箱 {sync_email} 对应的OneDrive用户ID")
            return
        
        # 处理新增文件
        added_files = [item for item in changes.get('added', []) if item.get('type') == 'file']
        logger.info(f"知识库 {kb_id} 有 {len(added_files)} 个新增文件需要处理")
        
        for file_item in added_files:
            try:
                # 检查是否被取消
                if check_cancelled:
                    from api.db.services.sync_state import SYNCING_KNOWLEDGE_BASES
                    if kb_id in SYNCING_KNOWLEDGE_BASES and SYNCING_KNOWLEDGE_BASES[kb_id].get("cancelled"):
                        logger.info(f"知识库 {kb_id} 的同步任务被取消，停止处理")
                        return
                
                file_path = file_item.get('path')
                file_name = file_item.get('name')
                if not file_path or not file_name:
                    continue
                
                # 清理路径，去掉可能的前缀
                clean_path = file_path
                if clean_path.startswith('/drive/root:'):
                    clean_path = clean_path[12:]  # 去掉 '/drive/root:'
                if clean_path.startswith('/'):
                    clean_path = clean_path[1:]  # 去掉开头的 '/'
                
                # 检查文件类型是否受支持
                if not cls._is_supported_file_type(file_name):
                    logger.info(f"跳过不支持的文件类型: {file_name}")
                    continue
                    
                # 下载文件
                file_data = await onedrive.download_file(onedrive_user_id, clean_path)
                if file_data.get('error'):
                    logger.error(f"下载文件 {clean_path} 失败: {file_data.get('error')}")
                    continue
                
                # 解码文件内容
                file_content = file_data.get('content_base64')
                if not file_content:
                    logger.error(f"文件 {clean_path} 内容为空")
                    continue
                    
                # 创建文件对象
                file_obj = cls._create_file_obj(file_name, file_content)
                
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
                    from api.db.services.sync_state import SYNCING_KNOWLEDGE_BASES
                    if kb_id in SYNCING_KNOWLEDGE_BASES and SYNCING_KNOWLEDGE_BASES[kb_id].get("cancelled"):
                        logger.info(f"知识库 {kb_id} 的同步任务被取消，停止处理")
                        return
                
                file_path = file_item.get('path')
                file_name = file_item.get('name')
                if not file_path or not file_name:
                    continue
                
                # 清理路径，去掉可能的前缀
                clean_path = file_path
                if clean_path.startswith('/drive/root:'):
                    clean_path = clean_path[12:]  # 去掉 '/drive/root:'
                if clean_path.startswith('/'):
                    clean_path = clean_path[1:]  # 去掉开头的 '/'
                
                # 检查文件类型是否受支持
                if not cls._is_supported_file_type(file_name):
                    logger.info(f"跳过不支持的文件类型: {file_name}")
                    continue
                
                # 查找对应的文档
                doc = cls._find_document_by_onedrive_path(kb_id, file_path)
                if doc:
                    # 删除旧文档
                    logger.info(f"删除已修改的文档: {doc.name}, ID: {doc.id}")
                    DocumentService.remove_document(doc, tenant_id)
                
                # 下载新文件
                file_data = await onedrive.download_file(onedrive_user_id, clean_path)
                if file_data.get('error'):
                    logger.error(f"下载文件 {clean_path} 失败: {file_data.get('error')}")
                    continue
                
                # 解码文件内容
                file_content = file_data.get('content_base64')
                if not file_content:
                    logger.error(f"文件 {clean_path} 内容为空")
                    continue
                    
                # 创建文件对象
                file_obj = cls._create_file_obj(file_name, file_content)
                
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
                    from api.db.services.sync_state import SYNCING_KNOWLEDGE_BASES
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
            
            # 创建解析任务
            try:
                # 获取文档信息
                e, doc = DocumentService.get_by_id(doc_id)
                if e and doc:
                    doc_data = doc.to_dict()
                    # 获取存储地址
                    bucket, name = File2DocumentService.get_storage_address(doc_id=doc_id)
                    # 创建解析任务
                    queue_tasks(doc_data, bucket, name, 0)
                    
                    # 设置运行状态
                    DocumentService.update_by_id(doc_id, {"run": TaskStatus.RUNNING.value})
                    
                    logger.info(f"成功为文件 {file_obj.filename} 创建解析任务")
                else:
                    logger.error(f"无法获取文档信息，文档ID: {doc_id}")
            except Exception as e:
                logger.error(f"创建解析任务失败: {str(e)}")
            
            logger.info(f"文件 {file_obj.filename} 已上传到知识库 {kb_id}，文档ID: {doc_id}")
            
        except Exception as e:
            logger.exception(f"上传文件到知识库时发生错误: {str(e)}")

    @classmethod
    async def sync_single_kb(cls, kb_id: str, force_sync: bool = False, email: Optional[str] = None, folder_path: Optional[str] = None):
        """同步单个知识库
        
        Args:
            kb_id: 知识库ID
            force_sync: 是否强制同步（跳过同步开关检查）
            email: 可选的邮箱地址，用于"立即同步"时直接传递参数
            folder_path: 可选的文件夹路径，用于"立即同步"时直接传递参数
            
        Returns:
            同步结果
        """
        try:
            logger.info(f"开始同步单个知识库 {kb_id} 的OneDrive文件")
            
            # 检查知识库是否存在
            e, kb = KnowledgebaseService.get_by_id(kb_id)
            if not e or kb is None:
                logger.error(f"知识库 {kb_id} 不存在")
                return {"success": False, "error": "知识库不存在"}
            
            # 获取解析器配置
            parser_config = getattr(kb, 'parser_config', {}) or {}
            
            # 检查知识库是否启用OneDrive同步（除非强制同步）
            if not force_sync and not parser_config.get('onedrive_sync_enabled'):
                logger.error(f"知识库 {kb_id} 未启用OneDrive同步")
                return {"success": False, "error": "知识库未启用OneDrive同步"}
            
            # 获取邮箱和文件夹路径配置
            # 优先使用直接传递的参数（用于"立即同步"），否则从配置读取（用于定时同步）
            sync_email = email or parser_config.get('onedrive_email')
            sync_folder_path = folder_path or parser_config.get('onedrive_folder_path')
            
            if not sync_email:
                if force_sync:
                    logger.error(f"知识库 {kb_id} 缺少邮箱配置，请先配置邮箱后再进行同步")
                else:
                    logger.error(f"知识库 {kb_id} 缺少邮箱配置")
                return {"success": False, "error": "未设置OneDrive邮箱"}
            
            # 获取OneDrive配置
            config = cls._get_onedrive_config()
            if not config:
                logger.error("无法获取OneDrive配置")
                return {"success": False, "error": "无法获取OneDrive配置"}
            
            # 创建OneDriveAccess实例
            onedrive = OneDriveAccess(config['azure'])
            
            # 获取delta_link
            delta_link = getattr(kb, 'delta_link', None)
            
            # 如果指定了文件夹路径，需要从该文件夹获取文件
            if sync_folder_path:
                logger.info(f"开始获取知识库 {kb_id} 的OneDrive指定文件夹 {sync_folder_path} 内容，用户邮箱: {sync_email}")
                # 获取文件夹内容
                content = await onedrive.get_all_files_by_email_and_folder(sync_email, sync_folder_path)
                
                if content.get('error'):
                    logger.error(f"获取OneDrive文件夹内容失败: {content['error']}")
                    return {"success": False, "error": f"获取OneDrive文件夹内容失败: {content['error']}"}
                
                # 处理文件夹内容作为新增文件
                files = content.get('files', [])
                changes = {
                    'added': files,
                    'modified': [],
                    'deleted': [],
                    'delta_link': None
                }
            else:
                # 使用增量同步
                logger.info(f"开始获取知识库 {kb_id} 的OneDrive变更，用户邮箱: {sync_email}")
                changes = await onedrive.get_drive_delta_by_email(sync_email, delta_link or "")
            
            if changes.get('error'):
                logger.error(f"获取OneDrive变更失败: {changes['error']}")
                return {"success": False, "error": f"获取OneDrive变更失败: {changes['error']}"}
            
            # 处理变更
            await cls._process_changes(kb, changes, onedrive, check_cancelled=True, email=sync_email)
            
            # 检查是否被取消
            from api.db.services.sync_state import SYNCING_KNOWLEDGE_BASES
            if kb_id in SYNCING_KNOWLEDGE_BASES and SYNCING_KNOWLEDGE_BASES[kb_id].get("cancelled"):
                logger.info(f"知识库 {kb_id} 的同步任务被取消")
                return {"success": False, "error": "同步任务被取消"}
            
            # 更新delta_link（仅在增量同步时）
            if not sync_folder_path:
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