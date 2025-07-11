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
import logging
from typing import Dict, List, Optional, Any

from flask import request
from flask_login import login_required, current_user

from api import settings
from api.db.services.role_service import RoleService
from api.db.services.user_service import UserService
from api.utils.api_utils import server_error_response, get_data_error_result, validate_request, not_allowed_parameters
from api.utils.api_utils import get_json_result


@manager.route('/create', methods=['POST'])  # noqa: F821
@login_required
@validate_request("name")
def create():
    """Create a new role.

    Returns:
        JSON response with the created role ID.
    """
    req = request.json
    name = req.get("name", "").strip()
    description = req.get("description", "")
    
    if not name:
        return get_data_error_result(message="Role name cannot be empty.")
    
    try:
        # 获取当前用户的tenant_id
        tenant_id = current_user.id
        
        role_id = RoleService.create_role(
            name=name,
            description=description,
            created_by=current_user.id,
            tenant_id=tenant_id
        )
        
        if not role_id:
            return get_data_error_result(message="Failed to create role.")
        
        return get_json_result(data={"role_id": role_id})
    except Exception as e:
        return server_error_response(e)


@manager.route('/list', methods=['GET'])  # noqa: F821
@login_required
def list_roles():
    """Get all roles.

    Returns:
        JSON response with roles.
    """
    try:
        # 获取请求中的tenant_id参数
        tenant_id = request.args.get("tenant_id")
        
        # 如果提供了tenant_id，则获取该租户的角色
        if tenant_id:
            # 检查当前用户是否有权限查看该租户的角色（只有租户的owner或admin可以查看）
            from api.db.services.user_service import UserTenantService
            from api.db import UserTenantRole
            
            user_tenant = UserTenantService.get_user_tenant(current_user.id, tenant_id)
            if not user_tenant or user_tenant.role not in [UserTenantRole.OWNER, UserTenantRole.ADMIN]:
                return get_data_error_result(message="No permission to view roles for this tenant.")
                
            # 获取该租户创建的角色
            roles = RoleService.get_tenant_roles(tenant_id)
        else:
            # 否则获取所有角色
            roles = RoleService.get_all_roles()
            
        return get_json_result(data={"roles": roles})
    except Exception as e:
        return server_error_response(e)


@manager.route('/detail/<role_id>', methods=['GET'])  # noqa: F821
@login_required
def get_role_detail(role_id):
    """Get role details.

    Args:
        role_id: ID of the role.

    Returns:
        JSON response with role details.
    """
    try:
        role = RoleService.get_role(role_id)
        if not role:
            return get_data_error_result(message="Role not found.")
        
        return get_json_result(data=role)
    except Exception as e:
        return server_error_response(e)


@manager.route('/update/<role_id>', methods=['POST'])  # noqa: F821
@login_required
@validate_request("name")
@not_allowed_parameters("id", "created_by", "create_time", "update_time", "create_date", "update_date", "status")
def update_role(role_id):
    """Update a role.

    Args:
        role_id: ID of the role to update.

    Returns:
        JSON response with result.
    """
    req = request.json
    name = req.get("name", "").strip()
    description = req.get("description")
    
    if not name:
        return get_data_error_result(message="Role name cannot be empty.")
    
    try:
        success = RoleService.update_role(
            role_id=role_id,
            name=name,
            description=description
        )
        
        if not success:
            return get_data_error_result(message="Failed to update role.")
        
        # Get updated role
        role = RoleService.get_role(role_id)
        
        return get_json_result(data=role)
    except Exception as e:
        return server_error_response(e)


