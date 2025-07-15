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
from typing import List, Optional, Dict, Any, Tuple, Union

import peewee

from api.db.db_models import DB, Role, RoleUser, RolePermission, User, UserTenant
from api.db.services.common_service import CommonService
from api.utils import get_uuid, current_timestamp, datetime_format
from api.db import StatusEnum


class RoleService(CommonService):
    """Service class for managing role-related database operations.

    This class extends CommonService to provide specialized functionality for role management,
    including creation, updates, and deletions.

    Attributes:
        model: The Role model class for database operations.
    """
    model = Role

    @classmethod
    @DB.connection_context()
    def create_role(cls, name: str, description: str, created_by: str, tenant_id: str) -> str:
        """Create a new role.

        Args:
            name: Role name.
            description: Role description.
            created_by: ID of the user creating the role.
            tenant_id: ID of the tenant this role belongs to.

        Returns:
            The ID of the newly created role.
        """
        role_id = get_uuid()
        role = Role.create(
            id=role_id,
            name=name,
            description=description,
            created_by=created_by,
            tenant_id=tenant_id,
            create_time=current_timestamp(),
            update_time=current_timestamp(),
            status=StatusEnum.VALID.value
        )
        return role_id

    @classmethod
    @DB.connection_context()
    def update_role(cls, role_id: str, name: str = None, description: str = None) -> bool:
        """Update a role's information.

        Args:
            role_id: The ID of the role to update.
            name: New role name (optional).
            description: New role description (optional).

        Returns:
            True if update was successful, False otherwise.
        """
        try:
            update_data = {}
            if name is not None:
                update_data["name"] = name
            if description is not None:
                update_data["description"] = description
            
            if update_data:
                update_data["update_time"] = current_timestamp()
                return Role.update(update_data).where(
                    (Role.id == role_id) & 
                    (Role.status == StatusEnum.VALID.value)
                ).execute() > 0
            return True
        except Exception:
            return False

    @classmethod
    @DB.connection_context()
    def delete_role(cls, role_id: str) -> bool:
        """Mark a role as deleted.

        Args:
            role_id: The ID of the role to delete.

        Returns:
            True if deletion was successful, False otherwise.
        """
        try:
            with DB.atomic():
                # Mark role as deleted
                result = Role.update(status=StatusEnum.INVALID.value).where(
                    (Role.id == role_id) & 
                    (Role.status == StatusEnum.VALID.value)
                ).execute()
                
                # Mark role users as deleted
                RoleUser.update(status=StatusEnum.INVALID.value).where(
                    (RoleUser.role_id == role_id) & 
                    (RoleUser.status == StatusEnum.VALID.value)
                ).execute()
                
                # Mark role permissions as deleted
                RolePermission.update(status=StatusEnum.INVALID.value).where(
                    (RolePermission.role_id == role_id) & 
                    (RolePermission.status == StatusEnum.VALID.value)
                ).execute()
                
                return result > 0
        except Exception:
            return False

    @classmethod
    @DB.connection_context()
    def get_role(cls, role_id: str) -> Optional[Dict[str, Any]]:
        """Get role details by ID.

        Args:
            role_id: The ID of the role.

        Returns:
            Role information as a dictionary, or None if not found.
        """
        try:
            role = Role.select().where(
                (Role.id == role_id) & 
                (Role.status == StatusEnum.VALID.value)
            ).get()
            
            role_dict = role.to_dict()
            
            # Get role users
            role_users = (RoleUser
                .select(RoleUser, User.nickname, User.email)
                .join(User, on=(RoleUser.user_id == User.id))
                .where(
                    (RoleUser.role_id == role_id) & 
                    (RoleUser.status == StatusEnum.VALID.value) &
                    (User.status == StatusEnum.VALID.value)
                )
                .order_by(RoleUser.create_time.desc())
                .dicts())
            
            # Get role permissions
            role_permissions = (RolePermission
                .select()
                .where(
                    (RolePermission.role_id == role_id) & 
                    (RolePermission.status == StatusEnum.VALID.value)
                )
                .order_by(RolePermission.create_time.desc())
                .dicts())
            
            role_dict["users"] = list(role_users)
            role_dict["permissions"] = list(role_permissions)
            
            return role_dict
        except peewee.DoesNotExist:
            return None
        except Exception:
            return None

    @classmethod
    @DB.connection_context()
    def get_all_roles(cls) -> List[Dict[str, Any]]:
        """Get all roles.

        Returns:
            List of role information dictionaries.
        """
        try:
            roles = (Role
                .select()
                .where(Role.status == StatusEnum.VALID.value)
                .order_by(Role.create_time.desc())
                .dicts())
            return list(roles)
        except Exception:
            return []

    @classmethod
    @DB.connection_context()
    def add_user_to_role(cls, role_id: str, user_id: str) -> bool:
        """Add a user to a role.

        Args:
            role_id: The ID of the role.
            user_id: The ID of the user to add.

        Returns:
            True if operation was successful, False otherwise.
        """
        try:
            # 检查是否存在已被标记为无效的记录
            existing_record = RoleUser.select().where(
                (RoleUser.role_id == role_id) & 
                (RoleUser.user_id == user_id)
            ).first()

            if existing_record:
                # 如果记录存在，更新状态为有效
                result = RoleUser.update(
                    status=StatusEnum.VALID.value,
                    create_time=current_timestamp()
                ).where(
                    (RoleUser.role_id == role_id) & 
                    (RoleUser.user_id == user_id)
                ).execute()
                return result > 0
            else:
                # 添加新记录
                role_user = RoleUser.create(
                    id=get_uuid(),
                    role_id=role_id,
                    user_id=user_id,
                    create_time=current_timestamp(),
                    status=StatusEnum.VALID.value
                )
                return True
        except Exception as e:
            print(f"Error adding user to role: {e}")
            return False

    @classmethod
    @DB.connection_context()
    def remove_user_from_role(cls, role_id: str, user_id: str) -> bool:
        """Remove a user from a role.

        Args:
            role_id: The ID of the role.
            user_id: The ID of the user to remove.

        Returns:
            True if operation was successful, False otherwise.
        """
        try:
            result = RoleUser.update(status=StatusEnum.INVALID.value).where(
                (RoleUser.role_id == role_id) & 
                (RoleUser.user_id == user_id) & 
                (RoleUser.status == StatusEnum.VALID.value)
            ).execute()
            return result > 0
        except Exception:
            return False

    @classmethod
    @DB.connection_context()
    def add_permission_to_role(cls, role_id: str, resource_type: str, 
                             resource_id: str, resource_name: str, 
                             permission_type: str) -> bool:
        """Add a permission to a role.

        Args:
            role_id: The ID of the role.
            resource_type: Type of resource (e.g., 'knowledgebase').
            resource_id: ID of the resource.
            resource_name: Name of the resource.
            permission_type: Type of permission (e.g., 'read', 'write', 'admin').

        Returns:
            True if operation was successful, False otherwise.
        """
        try:
            # Check if the permission already exists
            exists = RolePermission.select().where(
                (RolePermission.role_id == role_id) & 
                (RolePermission.resource_id == resource_id) & 
                (RolePermission.permission_type == permission_type) & 
                (RolePermission.status == StatusEnum.VALID.value)
            ).exists()
            
            if exists:
                return True
            
            # Add the permission
            permission = RolePermission.create(
                id=get_uuid(),
                role_id=role_id,
                resource_type=resource_type,
                resource_id=resource_id,
                resource_name=resource_name,
                permission_type=permission_type,
                create_time=current_timestamp(),
                status=StatusEnum.VALID.value
            )
            return True
        except Exception:
            return False

    @classmethod
    @DB.connection_context()
    def remove_permission_from_role(cls, permission_id: str) -> bool:
        """Remove a permission from a role.

        Args:
            permission_id: The ID of the permission to remove.

        Returns:
            True if operation was successful, False otherwise.
        """
        try:
            result = RolePermission.update(status=StatusEnum.INVALID.value).where(
                (RolePermission.id == permission_id) & 
                (RolePermission.status == StatusEnum.VALID.value)
            ).execute()
            return result > 0
        except Exception:
            return False

    @classmethod
    @DB.connection_context()
    def update_role_permissions(cls, role_id: str, permissions: List[Dict[str, Any]]) -> bool:
        """Update a role's permissions.

        Args:
            role_id: The ID of the role.
            permissions: List of permission dictionaries.

        Returns:
            True if operation was successful, False otherwise.
        """
        try:
            with DB.atomic():
                # Mark all existing permissions as invalid
                RolePermission.update(status=StatusEnum.INVALID.value).where(
                    (RolePermission.role_id == role_id) & 
                    (RolePermission.status == StatusEnum.VALID.value)
                ).execute()
                
                # Add new permissions
                for perm in permissions:
                    RolePermission.create(
                        id=get_uuid(),
                        role_id=role_id,
                        resource_type=perm.get("resource_type", "knowledgebase"),
                        resource_id=perm["resource_id"],
                        resource_name=perm["resource_name"],
                        permission_type=perm["permission_type"],
                        create_time=current_timestamp(),
                        status=StatusEnum.VALID.value
                    )
                return True
        except Exception:
            return False

    @classmethod
    @DB.connection_context()
    def get_user_roles(cls, user_id: str) -> List[Dict[str, Any]]:
        """Get roles for a user.

        Args:
            user_id: The ID of the user.

        Returns:
            List of role information dictionaries.
        """
        try:
            roles = (Role
                .select(Role, RoleUser.id.alias("role_user_id"))
                .join(RoleUser, on=(Role.id == RoleUser.role_id))
                .where(
                    (RoleUser.user_id == user_id) & 
                    (RoleUser.status == StatusEnum.VALID.value) &
                    (Role.status == StatusEnum.VALID.value)
                )
                .order_by(Role.create_time.desc())
                .dicts())
            return list(roles)
        except Exception:
            return []

    @classmethod
    @DB.connection_context()
    def check_user_permission(cls, user_id: str, resource_id: str, required_permission: str) -> bool:
        """Check if a user has a specific permission for a resource.

        Args:
            user_id: The ID of the user.
            resource_id: The ID of the resource.
            required_permission: The permission type required.

        Returns:
            True if the user has the permission, False otherwise.
        """
        try:
            # Get all roles for the user
            roles = (Role
                .select(Role.id)
                .join(RoleUser, on=(Role.id == RoleUser.role_id))
                .where(
                    (RoleUser.user_id == user_id) & 
                    (RoleUser.status == StatusEnum.VALID.value) &
                    (Role.status == StatusEnum.VALID.value)
                ))
            
            role_ids = [role.id for role in roles]
            
            if not role_ids:
                return False
            
            # Check if any role has the required permission
            has_permission = RolePermission.select().where(
                (RolePermission.role_id.in_(role_ids)) & 
                (RolePermission.resource_id == resource_id) & 
                (RolePermission.permission_type == required_permission) & 
                (RolePermission.status == StatusEnum.VALID.value)
            ).exists()
            
            return has_permission
        except Exception:
            return False

    @classmethod
    @DB.connection_context()
    def get_tenant_roles(cls, tenant_id: str) -> List[Dict[str, Any]]:
        """获取特定租户创建的角色列表

        Args:
            tenant_id: 租户ID

        Returns:
            角色信息列表
        """
        try:
            roles = (Role
                .select()
                .where(
                    (Role.tenant_id == tenant_id) &
                    (Role.status == StatusEnum.VALID.value)
                )
                .order_by(Role.create_time.desc())
                .dicts())
            return list(roles)
        except Exception as e:
            print(f"Error getting tenant roles: {e}")
            return [] 