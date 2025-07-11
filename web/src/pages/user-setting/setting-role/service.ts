import { ResponseType } from '@/interfaces/database/base';
import request from '@/utils/request';
import { IRole } from './types';

// 获取所有角色
export const fetchRoles = async (
  tenantId?: string,
): Promise<ResponseType<IRole[]>> => {
  try {
    // 如果提供了tenantId，则使用该参数获取特定工作空间的角色
    const url = tenantId
      ? `/v1/role/list?tenant_id=${tenantId}`
      : '/v1/role/list';

    const response = await request.get(url);

    // 正确解析响应数据
    if (response && response.data) {
      // response.data 是API响应的完整对象
      const responseData = response.data as ResponseType<{ roles: IRole[] }>;
      return {
        code: responseData.code,
        message: responseData.message,
        data: responseData.data?.roles || [],
        status: responseData.status,
      };
    }

    return { code: 0, message: '成功', data: [], status: 200 };
  } catch (error) {
    return { code: 500, message: '获取角色列表失败', data: [], status: 500 };
  }
};

// 获取角色详情
export const fetchRoleDetail = async (roleId: string) => {
  return request.get<ResponseType<IRole>>(`/v1/role/detail/${roleId}`);
};

// 创建角色
export const createRole = async (data: Partial<IRole>) => {
  console.log('服务层创建角色请求数据:', data);
  return request.post('/v1/role/create', { data });
};

// 更新角色
export const updateRole = async (roleId: string, data: Partial<IRole>) => {
  return request.post(`/v1/role/update/${roleId}`, { data });
};

// 删除角色
export const deleteRole = async (roleId: string) => {
  return request.post(`/v1/role/delete/${roleId}`);
};

// 添加用户到角色
export const addUserToRole = async (roleId: string, userId: string) => {
  return request.post(`/v1/role/add_user/${roleId}`, {
    data: { user_id: userId },
  });
};

// 从角色中移除用户
export const removeUserFromRole = async (roleId: string, userId: string) => {
  return request.post(`/v1/role/remove_user/${roleId}`, {
    data: { user_id: userId },
  });
};

// 更新角色权限
export const updateRolePermissions = async (
  roleId: string,
  permissions: any[],
) => {
  return request.post(`/v1/role/update_permissions/${roleId}`, {
    data: { permissions },
  });
};
