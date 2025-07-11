import { useTranslate } from '@/hooks/common-hooks';
import { useFetchTenantInfo } from '@/hooks/user-setting-hooks';
import { message } from 'antd';
import { useCallback, useEffect, useState } from 'react';
import {
  addUserToRole,
  createRole,
  deleteRole,
  fetchRoleDetail,
  fetchRoles,
  removeUserFromRole,
  updateRole,
  updateRolePermissions,
} from './service';
import { IRole } from './types';

export const useRoleList = () => {
  const [loading, setLoading] = useState(false);
  const [roles, setRoles] = useState<IRole[]>([]);
  const { t } = useTranslate('setting');
  const { data: tenantInfo } = useFetchTenantInfo();

  const fetchRoleList = useCallback(async () => {
    try {
      setLoading(true);
      // 使用当前用户的tenant_id获取特定工作空间的角色
      const result = await fetchRoles(tenantInfo.tenant_id);
      console.log('处理后的角色列表结果:', result);

      // 设置角色列表
      if (result && result.data) {
        // API返回的格式可能是 {code: 0, data: {roles: Array(2)}, message: 'success'}
        // 或者是 {code: 0, data: Array(2), message: 'success'}
        if (Array.isArray(result.data)) {
          console.log('设置角色列表(数组格式):', result.data);
          setRoles(result.data);
        } else {
          // 尝试处理嵌套的结构
          const dataObj = result.data as any;
          if (dataObj.roles && Array.isArray(dataObj.roles)) {
            console.log('设置角色列表(嵌套格式):', dataObj.roles);
            setRoles(dataObj.roles as IRole[]);
          } else {
            console.warn('角色列表数据结构不符合预期:', result.data);
            setRoles([]);
          }
        }
      } else {
        console.warn('角色列表返回数据不包含data字段:', result);
        setRoles([]);
      }
    } catch (error) {
      console.error('获取角色列表失败:', error);
      setRoles([]);
    } finally {
      setLoading(false);
    }
  }, [tenantInfo.tenant_id]);

  useEffect(() => {
    if (tenantInfo.tenant_id) {
      fetchRoleList();
    }
  }, [fetchRoleList, tenantInfo.tenant_id]);

  const handleCreateRole = useCallback(
    async (role: Partial<IRole>) => {
      try {
        setLoading(true);
        console.log('创建角色请求数据:', role);
        const response = await createRole(role);
        console.log('创建角色响应数据:', response);
        message.success(t('message.created'));
        await fetchRoleList();
        return true;
      } catch (error) {
        console.error('Failed to create role:', error);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchRoleList, t],
  );

  const handleUpdateRole = useCallback(
    async (roleId: string, role: Partial<IRole>) => {
      try {
        setLoading(true);
        await updateRole(roleId, role);
        message.success(t('message.updated'));
        await fetchRoleList();
        return true;
      } catch (error) {
        console.error('Failed to update role:', error);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchRoleList, t],
  );

  const handleDeleteRole = useCallback(
    async (roleId: string) => {
      try {
        setLoading(true);
        await deleteRole(roleId);
        message.success(t('message.deleted'));
        await fetchRoleList();
        return true;
      } catch (error) {
        console.error('Failed to delete role:', error);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [fetchRoleList, t],
  );

  return {
    loading,
    roles,
    fetchRoleList,
    handleCreateRole,
    handleUpdateRole,
    handleDeleteRole,
  };
};

export const useRoleDetail = (roleId?: string) => {
  const [loading, setLoading] = useState(false);
  const [role, setRole] = useState<IRole | null>(null);
  const { t } = useTranslate('setting');

  const fetchRoleInfo = useCallback(async () => {
    if (!roleId) return;

    try {
      setLoading(true);
      const response = await fetchRoleDetail(roleId);
      setRole(response.data || null);
    } catch (error) {
      console.error('Failed to fetch role detail:', error);
    } finally {
      setLoading(false);
    }
  }, [roleId]);

  useEffect(() => {
    if (roleId) {
      fetchRoleInfo();
    } else {
      setRole(null);
    }
  }, [roleId, fetchRoleInfo]);

  const handleAddUser = useCallback(
    async (userId: string) => {
      if (!roleId) return false;

      try {
        setLoading(true);
        await addUserToRole(roleId, userId);
        message.success(t('message.updated'));
        await fetchRoleInfo();
        return true;
      } catch (error) {
        console.error('Failed to add user to role:', error);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [roleId, fetchRoleInfo, t],
  );

  const handleRemoveUser = useCallback(
    async (userId: string) => {
      if (!roleId) return false;

      try {
        setLoading(true);
        await removeUserFromRole(roleId, userId);
        message.success(t('message.updated'));
        await fetchRoleInfo();
        return true;
      } catch (error) {
        console.error('Failed to remove user from role:', error);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [roleId, fetchRoleInfo, t],
  );

  const handleUpdatePermissions = useCallback(
    async (permissions: any[]) => {
      if (!roleId) return false;

      try {
        setLoading(true);
        await updateRolePermissions(roleId, permissions);
        message.success(t('message.updated'));
        await fetchRoleInfo();
        return true;
      } catch (error) {
        console.error('Failed to update role permissions:', error);
        return false;
      } finally {
        setLoading(false);
      }
    },
    [roleId, fetchRoleInfo, t],
  );

  return {
    loading,
    role,
    fetchRoleInfo,
    handleAddUser,
    handleRemoveUser,
    handleUpdatePermissions,
  };
};