@manager.route('/delete/<role_id>', methods=['POST'])  # noqa: F821
@login_required
def delete_role(role_id):
    """Delete a role.

    Args:
        role_id: ID of the role to delete.

    Returns:
        JSON response with result.
    """
    try:
        success = RoleService.delete_role(role_id)
        
        if not success:
            return get_data_error_result(message="Failed to delete role.")
        
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/add_user/<role_id>', methods=['POST'])  # noqa: F821
@login_required
@validate_request("user_id")
def add_user_to_role(role_id):
    """Add a user to a role.

    Args:
        role_id: ID of the role.

    Returns:
        JSON response with result.
    """
    req = request.json
    user_id = req.get("user_id")
    
    # Verify user exists
    user = UserService.filter_by_id(user_id)
    if not user:
        return get_data_error_result(message="User not found.")
    
    try:
        success = RoleService.add_user_to_role(role_id, user_id)
        
        if not success:
            return get_data_error_result(message="Failed to add user to role.")
        
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/remove_user/<role_id>', methods=['POST'])  # noqa: F821
@login_required
@validate_request("user_id")
def remove_user_from_role(role_id):
    """Remove a user from a role.

    Args:
        role_id: ID of the role.

    Returns:
        JSON response with result.
    """
    req = request.json
    user_id = req.get("user_id")
    
    try:
        success = RoleService.remove_user_from_role(role_id, user_id)
        
        if not success:
            return get_data_error_result(message="Failed to remove user from role.")
        
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/add_permission/<role_id>', methods=['POST'])  # noqa: F821
@login_required
@validate_request("resource_id", "resource_name", "permission_type")
def add_permission_to_role(role_id):
    """Add a permission to a role.

    Args:
        role_id: ID of the role.

    Returns:
        JSON response with result.
    """
    req = request.json
    resource_type = req.get("resource_type", "knowledgebase")
    resource_id = req.get("resource_id")
    resource_name = req.get("resource_name")
    permission_type = req.get("permission_type")
    
    try:
        success = RoleService.add_permission_to_role(
            role_id=role_id,
            resource_type=resource_type,
            resource_id=resource_id,
            resource_name=resource_name,
            permission_type=permission_type
        )
        
        if not success:
            return get_data_error_result(message="Failed to add permission to role.")
        
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/remove_permission/<permission_id>', methods=['POST'])  # noqa: F821
@login_required
def remove_permission_from_role(permission_id):
    """Remove a permission from a role.

    Args:
        permission_id: ID of the permission.

    Returns:
        JSON response with result.
    """
    try:
        success = RoleService.remove_permission_from_role(permission_id)
        
        if not success:
            return get_data_error_result(message="Failed to remove permission.")
        
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/update_permissions/<role_id>', methods=['POST'])  # noqa: F821
@login_required
@validate_request("permissions")
def update_role_permissions(role_id):
    """Update a role's permissions.

    Args:
        role_id: ID of the role.

    Returns:
        JSON response with result.
    """
    req = request.json
    permissions = req.get("permissions", [])
    
    try:
        success = RoleService.update_role_permissions(role_id, permissions)
        
        if not success:
            return get_data_error_result(message="Failed to update role permissions.")
        
        return get_json_result(data=True)
    except Exception as e:
        return server_error_response(e)


@manager.route('/user_roles', methods=['GET'])  # noqa: F821
@login_required
def get_user_roles():
    """Get roles for a user.

    Returns:
        JSON response with roles.
    """
    user_id = request.args.get("user_id")
    
    if not user_id:
        user_id = current_user.id
    
    try:
        roles = RoleService.get_user_roles(user_id)
        return get_json_result(data={"roles": roles})
    except Exception as e:
        return server_error_response(e)


@manager.route('/check_permission', methods=['GET'])  # noqa: F821
@login_required
def check_user_permission():
    """Check if a user has a specific permission for a resource.

    Returns:
        JSON response with result.
    """
    resource_id = request.args.get("resource_id")
    permission_type = request.args.get("permission_type")
    user_id = request.args.get("user_id")
    
    if not resource_id or not permission_type:
        return get_data_error_result(message="Missing required parameters.")
    
    if not user_id:
        user_id = current_user.id
    
    try:
        has_permission = RoleService.check_user_permission(
            user_id=user_id,
            resource_id=resource_id,
            required_permission=permission_type
        )
        
        return get_json_result(data={"has_permission": has_permission})
    except Exception as e:
        return server_error_response(e) 