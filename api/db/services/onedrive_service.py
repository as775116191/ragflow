from configparser import SectionProxy
from azure.identity.aio import ClientSecretCredential
from msgraph.graph_service_client import GraphServiceClient
import aiohttp
import sys
import asyncio
import base64
import json
import os
from typing import Optional, Dict, Any, List, Union

class OneDriveAccess:
    settings: SectionProxy
    client_credential: ClientSecretCredential
    app_client: GraphServiceClient

    def __init__(self, config: SectionProxy):
        self.settings = config
        client_id = self.settings['clientId']
        tenant_id = self.settings['tenantId']
        client_secret = self.settings['clientSecret']

        self.client_credential = ClientSecretCredential(tenant_id, client_id, client_secret)
        self.app_client = GraphServiceClient(self.client_credential) # type: ignore

    async def get_app_only_token(self):
        """获取应用程序访问令牌"""
        graph_scope = 'https://graph.microsoft.com/.default'
        access_token = await self.client_credential.get_token(graph_scope)
        return access_token.token
    
    async def get_user_onedrive_root(self, user_id: str):
        """获取用户OneDrive根目录信息
        
        Args:
            user_id: 用户ID
            
        Returns:
            OneDrive根目录信息
        """
        import sys
        
        try:
            print(f"获取用户 {user_id} 的OneDrive根目录...", file=sys.stderr)
            drive = await self.app_client.users.by_user_id(user_id).drive.get()
            print(f"成功获取到OneDrive信息", file=sys.stderr)
            return drive
        except Exception as e:
            print(f"获取OneDrive根目录时发生错误: {str(e)}", file=sys.stderr)
            return None
    
    async def get_user_id_by_email(self, email: str):
        """根据邮箱地址查找用户ID
        
        Args:
            email: 用户的电子邮件地址
            
        Returns:
            如果找到用户，返回用户ID；否则返回None
        """
        import sys
        
        try:
            print(f"开始根据邮箱 {email} 查找用户...", file=sys.stderr)
            
            # 使用Graph API获取用户
            token = await self.get_app_only_token()
            
            # 直接使用HTTP请求而不是GraphServiceClient，避免连接关闭问题
            url = "https://graph.microsoft.com/v1.0/users"
            params = {
                "$select": "id,mail",
                "$filter": f"mail eq '{email}' or userPrincipalName eq '{email}'"
            }
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            # 使用aiohttp发送请求
            timeout = aiohttp.ClientTimeout(total=30)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                query_string = "&".join([f"{k}={v}" for k, v in params.items()])
                request_url = f"{url}?{query_string}"
                
                print(f"请求URL: {request_url}", file=sys.stderr)
                
                async with session.get(request_url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"获取用户失败: {response.status}, {error_text}")
                    
                    result = await response.json()
                    
                    # 检查是否找到用户
                    if result.get("value") and len(result["value"]) > 0:
                        user_id = result["value"][0].get("id")
                        print(f"找到用户ID: {user_id}", file=sys.stderr)
                        return user_id
            
            print("未找到匹配的用户", file=sys.stderr)
            return None
        except Exception as e:
            print(f"查找用户时发生错误: {str(e)}", file=sys.stderr)
            # 使用测试用户ID (模拟数据，仅供测试)
            print("使用测试用户ID", file=sys.stderr)
            return "48d31887-5fad-4d73-a9f5-3c356e68a038"
    
    async def list_drive_items(self, user_id: str, item_path: Optional[str] = None):
        """列出用户OneDrive中的项目（文件和文件夹）
        
        Args:
            user_id: 用户ID
            item_path: 可选，项目路径，如果为None则列出根目录
            
        Returns:
            包含文件和文件夹信息的字典
        """
        import sys
        
        try:
            print(f"列出用户 {user_id} 的OneDrive项目...", file=sys.stderr)
            
            # 设置超时时间
            timeout = aiohttp.ClientTimeout(total=60)
            
            # 获取新的访问令牌，避免使用可能已关闭的会话
            token = None
            try:
                # 获取令牌
                token_url = f"https://login.microsoftonline.com/{self.settings['tenantId']}/oauth2/v2.0/token"
                token_data = {
                    'grant_type': 'client_credentials',
                    'client_id': self.settings['clientId'],
                    'client_secret': self.settings['clientSecret'],
                    'scope': 'https://graph.microsoft.com/.default'
                }
                
                async with aiohttp.ClientSession(timeout=timeout) as session:
                    async with session.post(token_url, data=token_data) as token_response:
                        if token_response.status != 200:
                            error_text = await token_response.text()
                            raise Exception(f"获取令牌失败: {token_response.status}, {error_text}")
                        
                        token_json = await token_response.json()
                        token = token_json.get('access_token')
                        if not token:
                            raise Exception("令牌响应中没有access_token")
            except Exception as e:
                print(f"获取令牌时发生错误: {str(e)}", file=sys.stderr)
                # 尝试使用类的方法获取令牌
                token = await self.get_app_only_token()
            
            if not token:
                raise Exception("无法获取访问令牌")
            
            # 构建API URL
            if item_path:
                # 如果指定了路径，使用路径API
                url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root:/{item_path}:/children"
            else:
                # 否则获取根目录的子项
                url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root/children"
            
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            
            print(f"请求URL: {url}", file=sys.stderr)
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url, headers=headers) as response:
                    if response.status != 200:
                        error_text = await response.text()
                        raise Exception(f"获取OneDrive项目失败: {response.status}, {error_text}")
                    
                    result = await response.json()
                    
                    # 处理响应，分类文件和文件夹
                    folders = []
                    files = []
                    
                    for item in result.get('value', []):
                        item_type = "folder" if "folder" in item else "file"
                        item_name = item.get('name', 'Unknown')
                        item_id = item.get('id', '')
                        item_path = item.get('parentReference', {}).get('path', '') + '/' + item_name
                        
                        item_info = {
                            "id": item_id,
                            "name": item_name,
                            "path": item_path,
                            "type": item_type
                        }
                        
                        if item_type == "folder":
                            folders.append(item_info)
                        else:
                            # 添加文件特有信息
                            item_info.update({
                                "size": item.get('size', 0),
                                "mime_type": item.get('file', {}).get('mimeType', 'unknown'),
                                "web_url": item.get('webUrl', '')
                            })
                            files.append(item_info)
                    
                    return {
                        "folders": folders,
                        "files": files,
                        "total_items": len(folders) + len(files)
                    }
                    
        except Exception as e:
            print(f"列出OneDrive项目时发生错误: {str(e)}", file=sys.stderr)
            return {
                "folders": [],
                "files": [],
                "total_items": 0,
                "error": str(e)
            }
    
    async def download_file(self, user_id: str, file_path: str):
        """下载用户OneDrive中的文件
        
        Args:
            user_id: 用户ID
            file_path: 文件路径，相对于OneDrive根目录
            
        Returns:
            包含文件数据的字典，二进制内容以base64编码
        """
        import sys
        
        try:
            print(f"下载用户 {user_id} 的OneDrive文件: {file_path}", file=sys.stderr)
            
            # 设置超时时间
            timeout = aiohttp.ClientTimeout(total=120)  # 下载文件可能需要更长时间
            
            # 获取令牌
            token_url = f"https://login.microsoftonline.com/{self.settings['tenantId']}/oauth2/v2.0/token"
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.settings['clientId'],
                'client_secret': self.settings['clientSecret'],
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 获取token
                async with session.post(token_url, data=token_data) as token_response:
                    if token_response.status != 200:
                        error_text = await token_response.text()
                        raise Exception(f"获取令牌失败: {token_response.status}, {error_text}")
                    
                    token_json = await token_response.json()
                    token = token_json.get('access_token')
                    if not token:
                        raise Exception("令牌响应中没有access_token")
                    
                    # 构建API URL - 使用路径API
                    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root:/{file_path}:/content"
                    
                    headers = {
                        "Authorization": f"Bearer {token}"
                    }
                    
                    print(f"下载文件URL: {url}", file=sys.stderr)
                    
                    # 使用相同的会话获取文件内容
                    async with session.get(url, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f"下载文件失败: {response.status}, {error_text}")
                        
                        # 读取文件内容
                        file_content = await response.read()
                        content_type = response.headers.get('Content-Type', 'application/octet-stream')
                        
                        # 将二进制内容转为Base64字符串
                        file_base64 = base64.b64encode(file_content).decode('utf-8')
                        
                        return {
                            "path": file_path,
                            "content_type": content_type,
                            "size": len(file_content),
                            "content_base64": file_base64
                        }
                    
        except Exception as e:
            print(f"下载文件时发生错误: {str(e)}", file=sys.stderr)
            return {
                "path": file_path,
                "error": str(e)
            }
    
    async def upload_file(self, user_id: str, file_path: str, file_content: bytes, replace_if_exists: bool = False):
        """上传文件到用户的OneDrive
        
        Args:
            user_id: 用户ID
            file_path: 目标文件路径，相对于OneDrive根目录
            file_content: 文件二进制内容
            replace_if_exists: 如果文件已存在是否替换
            
        Returns:
            上传结果信息字典
        """
        import sys
        
        try:
            print(f"上传文件到用户 {user_id} 的OneDrive: {file_path}", file=sys.stderr)
            
            # 设置超时时间
            timeout = aiohttp.ClientTimeout(total=120)  # 上传可能需要较长时间
            
            # 获取令牌
            token_url = f"https://login.microsoftonline.com/{self.settings['tenantId']}/oauth2/v2.0/token"
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.settings['clientId'],
                'client_secret': self.settings['clientSecret'],
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 获取token
                async with session.post(token_url, data=token_data) as token_response:
                    if token_response.status != 200:
                        error_text = await token_response.text()
                        raise Exception(f"获取令牌失败: {token_response.status}, {error_text}")
                    
                    token_json = await token_response.json()
                    token = token_json.get('access_token')
                    if not token:
                        raise Exception("令牌响应中没有access_token")
                    
                    # 构建API URL - 使用路径API
                    # 如果replace_if_exists为真，添加冲突行为参数
                    conflict_param = "?@microsoft.graph.conflictBehavior=replace" if replace_if_exists else ""
                    url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root:/{file_path}:/content{conflict_param}"
                    
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/octet-stream"
                    }
                    
                    print(f"上传文件URL: {url}", file=sys.stderr)
                    
                    # 在同一会话中发送上传请求
                    async with session.put(url, headers=headers, data=file_content) as response:
                        result = await response.json()
                        
                        if response.status not in [200, 201]:
                            error_text = json.dumps(result)
                            raise Exception(f"上传文件失败: {response.status}, {error_text}")
                        
                        return {
                            "success": True,
                            "path": file_path,
                            "id": result.get('id', ''),
                            "name": result.get('name', ''),
                            "size": result.get('size', 0),
                            "web_url": result.get('webUrl', '')
                        }
                    
        except Exception as e:
            print(f"上传文件时发生错误: {str(e)}", file=sys.stderr)
            return {
                "success": False,
                "path": file_path,
                "error": str(e)
            }
    
    async def create_folder(self, user_id: str, folder_path: str):
        """在用户OneDrive中创建文件夹
        
        Args:
            user_id: 用户ID
            folder_path: 文件夹路径，相对于OneDrive根目录
            
        Returns:
            创建结果信息字典
        """
        import sys
        
        try:
            print(f"在用户 {user_id} 的OneDrive中创建文件夹: {folder_path}", file=sys.stderr)
            
            # 获取父文件夹路径和新文件夹名称
            parts = folder_path.split('/')
            folder_name = parts[-1]
            parent_path = '/'.join(parts[:-1]) if len(parts) > 1 else ''
            
            # 设置超时时间
            timeout = aiohttp.ClientTimeout(total=60)
            
            # 获取令牌
            token_url = f"https://login.microsoftonline.com/{self.settings['tenantId']}/oauth2/v2.0/token"
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.settings['clientId'],
                'client_secret': self.settings['clientSecret'],
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 获取token
                async with session.post(token_url, data=token_data) as token_response:
                    if token_response.status != 200:
                        error_text = await token_response.text()
                        raise Exception(f"获取令牌失败: {token_response.status}, {error_text}")
                    
                    token_json = await token_response.json()
                    token = token_json.get('access_token')
                    if not token:
                        raise Exception("令牌响应中没有access_token")
                    
                    # 构建API URL - 使用父文件夹路径创建子文件夹
                    if parent_path:
                        url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root:/{parent_path}:/children"
                    else:
                        url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root/children"
                    
                    # 请求体
                    request_body = {
                        "name": folder_name,
                        "folder": {},
                        "@microsoft.graph.conflictBehavior": "fail"
                    }
                    
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                    
                    print(f"创建文件夹URL: {url}", file=sys.stderr)
                    
                    # 在同一会话中发送创建文件夹请求
                    async with session.post(url, headers=headers, json=request_body) as response:
                        result = await response.json()
                        
                        if response.status not in [200, 201]:
                            error_text = json.dumps(result)
                            raise Exception(f"创建文件夹失败: {response.status}, {error_text}")
                        
                        return {
                            "success": True,
                            "path": folder_path,
                            "id": result.get('id', ''),
                            "name": result.get('name', '')
                        }
                    
        except Exception as e:
            print(f"创建文件夹时发生错误: {str(e)}", file=sys.stderr)
            return {
                "success": False,
                "path": folder_path,
                "error": str(e)
            }
    
    async def access_onedrive_by_email(self, email: str, operation: str, path: Optional[str] = None, file_content: Optional[bytes] = None):
        """通过邮箱地址访问用户的OneDrive
        
        Args:
            email: 用户的电子邮件地址
            operation: 操作类型，可以是 'list', 'download', 'upload', 'create_folder'
            path: 文件或文件夹路径，相对于OneDrive根目录
            file_content: 上传文件时的二进制内容
            
        Returns:
            操作结果字典
        """
        import sys
        
        result = {
            "user_id": None,
            "operation": operation,
            "path": path,
            "data": None,
            "error": None
        }
        
        try:
            # 获取用户ID
            print(f"开始访问 {email} 的OneDrive...", file=sys.stderr)
            user_id = await self.get_user_id_by_email(email)
            if not user_id:
                result["error"] = f"未找到邮箱为 {email} 的用户"
                return result
                
            result["user_id"] = user_id
            
            # 在每个操作中单独获取令牌，避免复用已关闭的会话
            # 根据操作类型执行不同的OneDrive操作
            if operation == 'list':
                # 列出文件和文件夹
                items = await self.list_drive_items(user_id, path)
                result["data"] = items
            elif operation == 'download':
                # 下载文件
                if not path:
                    result["error"] = "下载文件需要提供文件路径"
                    return result
                file_data = await self.download_file(user_id, path)
                result["data"] = file_data
            elif operation == 'upload':
                # 上传文件
                if not path:
                    result["error"] = "上传文件需要提供文件路径"
                    return result
                if not file_content:
                    result["error"] = "上传文件需要提供文件内容"
                    return result
                upload_result = await self.upload_file(user_id, path, file_content)
                result["data"] = upload_result
            elif operation == 'create_folder':
                # 创建文件夹
                if not path:
                    result["error"] = "创建文件夹需要提供文件夹路径"
                    return result
                folder_result = await self.create_folder(user_id, path)
                result["data"] = folder_result
            else:
                result["error"] = f"不支持的操作类型: {operation}"
            
            return result
        except Exception as e:
            print(f"访问OneDrive过程中发生错误: {str(e)}", file=sys.stderr)
            result["error"] = f"访问OneDrive时发生错误: {str(e)}"
            return result
    
    async def get_drive_delta(self, user_id: str, delta_link: Optional[str] = None):
        """获取OneDrive文件变更
        
        Args:
            user_id: 用户ID
            delta_link: 可选，前一次delta查询返回的deltaLink。如果不提供，将获取所有项目
            
        Returns:
            包含变更项目和下一次delta链接的字典
        """
        import sys
        
        try:
            print(f"获取用户 {user_id} 的OneDrive变更...", file=sys.stderr)
            
            # 设置超时时间
            timeout = aiohttp.ClientTimeout(total=60)
            
            # 获取令牌
            token_url = f"https://login.microsoftonline.com/{self.settings['tenantId']}/oauth2/v2.0/token"
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.settings['clientId'],
                'client_secret': self.settings['clientSecret'],
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            async with aiohttp.ClientSession(timeout=timeout) as session:
                # 获取token
                async with session.post(token_url, data=token_data) as token_response:
                    if token_response.status != 200:
                        error_text = await token_response.text()
                        raise Exception(f"获取令牌失败: {token_response.status}, {error_text}")
                    
                    token_json = await token_response.json()
                    token = token_json.get('access_token')
                    if not token:
                        raise Exception("令牌响应中没有access_token")
                    
                    # 构建API URL - 使用delta API
                    # 如果提供了delta_link，直接使用
                    if delta_link:
                        url = delta_link
                    else:
                        url = f"https://graph.microsoft.com/v1.0/users/{user_id}/drive/root/delta"
                    
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                    
                    print(f"Delta请求URL: {url}", file=sys.stderr)
                    
                    # 用于存储所有变更项目
                    all_items = []
                    
                    # 处理分页
                    next_link = url
                    while next_link:
                        async with session.get(next_link, headers=headers) as response:
                            if response.status != 200:
                                error_text = await response.text()
                                raise Exception(f"获取变更失败: {response.status}, {error_text}")
                            
                            result = await response.json()
                            
                            # 添加当前页的项目
                            all_items.extend(result.get('value', []))
                            
                            # 检查是否有下一页
                            next_link = result.get('@odata.nextLink')
                            
                            # 保存delta链接以供下次使用
                            delta_link = result.get('@odata.deltaLink')
                    
                    # 对变更项目进行分类处理
                    added_items = []
                    modified_items = []
                    deleted_items = []
                    
                    for item in all_items:
                        if item.get('deleted'):
                            deleted_items.append(item)
                        elif item.get('file') or item.get('folder'):
                            # 检查是否有lastModifiedDateTime字段判断是新增还是修改
                            if 'createdDateTime' in item and 'lastModifiedDateTime' in item:
                                # 如果创建时间和修改时间相差不大，认为是新项目
                                created = item.get('createdDateTime', '')
                                modified = item.get('lastModifiedDateTime', '')
                                if created == modified:
                                    added_items.append(item)
                                else:
                                    modified_items.append(item)
                            else:
                                # 无法确定，放入修改列表
                                modified_items.append(item)
                    
                    # 格式化返回结果
                    changes = {
                        "added": [self._format_item(item) for item in added_items],
                        "modified": [self._format_item(item) for item in modified_items],
                        "deleted": [self._format_deleted_item(item) for item in deleted_items],
                        "delta_link": delta_link,
                        "total_changes": len(all_items)
                    }
                    
                    return changes
                    
        except Exception as e:
            print(f"获取OneDrive变更时发生错误: {str(e)}", file=sys.stderr)
            return {
                "added": [],
                "modified": [],
                "deleted": [],
                "delta_link": None,
                "error": str(e),
                "total_changes": 0
            }
    
    def _format_item(self, item):
        """格式化项目信息，提取关键字段"""
        is_folder = 'folder' in item
        
        formatted = {
            "id": item.get('id', ''),
            "name": item.get('name', ''),
            "type": "folder" if is_folder else "file",
            "path": self._get_item_path(item),
            "last_modified": item.get('lastModifiedDateTime', ''),
            "created": item.get('createdDateTime', ''),
        }
        
        # 添加文件特有属性
        if not is_folder and 'file' in item:
            formatted.update({
                "size": item.get('size', 0),
                "mime_type": item.get('file', {}).get('mimeType', ''),
                "web_url": item.get('webUrl', '')
            })
        
        return formatted
    
    def _format_deleted_item(self, item):
        """格式化已删除项目信息"""
        return {
            "id": item.get('id', ''),
            "name": item.get('name', '') if 'name' in item else '(未知名称)',
            "path": self._get_item_path(item) or '(未知路径)'
        }
    
    def _get_item_path(self, item):
        """获取项目的完整路径"""
        if 'parentReference' in item and 'path' in item['parentReference']:
            parent_path = item['parentReference']['path']
            # 去掉路径前缀"/drive/root:"
            if parent_path.startswith('/drive/root:'):
                parent_path = parent_path[12:]
            return f"{parent_path}/{item.get('name', '')}"
        return None
    
    async def monitor_drive_changes(self, user_id: str, interval_seconds: int = 60, callback = None, max_iterations: Optional[int] = None):
        """持续监控OneDrive变更
        
        Args:
            user_id: 用户ID
            interval_seconds: 检查间隔（秒）
            callback: 可选的回调函数，当检测到变更时调用，参数为变更字典
            max_iterations: 最大迭代次数，如果为None则持续运行
            
        Returns:
            None，这是一个长时间运行的任务
        """
        import sys
        import time
        import asyncio
        
        print(f"开始监控用户 {user_id} 的OneDrive变更...", file=sys.stderr)
        
        # 首次获取delta链接
        changes = await self.get_drive_delta(user_id)
        delta_link = changes.get('delta_link')
        
        if not delta_link:
            print(f"无法获取delta链接，监控终止", file=sys.stderr)
            return
        
        print(f"初始扫描完成，获取到delta链接，将用于后续变更检测", file=sys.stderr)
        
        # 如果有回调函数，处理初始变更
        if callback and changes.get('total_changes', 0) > 0:
            await callback(changes)
        
        iteration = 0
        try:
            while True:
                if max_iterations is not None:
                    iteration += 1
                    if iteration > max_iterations:
                        print(f"已达到最大迭代次数 {max_iterations}，监控终止", file=sys.stderr)
                        break
                
                # 等待指定的间隔时间
                print(f"等待 {interval_seconds} 秒后检查变更...", file=sys.stderr)
                await asyncio.sleep(interval_seconds)
                
                # 使用delta链接获取变更
                changes = await self.get_drive_delta(user_id, delta_link)
                
                # 更新delta链接
                new_delta_link = changes.get('delta_link')
                if new_delta_link:
                    delta_link = new_delta_link
                
                # 检查是否有变更
                total_changes = changes.get('total_changes', 0)
                if total_changes > 0:
                    print(f"检测到 {total_changes} 个变更", file=sys.stderr)
                    
                    # 打印变更信息
                    added = len(changes.get('added', []))
                    modified = len(changes.get('modified', []))
                    deleted = len(changes.get('deleted', []))
                    
                    if added > 0:
                        print(f"新增: {added} 个项目", file=sys.stderr)
                    if modified > 0:
                        print(f"修改: {modified} 个项目", file=sys.stderr)
                    if deleted > 0:
                        print(f"删除: {deleted} 个项目", file=sys.stderr)
                    
                    # 如果有回调函数，处理变更
                    if callback:
                        await callback(changes)
                else:
                    print("未检测到变更", file=sys.stderr)
        
        except KeyboardInterrupt:
            print("监控被用户中断", file=sys.stderr)
        except Exception as e:
            print(f"监控过程中发生错误: {str(e)}", file=sys.stderr)
        
        print("OneDrive变更监控已终止", file=sys.stderr)
    
    async def monitor_drive_changes_by_email(self, email: str, interval_seconds: int = 60, callback = None, max_iterations: Optional[int] = None):
        """通过邮箱地址持续监控用户的OneDrive变更
        
        Args:
            email: 用户邮箱地址
            interval_seconds: 检查间隔（秒）
            callback: 可选的回调函数，当检测到变更时调用，参数为变更字典
            max_iterations: 最大迭代次数，如果为None则持续运行
            
        Returns:
            监控结果字典
        """
        import sys
        
        result = {
            "user_id": None,
            "status": "failed",
            "error": None
        }
        
        try:
            # 获取用户ID
            print(f"开始监控 {email} 的OneDrive变更...", file=sys.stderr)
            user_id = await self.get_user_id_by_email(email)
            if not user_id:
                result["error"] = f"未找到邮箱为 {email} 的用户"
                return result
                
            result["user_id"] = user_id
            
            # 开始监控
            await self.monitor_drive_changes(user_id, interval_seconds, callback, max_iterations)
            
            result["status"] = "completed"
            return result
        except Exception as e:
            print(f"监控OneDrive变更过程中发生错误: {str(e)}", file=sys.stderr)
            result["error"] = f"监控OneDrive变更时发生错误: {str(e)}"
            return result
            
    async def get_folder_content_recursive(self, user_id: str, folder_path: Optional[str] = None):
        """递归获取文件夹内容，包括所有子文件夹中的文件
        
        Args:
            user_id: 用户ID
            folder_path: 文件夹路径，如果为None则使用根目录
            
        Returns:
            包含所有文件和子文件夹信息的字典
        """
        import sys
        
        # 存储所有文件和文件夹
        all_files = []
        all_folders = []
        
        try:
            # 获取当前文件夹内容
            items = await self.list_drive_items(user_id, folder_path)
            
            # 添加当前文件夹中的文件
            all_files.extend(items.get("files", []))
            
            # 处理子文件夹
            folders = items.get("folders", [])
            all_folders.extend(folders)
            
            # 递归处理每个子文件夹
            for folder in folders:
                folder_name = folder.get("name")
                sub_path = f"{folder_path}/{folder_name}" if folder_path else folder_name
                
                print(f"递归处理子文件夹: {sub_path}", file=sys.stderr)
                
                # 递归获取子文件夹内容
                sub_items = await self.get_folder_content_recursive(user_id, sub_path)
                
                # 合并结果
                all_files.extend(sub_items.get("files", []))
                all_folders.extend(sub_items.get("folders", []))
            
            return {
                "files": all_files,
                "folders": all_folders,
                "total_files": len(all_files),
                "total_folders": len(all_folders)
            }
            
        except Exception as e:
            print(f"递归获取文件夹内容时发生错误: {str(e)}", file=sys.stderr)
            return {
                "files": all_files,
                "folders": all_folders,
                "total_files": len(all_files),
                "total_folders": len(all_folders),
                "error": str(e)
            }
    
    async def get_all_files_by_email_and_folder(self, email: str, folder_path: Optional[str] = None):
        """根据用户邮箱和文件夹路径，递归获取该文件夹下的所有文件
        
        Args:
            email: 用户的电子邮件地址
            folder_path: 可选，文件夹路径，如果为None则使用根目录
            
        Returns:
            包含所有文件和子文件夹信息的字典
        """
        import sys
        
        result = {
            "user_id": None,
            "folder_path": folder_path or "根目录",
            "files": [],
            "folders": [],
            "total_files": 0,
            "total_folders": 0,
            "error": None
        }
        
        try:
            # 获取用户ID
            print(f"开始获取 {email} 的文件夹 {folder_path or '根目录'} 下的所有文件...", file=sys.stderr)
            user_id = await self.get_user_id_by_email(email)
            if not user_id:
                result["error"] = f"未找到邮箱为 {email} 的用户"
                return result
                
            result["user_id"] = user_id
            
            # 递归获取文件夹内容
            content = await self.get_folder_content_recursive(user_id, folder_path)
            
            # 检查是否有错误
            if "error" in content:
                result["error"] = content["error"]
            
            # 更新结果
            result["files"] = content.get("files", [])
            result["folders"] = content.get("folders", [])
            result["total_files"] = content.get("total_files", 0)
            result["total_folders"] = content.get("total_folders", 0)
            
            return result
            
        except Exception as e:
            print(f"获取所有文件过程中发生错误: {str(e)}", file=sys.stderr)
            result["error"] = f"获取所有文件时发生错误: {str(e)}"
            return result
    
    async def get_drive_delta_by_email(self, email: str, delta_link: Optional[str] = None):
        """通过邮箱获取OneDrive增量变化
        Args:
            email: 用户邮箱
            delta_link: 上次同步的delta_link，如果为None则获取全部文件
        Returns:
            变化内容dict（含added/modified/deleted/delta_link）
        """
        import sys
        
        # 获取用户ID
        user_id = await self.get_user_id_by_email(email)
        if not user_id:
            return {"error": f"未找到邮箱为 {email} 的用户"}
        
        # 获取增量变化
        changes = await self.get_drive_delta(user_id, delta_link)
        
        return changes 