#
#  Copyright 2024 The InfiniFlow Authors. All Rights Reserved.
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
from datetime import datetime

from peewee import fn

from api.db import StatusEnum, TenantPermission
from api.db.db_models import DB, Document, Knowledgebase, Tenant, User, UserTenant
from api.db.services.common_service import CommonService
from api.utils import current_timestamp, datetime_format


class KnowledgebaseService(CommonService):
    """Service class for managing knowledge base operations.

    This class extends CommonService to provide specialized functionality for knowledge base
    management, including document parsing status tracking, access control, and configuration
    management. It handles operations such as listing, creating, updating, and deleting
    knowledge bases, as well as managing their associated documents and permissions.

    The class implements a comprehensive set of methods for:
    - Document parsing status verification
    - Knowledge base access control
    - Parser configuration management
    - Tenant-based knowledge base organization

    Attributes:
        model: The Knowledgebase model class for database operations.
    """
    model = Knowledgebase

    @classmethod
    @DB.connection_context()
    def accessible4deletion(cls, kb_id, user_id):
        """Check if a knowledge base can be deleted by a specific user.

        This method verifies whether a user has permission to delete a knowledge base
        by checking if they are the creator of that knowledge base.

        Args:
            kb_id (str): The unique identifier of the knowledge base to check.
            user_id (str): The unique identifier of the user attempting the deletion.

        Returns:
            bool: True if the user has permission to delete the knowledge base,
                  False if the user doesn't have permission or the knowledge base doesn't exist.

        Example:
            >>> KnowledgebaseService.accessible4deletion("kb123", "user456")
            True

        Note:
            - This method only checks creator permissions
            - A return value of False can mean either:
                1. The knowledge base doesn't exist
                2. The user is not the creator of the knowledge base
        """
        # Check if a knowledge base can be deleted by a user
        docs = cls.model.select(
            cls.model.id).where(cls.model.id == kb_id, cls.model.created_by == user_id).paginate(0, 1)
        docs = docs.dicts()
        if not docs:
            return False
        return True

    @classmethod
    @DB.connection_context()
    def is_parsed_done(cls, kb_id):
        # Check if all documents in the knowledge base have completed parsing
        #
        # Args:
        #     kb_id: Knowledge base ID
        #
        # Returns:
        #     If all documents are parsed successfully, returns (True, None)
        #     If any document is not fully parsed, returns (False, error_message)
        from api.db import TaskStatus
        from api.db.services.document_service import DocumentService

        # Get knowledge base information
        kbs = cls.query(id=kb_id)
        if not kbs:
            return False, "Knowledge base not found"
        kb = kbs[0]

        # Get all documents in the knowledge base
        docs, _ = DocumentService.get_by_kb_id(kb_id, 1, 1000, "create_time", True, "", [], [])

        # Check parsing status of each document
        for doc in docs:
            # If document is being parsed, don't allow chat creation
            if doc['run'] == TaskStatus.RUNNING.value or doc['run'] == TaskStatus.CANCEL.value or doc['run'] == TaskStatus.FAIL.value:
                return False, f"Document '{doc['name']}' in dataset '{kb.name}' is still being parsed. Please wait until all documents are parsed before starting a chat."
            # If document is not yet parsed and has no chunks, don't allow chat creation
            if doc['run'] == TaskStatus.UNSTART.value and doc['chunk_num'] == 0:
                return False, f"Document '{doc['name']}' in dataset '{kb.name}' has not been parsed yet. Please parse all documents before starting a chat."

        return True, None

    @classmethod
    @DB.connection_context()
    def list_documents_by_ids(cls, kb_ids):
        # Get document IDs associated with given knowledge base IDs
        # Args:
        #     kb_ids: List of knowledge base IDs
        # Returns:
        #     List of document IDs
        doc_ids = cls.model.select(Document.id.alias("document_id")).join(Document, on=(cls.model.id == Document.kb_id)).where(
            cls.model.id.in_(kb_ids)
        )
        doc_ids = list(doc_ids.dicts())
        doc_ids = [doc["document_id"] for doc in doc_ids]
        return doc_ids

    @classmethod
    @DB.connection_context()
    def get_by_tenant_ids(cls, joined_tenant_ids, user_id,
                          page_number, items_per_page,
                          orderby, desc, keywords,
                          parser_id=None
                          ):
        # Get knowledge bases by tenant IDs with pagination and filtering
        # Args:
        #     joined_tenant_ids: List of tenant IDs
        #     user_id: Current user ID
        #     page_number: Page number for pagination
        #     items_per_page: Number of items per page
        #     orderby: Field to order by
        #     desc: Boolean indicating descending order
        #     keywords: Search keywords
        #     parser_id: Optional parser ID filter
        # Returns:
        #     Tuple of (knowledge_base_list, total_count)
        fields = [
            cls.model.id,
            cls.model.avatar,
            cls.model.name,
            cls.model.language,
            cls.model.description,
            cls.model.tenant_id,
            cls.model.permission,
            cls.model.role_ids,
            cls.model.doc_num,
            cls.model.token_num,
            cls.model.chunk_num,
            cls.model.parser_id,
            cls.model.embd_id,
            User.nickname,
            User.avatar.alias('tenant_avatar'),
            cls.model.update_time
        ]
        
        # 获取用户角色ID列表
        from api.db.services.role_service import RoleService
        user_roles = RoleService.get_user_roles(user_id)
        user_role_ids = [role['id'] for role in user_roles]
        
        if keywords:
            kbs = cls.model.select(*fields).join(User, on=(cls.model.tenant_id == User.id)).where(
                (
                    # 用户创建的知识库
                    (cls.model.tenant_id == user_id) |
                    # 或 团队内共享的知识库
                    (cls.model.tenant_id.in_(joined_tenant_ids) & 
                     (cls.model.permission == TenantPermission.TEAM.value))
                ) &
                (cls.model.status == StatusEnum.VALID.value) &
                (fn.LOWER(cls.model.name).contains(keywords.lower()))
            )
        else:
            kbs = cls.model.select(*fields).join(User, on=(cls.model.tenant_id == User.id)).where(
                (
                    # 用户创建的知识库
                    (cls.model.tenant_id == user_id) |
                    # 或 团队内共享的知识库
                    (cls.model.tenant_id.in_(joined_tenant_ids) & 
                     (cls.model.permission == TenantPermission.TEAM.value))
                ) &
                (cls.model.status == StatusEnum.VALID.value)
            )
        
        if parser_id:
            kbs = kbs.where(cls.model.parser_id == parser_id)
        if desc:
            kbs = kbs.order_by(cls.model.getter_by(orderby).desc())
        else:
            kbs = kbs.order_by(cls.model.getter_by(orderby).asc())

        # 获取符合基本条件的知识库列表
        kb_list = list(kbs.dicts())
        
        # 处理基于角色的权限
        role_based_kbs = []
        if user_role_ids:
            role_kbs = cls.model.select(*fields).join(User, on=(cls.model.tenant_id == User.id)).where(
                (cls.model.permission == TenantPermission.ROLE.value) &
                (cls.model.status == StatusEnum.VALID.value)
            )
            
            if keywords:
                role_kbs = role_kbs.where(fn.LOWER(cls.model.name).contains(keywords.lower()))
                
            if parser_id:
                role_kbs = role_kbs.where(cls.model.parser_id == parser_id)
                
            role_kbs = list(role_kbs.dicts())
            
            # 过滤出用户有权限的基于角色的知识库
            for kb in role_kbs:
                kb_role_ids = kb.get('role_ids', [])
                if not kb_role_ids:
                    continue
                    
                # 检查是否为知识库创建者
                if kb['tenant_id'] == user_id:
                    role_based_kbs.append(kb)
                    continue
                    
                # 检查用户角色与知识库角色是否有交集
                for role_id in user_role_ids:
                    if role_id in kb_role_ids:
                        role_based_kbs.append(kb)
                        break
        
        # 合并常规知识库列表和基于角色的知识库列表
        all_kbs = kb_list + role_based_kbs
        
        # 去重（可能有重复的知识库）
        unique_kbs = []
        kb_ids = set()
        for kb in all_kbs:
            if kb['id'] not in kb_ids:
                unique_kbs.append(kb)
                kb_ids.add(kb['id'])
        
        # 重新排序
        if desc:
            unique_kbs.sort(key=lambda x: x.get(orderby, 0), reverse=True)
        else:
            unique_kbs.sort(key=lambda x: x.get(orderby, 0))
            
        count = len(unique_kbs)
        
        # 分页
        if page_number and items_per_page:
            start_idx = (page_number - 1) * items_per_page
            end_idx = start_idx + items_per_page
            unique_kbs = unique_kbs[start_idx:end_idx]

        return unique_kbs, count

    @classmethod
    @DB.connection_context()
    def get_kb_ids(cls, tenant_id):
        # Get all knowledge base IDs for a tenant
        # Args:
        #     tenant_id: Tenant ID
        # Returns:
        #     List of knowledge base IDs
        fields = [
            cls.model.id,
        ]
        kbs = cls.model.select(*fields).where(cls.model.tenant_id == tenant_id)
        kb_ids = [kb.id for kb in kbs]
        return kb_ids

    @classmethod
    @DB.connection_context()
    def get_detail(cls, kb_id):
        # Get detailed information about a knowledge base
        # Args:
        #     kb_id: Knowledge base ID
        # Returns:
        #     Dictionary containing knowledge base details
        fields = [
            cls.model.id,
            cls.model.embd_id,
            cls.model.avatar,
            cls.model.name,
            cls.model.language,
            cls.model.description,
            cls.model.permission,
            cls.model.role_ids,
            cls.model.doc_num,
            cls.model.token_num,
            cls.model.chunk_num,
            cls.model.parser_id,
            cls.model.parser_config,
            cls.model.pagerank,
            cls.model.create_time,
            cls.model.update_time
            ]
        kbs = cls.model.select(*fields).join(Tenant, on=(
            (Tenant.id == cls.model.tenant_id) & (Tenant.status == StatusEnum.VALID.value))).where(
            (cls.model.id == kb_id),
            (cls.model.status == StatusEnum.VALID.value)
        )
        if not kbs:
            return
        d = kbs[0].to_dict()
        return d

    @classmethod
    @DB.connection_context()
    def update_parser_config(cls, id, config):
        # Update parser configuration for a knowledge base
        # Args:
        #     id: Knowledge base ID
        #     config: New parser configuration
        e, m = cls.get_by_id(id)
        if not e:
            raise LookupError(f"knowledgebase({id}) not found.")

        def dfs_update(old, new):
            # Deep update of nested configuration
            for k, v in new.items():
                if k not in old:
                    old[k] = v
                    continue
                if isinstance(v, dict):
                    assert isinstance(old[k], dict)
                    dfs_update(old[k], v)
                elif isinstance(v, list):
                    assert isinstance(old[k], list)
                    old[k] = list(set(old[k] + v))
                else:
                    old[k] = v

        dfs_update(m.parser_config, config)
        cls.update_by_id(id, {"parser_config": m.parser_config})

    @classmethod
    @DB.connection_context()
    def delete_field_map(cls, id):
        e, m = cls.get_by_id(id)
        if not e:
            raise LookupError(f"knowledgebase({id}) not found.")

        m.parser_config.pop("field_map", None)
        cls.update_by_id(id, {"parser_config": m.parser_config})

    @classmethod
    @DB.connection_context()
    def get_field_map(cls, ids):
        # Get field mappings for knowledge bases
        # Args:
        #     ids: List of knowledge base IDs
        # Returns:
        #     Dictionary of field mappings
        conf = {}
        for k in cls.get_by_ids(ids):
            if k.parser_config and "field_map" in k.parser_config:
                conf.update(k.parser_config["field_map"])
        return conf

    @classmethod
    @DB.connection_context()
    def get_by_name(cls, kb_name, tenant_id):
        # Get knowledge base by name and tenant ID
        # Args:
        #     kb_name: Knowledge base name
        #     tenant_id: Tenant ID
        # Returns:
        #     Tuple of (exists, knowledge_base)
        kb = cls.model.select().where(
            (cls.model.name == kb_name)
            & (cls.model.tenant_id == tenant_id)
            & (cls.model.status == StatusEnum.VALID.value)
        )
        if kb:
            return True, kb[0]
        return False, None

    @classmethod
    @DB.connection_context()
    def get_all_ids(cls):
        # Get all knowledge base IDs
        # Returns:
        #     List of all knowledge base IDs
        return [m["id"] for m in cls.model.select(cls.model.id).dicts()]

    @classmethod
    @DB.connection_context()
    def get_list(cls, joined_tenant_ids, user_id,
                 page_number, items_per_page, orderby, desc, id, name):
        # Get list of knowledge bases with filtering and pagination
        # Args:
        #     joined_tenant_ids: List of tenant IDs
        #     user_id: Current user ID
        #     page_number: Page number for pagination
        #     items_per_page: Number of items per page
        #     orderby: Field to order by
        #     desc: Boolean indicating descending order
        #     id: Optional ID filter
        #     name: Optional name filter
        # Returns:
        #     List of knowledge bases
        kbs = cls.model.select()
        if id:
            kbs = kbs.where(cls.model.id == id)
        if name:
            kbs = kbs.where(cls.model.name == name)
        kbs = kbs.where(
            ((cls.model.tenant_id.in_(joined_tenant_ids) & (cls.model.permission ==
                                                            TenantPermission.TEAM.value)) | (
                cls.model.tenant_id == user_id))
            & (cls.model.status == StatusEnum.VALID.value)
        )
        if desc:
            kbs = kbs.order_by(cls.model.getter_by(orderby).desc())
        else:
            kbs = kbs.order_by(cls.model.getter_by(orderby).asc())

        kbs = kbs.paginate(page_number, items_per_page)

        return list(kbs.dicts())

    @classmethod
    @DB.connection_context()
    def accessible(cls, kb_id, user_id):
        # Check if a knowledge base is accessible by a user
        # Args:
        #     kb_id: Knowledge base ID
        #     user_id: User ID
        # Returns:
        #     Boolean indicating accessibility
        
        # 首先检查是否为知识库创建者，创建者必定有访问权限
        is_creator = cls.model.select(cls.model.id).where(
            cls.model.id == kb_id, 
            cls.model.created_by == user_id, 
            cls.model.status == StatusEnum.VALID.value
        ).exists()
        
        if is_creator:
            return True
        
        # 获取知识库详细信息
        e, kb = cls.get_by_id(kb_id)
        if not e:
            return False
            
        # 检查权限设置
        if kb.permission == TenantPermission.ME.value:
            # 私有知识库，只有创建者有权限
            return False
        elif kb.permission == TenantPermission.TEAM.value:
            # 团队知识库，检查用户是否在团队中
            docs = cls.model.select(cls.model.id).join(
                UserTenant, on=(UserTenant.tenant_id == Knowledgebase.tenant_id)
            ).where(
                cls.model.id == kb_id, 
                UserTenant.user_id == user_id,
                cls.model.status == StatusEnum.VALID.value,
                UserTenant.status == StatusEnum.VALID.value
            ).exists()
            return docs
        elif kb.permission == TenantPermission.ROLE.value:
            # 基于角色的权限检查
            from api.db.services.role_service import RoleService
            
            # 获取知识库关联的角色ID列表
            role_ids = kb.role_ids if hasattr(kb, 'role_ids') and kb.role_ids else []
            
            if not role_ids:
                return False
                
            # 获取用户所有角色
            user_roles = RoleService.get_user_roles(user_id)
            user_role_ids = [role['id'] for role in user_roles]
            
            # 检查用户的角色是否与知识库允许的角色有交集
            for role_id in role_ids:
                if role_id in user_role_ids:
                    return True
            
            return False
        
        return False

    @classmethod
    @DB.connection_context()
    def get_kb_by_id(cls, kb_id, user_id):
        # Get knowledge base by ID and user ID
        # Args:
        #     kb_id: Knowledge base ID
        #     user_id: User ID
        # Returns:
        #     List containing knowledge base information
        kbs = cls.model.select().join(UserTenant, on=(UserTenant.tenant_id == Knowledgebase.tenant_id)
                                      ).where(cls.model.id == kb_id, UserTenant.user_id == user_id).paginate(0, 1)
        kbs = kbs.dicts()
        return list(kbs)

    @classmethod
    @DB.connection_context()
    def get_kb_by_name(cls, kb_name, user_id):
        # Get knowledge base by name and user ID
        # Args:
        #     kb_name: Knowledge base name
        #     user_id: User ID
        # Returns:
        #     List containing knowledge base information
        kbs = cls.model.select().join(UserTenant, on=(UserTenant.tenant_id == Knowledgebase.tenant_id)
                                      ).where(cls.model.name == kb_name, UserTenant.user_id == user_id).paginate(0, 1)
        kbs = kbs.dicts()
        return list(kbs)

    @classmethod
    @DB.connection_context()
    def atomic_increase_doc_num_by_id(cls, kb_id):
        from api.db.services.document_service import DocumentService
        
        # 获取知识库中的实际文档数量（不包括文件夹）
        docs = DocumentService.query(kb_id=kb_id)
        doc_count = len(docs)
        
        # 更新知识库的文档数量
        data = {}
        data["doc_num"] = doc_count
        data["update_time"] = current_timestamp()
        
        cls.model.update(**data).where(cls.model.id == kb_id).execute()
        return True

    @classmethod
    @DB.connection_context()
    def update_document_number_in_init(cls, kb_id, doc_num):
        """
        Only use this function when init system
        """
        ok, kb = cls.get_by_id(kb_id)
        if not ok:
            return
        kb.doc_num = doc_num

        dirty_fields = kb.dirty_fields
        if cls.model._meta.combined.get("update_time") in dirty_fields:
            dirty_fields.remove(cls.model._meta.combined["update_time"])

        if cls.model._meta.combined.get("update_date") in dirty_fields:
            dirty_fields.remove(cls.model._meta.combined["update_date"])

        try:
            kb.save(only=dirty_fields)
        except ValueError as e:
            if str(e) == "no data to save!":
                pass # that's OK
            else:
                raise e

    @classmethod
    @DB.connection_context()
    def get_delta_link(cls, kb_id):
        kb = cls.model.get_or_none(cls.model.id == kb_id)
        if kb:
            return kb.delta_link
        return None

    @classmethod
    @DB.connection_context()
    def update_delta_link(cls, kb_id, delta_link):
        return cls.model.update({cls.model.delta_link: delta_link}).where(cls.model.id == kb_id).execute()

