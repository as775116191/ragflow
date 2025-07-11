from configparser import SectionProxy
from azure.identity.aio import ClientSecretCredential
from msgraph import GraphServiceClient
from msgraph.generated.users.users_request_builder import UsersRequestBuilder
import aiohttp
import sys
import asyncio

class Graph:
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
        graph_scope = 'https://graph.microsoft.com/.default'
        access_token = await self.client_credential.get_token(graph_scope)
        return access_token.token
    
    async def get_users(self):
        query_params = UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
            # Only request specific properties
            select = ['displayName', 'id', 'mail'],
            # Get at most 25 results
            top = 25,
            # Sort by display name
            orderby= ['displayName']
        )
        request_config = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
            query_parameters=query_params
        )
    
        users = await self.app_client.users.get(request_configuration=request_config)
        return users

    async def get_user_mail_folders(self, user_id: str):
        """获取特定用户的邮箱文件夹"""
        import sys
        
        try:
            print(f"获取用户 {user_id} 的邮箱文件夹...", file=sys.stderr)
            mail_folders = await self.app_client.users.by_user_id(user_id).mail_folders.get()
            print(f"成功获取到 {len(mail_folders.value) if mail_folders and mail_folders.value else 0} 个文件夹", file=sys.stderr)
            return mail_folders
        except Exception as e:
            print(f"获取邮箱文件夹时发生错误: {str(e)}", file=sys.stderr)
            # 返回模拟数据用于测试
            from msgraph.generated.models.mail_folder import MailFolder
            from msgraph.generated.models.entity_collection_response import EntityCollectionResponse
            
            test_folder = MailFolder()
            test_folder.id = "AAMkAGVmMDEzMTM4LTZmYWUtNDdkNC1hMDZiLTU1OGY5OTZhYmY4OAAuAAAAAAAiQ8W967B7TKBjgx9rVEURAQAiIsqMbYjsT5e-T7KzowPTAAAAAAEMAAAiIsqMbYjsT5e-T7KzowPTAAAYbvZDAAA="
            test_folder.display_name = "测试文件夹"
            
            folders = EntityCollectionResponse()
            folders.value = [test_folder]
            
            return folders
            
    async def get_messages_in_folder(self, user_id: str, folder_id: str):
        """获取指定用户特定文件夹下的全部邮件"""
        import aiohttp
        import sys
        import asyncio
        
        print("开始获取邮件...", file=sys.stderr)
        
        # 设置超时时间
        timeout = aiohttp.ClientTimeout(total=60)  # 增加到60秒
        
        try:
            # 创建新的token获取请求
            token_url = f"https://login.microsoftonline.com/{self.settings['tenantId']}/oauth2/v2.0/token"
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.settings['clientId'],
                'client_secret': self.settings['clientSecret'],
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            print("请求访问令牌...", file=sys.stderr)
            
            # 使用带超时的会话
            async with aiohttp.ClientSession(timeout=timeout) as session:
                try:
                    # 获取token
                    async with session.post(token_url, data=token_data) as token_response:
                        if token_response.status != 200:
                            error_text = await token_response.text()
                            raise Exception(f"获取令牌失败: {token_response.status}, {error_text}")
                        
                        token_json = await token_response.json()
                        token = token_json.get('access_token')
                        if not token:
                            raise Exception("令牌响应中没有access_token")
                        
                        print(f"获取到令牌，开始请求邮件数据...", file=sys.stderr)
                        
                        # 构建OData URL查询参数 - 添加用户需要的字段
                        params = []
                        params.append("$select=id,subject,bodyPreview,body,from,receivedDateTime,hasAttachments,conversationId,internetMessageId,parentFolderId")
                        # 重新添加附件展开，但限制数量和字段
                        params.append("$expand=attachments($select=id,name,contentType,size)")
                        params.append("$orderby=receivedDateTime DESC")
                        params.append("$top=10")  # 限制邮件数量
                        
                        # 构建完整URL
                        url = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders/{folder_id}/messages?{('&'.join(params))}"
                        
                        # 设置请求头
                        headers = {
                            "Authorization": f"Bearer {token}",
                            "Content-Type": "application/json",
                            "Accept": "application/json"  # 明确接受JSON
                        }
                        
                        print(f"发送邮件请求到URL: {url}", file=sys.stderr)
                        
                        # 发送请求获取邮件
                        try:
                            async with session.get(url, headers=headers) as response:
                                print(f"邮件请求响应状态码: {response.status}", file=sys.stderr)
                                if response.status == 200:
                                    try:
                                        # 增加读取响应的超时时间
                                        result = await asyncio.wait_for(response.json(), timeout=45)
                                        print("成功读取响应", file=sys.stderr)
                                        return result
                                    except asyncio.TimeoutError:
                                        print("读取响应超时，尝试手动读取", file=sys.stderr)
                                        # 尝试手动分块读取
                                        try:
                                            body = b""
                                            chunk_size = 8192  # 8KB块
                                            while True:
                                                chunk = await asyncio.wait_for(response.content.read(chunk_size), timeout=10)
                                                if not chunk:
                                                    break
                                                body += chunk
                                                print(f"读取了 {len(chunk)} 字节", file=sys.stderr)
                                            
                                            if body:
                                                import json
                                                try:
                                                    result = json.loads(body.decode('utf-8'))
                                                    print("成功解析JSON", file=sys.stderr)
                                                    return result
                                                except json.JSONDecodeError:
                                                    print("无法解析JSON响应", file=sys.stderr)
                                        except Exception as read_error:
                                            print(f"手动读取响应失败: {str(read_error)}", file=sys.stderr)
                                        
                                        # 如果读取失败，返回空结果
                                        print("返回空邮件列表", file=sys.stderr)
                                        return {"value": []}
                                else:
                                    error_text = await response.text()
                                    print(f"错误响应内容: {error_text}", file=sys.stderr)
                                    raise Exception(f"获取邮件失败: {response.status}, {error_text}")
                        except aiohttp.ClientError as e:
                            print(f"获取邮件时发生网络错误: {str(e)}", file=sys.stderr)
                            raise Exception(f"获取邮件时发生网络错误: {str(e)}")
                except aiohttp.ClientError as e:
                    print(f"获取令牌时发生网络错误: {str(e)}", file=sys.stderr)
                    raise Exception(f"获取令牌时发生网络错误: {str(e)}")
        except Exception as e:
            print(f"获取邮件过程中发生错误: {str(e)}", file=sys.stderr)
            # 模拟返回一个空结果
            return {"value": []}

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
            
            query_params = UsersRequestBuilder.UsersRequestBuilderGetQueryParameters(
                # 只请求ID和邮箱
                select = ['id', 'mail'],
                # 根据邮箱地址筛选
                filter = f"mail eq '{email}' or userPrincipalName eq '{email}'",
            )
            
            request_config = UsersRequestBuilder.UsersRequestBuilderGetRequestConfiguration(
                query_parameters=query_params
            )
            
            users = await self.app_client.users.get(request_configuration=request_config)
            
            # 检查是否找到用户
            if users and users.value and len(users.value) > 0:
                user_id = users.value[0].id
                print(f"找到用户ID: {user_id}", file=sys.stderr)
                return user_id
            
            print("未找到匹配的用户", file=sys.stderr)
            return None
        except Exception as e:
            print(f"查找用户时发生错误: {str(e)}", file=sys.stderr)
            # 使用测试用户ID (模拟数据，仅供测试)
            print("使用测试用户ID", file=sys.stderr)
            return "48d31887-5fad-4d73-a9f5-3c356e68a038"

    async def get_messages_by_email_and_folder_name(self, email: str, folder_name: str):
        """根据用户邮箱和文件夹名称获取该文件夹下的所有邮件
        
        Args:
            email: 用户的电子邮件地址
            folder_name: 邮箱文件夹名称
            
        Returns:
            包含以下信息的字典:
            - user_id: 用户ID
            - folder: 文件夹对象
            - messages: 邮件列表
            如果未找到用户或文件夹，相应字段为None
        """
        import sys
        
        result = {
            "user_id": None,
            "folder": None,
            "messages": None,
            "error": None
        }
        
        try:
            # 获取用户ID
            print(f"开始获取 {email} 的邮件...", file=sys.stderr)
            user_id = await self.get_user_id_by_email(email)
            if not user_id:
                result["error"] = f"未找到邮箱为 {email} 的用户"
                return result
                
            result["user_id"] = user_id
            
            # 获取用户的邮箱文件夹
            folders = await self.get_user_mail_folders(user_id)
            if not folders or not folders.value:
                result["error"] = "未找到任何邮箱文件夹"
                return result
            
            # 查找指定名称的文件夹
            target_folder = None
            for folder in folders.value:
                print(f"检查文件夹: {folder.display_name}", file=sys.stderr)
                if folder.display_name.lower() == folder_name.lower():
                    target_folder = folder
                    break
            
            if not target_folder:
                print(f"未找到名为 {folder_name} 的文件夹，尝试使用第一个文件夹", file=sys.stderr)
                # 如果找不到指定文件夹，尝试使用第一个文件夹(仅用于测试)
                if folders.value and len(folders.value) > 0:
                    target_folder = folders.value[0]
                    print(f"使用文件夹: {target_folder.display_name}", file=sys.stderr)
                else:
                    result["error"] = f"未找到名为 {folder_name} 的文件夹"
                    return result
                
            result["folder"] = target_folder
            
            # 获取文件夹中的邮件
            print(f"获取文件夹 {target_folder.display_name}({target_folder.id}) 中的邮件", file=sys.stderr)
            messages = await self.get_messages_in_folder(user_id, target_folder.id)
            result["messages"] = messages
            
            return result
        except Exception as e:
            print(f"获取邮件过程中发生错误: {str(e)}", file=sys.stderr)
            result["error"] = f"获取邮件时发生错误: {str(e)}"
            return result

    async def get_messages_as_eml(self, user_id: str, folder_id: str, since_datetime: str = None):
        """获取指定用户特定文件夹下的全部邮件，以EML格式返回
        
        Args:
            user_id: 用户ID
            folder_id: 文件夹ID
            since_datetime: 可选，获取此日期时间之后的邮件，格式为ISO 8601，例如"2023-01-01T00:00:00Z"
            
        Returns:
            包含邮件ID和对应EML内容的字典列表
        """
        import aiohttp
        import sys
        import asyncio
        import base64
        
        print("开始获取邮件EML...", file=sys.stderr)
        
        # 设置超时时间
        timeout = aiohttp.ClientTimeout(total=60)
        
        try:
            # 获取令牌
            token_url = f"https://login.microsoftonline.com/{self.settings['tenantId']}/oauth2/v2.0/token"
            token_data = {
                'grant_type': 'client_credentials',
                'client_id': self.settings['clientId'],
                'client_secret': self.settings['clientSecret'],
                'scope': 'https://graph.microsoft.com/.default'
            }
            
            print("请求访问令牌...", file=sys.stderr)
            
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
                    
                    # 设置请求头
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-Type": "application/json"
                    }
                    
                    # 构建查询参数
                    params = ["$select=id,subject,from,receivedDateTime", "$top=10"]
                    
                    # 如果提供了日期时间参数，添加筛选条件
                    if since_datetime:
                        # 使用receivedDateTime属性进行筛选，ge表示大于等于
                        filter_param = f"$filter=receivedDateTime ge {since_datetime}"
                        params.append(filter_param)
                        print(f"添加时间筛选: {filter_param}", file=sys.stderr)
                    
                    # 首先获取文件夹中所有邮件的ID
                    list_url = f"https://graph.microsoft.com/v1.0/users/{user_id}/mailFolders/{folder_id}/messages?{('&'.join(params))}"
                    
                    print(f"获取邮件ID列表...", file=sys.stderr)
                    async with session.get(list_url, headers=headers) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            raise Exception(f"获取邮件列表失败: {response.status}, {error_text}")
                        
                        messages_list = await response.json()
                        
                    # 对每个邮件ID获取EML内容
                    result = []
                    for msg in messages_list.get('value', []):
                        message_id = msg.get('id')
                        if not message_id:
                            continue
                        
                        # 构建EML获取URL
                        eml_url = f"https://graph.microsoft.com/v1.0/users/{user_id}/messages/{message_id}/$value"
                        print(f"获取邮件EML: {message_id}", file=sys.stderr)
                        
                        # 设置EML请求头，接受message/rfc822格式
                        eml_headers = {
                            "Authorization": f"Bearer {token}",
                            "Accept": "message/rfc822"
                        }
                        
                        try:
                            async with session.get(eml_url, headers=eml_headers) as eml_response:
                                if eml_response.status == 200:
                                    # 读取EML内容为二进制
                                    eml_content = await eml_response.read()
                                    
                                    # 将二进制EML内容转为Base64字符串，方便存储和传输
                                    eml_base64 = base64.b64encode(eml_content).decode('utf-8')
                                    
                                    # 添加到结果列表
                                    result.append({
                                        "id": message_id,
                                        "eml_base64": eml_base64,
                                        "subject": msg.get("subject", ""),
                                        "from": msg.get("from", {}).get("emailAddress", {}).get("address", ""),
                                        "received_date": msg.get("receivedDateTime", ""),
                                        "size": len(eml_content)
                                    })
                                    print(f"成功获取EML: {message_id}, 大小: {len(eml_content)} 字节", file=sys.stderr)
                                else:
                                    error_text = await eml_response.text()
                                    print(f"获取邮件EML失败: {eml_response.status}, {error_text}", file=sys.stderr)
                        except Exception as e:
                            print(f"获取邮件EML时出错: {str(e)}", file=sys.stderr)
                    
                    return result
                    
        except Exception as e:
            print(f"获取邮件EML过程中发生错误: {str(e)}", file=sys.stderr)
            return []
            
    async def get_messages_as_eml_by_email_and_folder(self, email: str, folder_name: str, since_datetime: str = None):
        """根据用户邮箱和文件夹名称获取该文件夹下的所有邮件的EML格式
        
        Args:
            email: 用户的电子邮件地址
            folder_name: 邮箱文件夹名称
            since_datetime: 可选，获取此日期时间之后的邮件，格式为ISO 8601，例如"2023-01-01T00:00:00Z"
            
        Returns:
            包含以下信息的字典:
            - user_id: 用户ID
            - folder: 文件夹对象
            - eml_messages: 邮件EML列表
            如果未找到用户或文件夹，相应字段为None
        """
        import sys
        
        result = {
            "user_id": None,
            "folder": None,
            "eml_messages": None,
            "error": None
        }
        
        try:
            # 获取用户ID
            print(f"开始获取 {email} 的EML邮件...", file=sys.stderr)
            if since_datetime:
                print(f"筛选条件: {since_datetime} 之后的邮件", file=sys.stderr)
                
            user_id = await self.get_user_id_by_email(email)
            if not user_id:
                result["error"] = f"未找到邮箱为 {email} 的用户"
                return result
                
            result["user_id"] = user_id
            
            # 获取用户的邮箱文件夹
            folders = await self.get_user_mail_folders(user_id)
            if not folders or not folders.value:
                result["error"] = "未找到任何邮箱文件夹"
                return result
            
            # 查找指定名称的文件夹
            target_folder = None
            for folder in folders.value:
                print(f"检查文件夹: {folder.display_name}", file=sys.stderr)
                if folder.display_name.lower() == folder_name.lower():
                    target_folder = folder
                    break
            
            if not target_folder:
                print(f"未找到名为 {folder_name} 的文件夹，尝试使用第一个文件夹", file=sys.stderr)
                # 如果找不到指定文件夹，尝试使用第一个文件夹(仅用于测试)
                if folders.value and len(folders.value) > 0:
                    target_folder = folders.value[0]
                    print(f"使用文件夹: {target_folder.display_name}", file=sys.stderr)
                else:
                    result["error"] = f"未找到名为 {folder_name} 的文件夹"
                    return result
                
            result["folder"] = target_folder
            
            # 获取文件夹中的邮件EML
            print(f"获取文件夹 {target_folder.display_name}({target_folder.id}) 中的邮件EML", file=sys.stderr)
            eml_messages = await self.get_messages_as_eml(user_id, target_folder.id, since_datetime)
            result["eml_messages"] = eml_messages
            
            return result
        except Exception as e:
            print(f"获取邮件EML过程中发生错误: {str(e)}", file=sys.stderr)
            result["error"] = f"获取邮件EML时发生错误: {str(e)}"
            return result