import {
  useAddUserRole,
  useGetUserRoles,
  useListTenantUser,
  useRemoveUserRole,
} from '@/hooks/user-setting-hooks';
import { ITenantUser } from '@/interfaces/database/user-setting';
import { getUserRoles } from '@/services/user-service';
import api from '@/utils/api';
import { formatDate } from '@/utils/date';
import { post } from '@/utils/request';
import { DeleteOutlined, TeamOutlined } from '@ant-design/icons';
import type { TableProps } from 'antd';
import { Button, Modal, Table, Tag, Tooltip, message } from 'antd';
import { upperFirst } from 'lodash';
import { useCallback, useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { TenantRole } from '../constants';
import { useRoleList } from '../setting-role/hooks';
import { IRole } from '../setting-role/types';
import { useHandleDeleteUser } from './hooks';

const ColorMap = {
  [TenantRole.Normal]: 'green',
  [TenantRole.Admin]: 'orange',
  [TenantRole.Owner]: 'red',
};

const UserTable = () => {
  const { data, loading } = useListTenantUser();
  const { roles } = useRoleList();
  const { handleDeleteTenantUser } = useHandleDeleteUser();
  const { t } = useTranslation();
  const [bindRoleModalVisible, setBindRoleModalVisible] = useState(false);
  const [currentUser, setCurrentUser] = useState<ITenantUser | null>(null);
  const [userRolesMap, setUserRolesMap] = useState<Record<string, IRole[]>>({});
  const { addUserRole: addUserRoleApi } = useAddUserRole();
  const { removeUserRole: removeUserRoleApi } = useRemoveUserRole();
  const [currentUserId, setCurrentUserId] = useState<string | undefined>(
    undefined,
  );
  const { data: currentUserRoles, refetch: refetchUserRoles } =
    useGetUserRoles(currentUserId);
  const [roleActionInProgress, setRoleActionInProgress] = useState(false);

  // 当currentUserId变化时，更新userRolesMap
  useEffect(() => {
    if (currentUserId && currentUserRoles) {
      setUserRolesMap((prev) => ({
        ...prev,
        [currentUserId]: currentUserRoles,
      }));
    }
  }, [currentUserId, currentUserRoles]);

  // 获取所有用户的角色
  useEffect(() => {
    if (data && data.length > 0) {
      const fetchUserRoles = async () => {
        const rolesMap: Record<string, IRole[]> = {};

        for (const user of data) {
          try {
            const response = await getUserRoles(user.user_id);
            rolesMap[user.user_id] = response.data?.data?.roles || [];
          } catch (error) {
            console.error(
              `Failed to fetch roles for user ${user.user_id}:`,
              error,
            );
            rolesMap[user.user_id] = [];
          }
        }

        setUserRolesMap(rolesMap);
      };

      fetchUserRoles();
    }
  }, [data]);

  const showBindRoleModal = useCallback((record: ITenantUser) => {
    setCurrentUser(record);
    setBindRoleModalVisible(true);

    // 设置当前用户ID，触发useGetUserRoles重新获取
    if (record && record.user_id) {
      setCurrentUserId(record.user_id);
    }
  }, []);

  const handleBindRoleCancel = useCallback(() => {
    setBindRoleModalVisible(false);
    setCurrentUser(null);
    setCurrentUserId(undefined);
  }, []);

  const handleAddRole = useCallback(
    async (userId: string, role: IRole) => {
      if (!userId || !role.id) {
        message.error(t('setting.missingRequiredParams'));
        return;
      }

      setRoleActionInProgress(true);
      try {
        // 直接使用post函数发送请求，确保请求体中包含user_id
        console.log(
          `添加角色: 发送到 ${api.addUserRole(role.id)}，用户ID: ${userId}`,
        );
        const response = await post(api.addUserRole(role.id), {
          user_id: userId,
        });
        const result = response.data;

        // 只有API调用成功后才更新UI
        if (result.code === 0) {
          // 重新获取用户的角色列表
          const response = await getUserRoles(userId);
          const updatedRoles = response.data?.data?.roles || [];

          // 更新本地状态
          setUserRolesMap((prev) => ({
            ...prev,
            [userId]: updatedRoles,
          }));

          message.success(t('setting.roleAddedSuccess'));
        } else {
          message.error(`${t('setting.roleAddFailed')}: ${result.message}`);
        }
      } catch (error) {
        console.error('Failed to add role:', error);
        message.error(t('setting.roleAddFailed'));
      } finally {
        setRoleActionInProgress(false);
      }
    },
    [t],
  );

  const handleRemoveRole = useCallback(
    async (userId: string, roleId: string) => {
      if (!userId || !roleId) {
        message.error(t('setting.missingRequiredParams'));
        return;
      }

      setRoleActionInProgress(true);
      try {
        // 直接使用post函数发送请求，确保请求体中包含user_id
        console.log(
          `移除角色: 发送到 ${api.removeUserRole(roleId)}，用户ID: ${userId}`,
        );
        const response = await post(api.removeUserRole(roleId), {
          user_id: userId,
        });
        const result = response.data;

        // 只有API调用成功后才更新UI
        if (result.code === 0) {
          // 重新获取用户的角色列表
          const response = await getUserRoles(userId);
          const updatedRoles = response.data?.data?.roles || [];

          // 更新本地状态
          setUserRolesMap((prev) => ({
            ...prev,
            [userId]: updatedRoles,
          }));

          message.success(t('setting.roleRemovedSuccess'));
        } else {
          message.error(`${t('setting.roleRemoveFailed')}: ${result.message}`);
        }
      } catch (error) {
        console.error('Failed to remove role:', error);
        message.error(t('setting.roleRemoveFailed'));
      } finally {
        setRoleActionInProgress(false);
      }
    },
    [t],
  );

  const columns: TableProps<ITenantUser>['columns'] = [
    {
      title: t('common.name'),
      dataIndex: 'nickname',
      key: 'nickname',
      align: 'center',
    },
    {
      title: t('setting.email'),
      dataIndex: 'email',
      key: 'email',
      align: 'center',
    },
    {
      title: t('setting.status'),
      dataIndex: 'role',
      key: 'role',
      align: 'center',
      render(value, { role }) {
        return (
          <Tag color={ColorMap[role as keyof typeof ColorMap]}>
            {upperFirst(role)}
          </Tag>
        );
      },
    },
    {
      title: t('setting.role'),
      key: 'userRoles',
      align: 'center',
      render(_, record) {
        const userBindRoles = userRolesMap[record.user_id] || [];
        return (
          <div>
            {userBindRoles.length > 0 ? (
              userBindRoles.map((role) => (
                <Tag key={role.id} color="blue">
                  {role.name}
                </Tag>
              ))
            ) : (
              <span>-</span>
            )}
          </div>
        );
      },
    },
    {
      title: t('setting.updateDate'),
      dataIndex: 'update_date',
      key: 'update_date',
      align: 'center',
      render(value) {
        return formatDate(value);
      },
    },
    {
      title: t('common.action'),
      key: 'action',
      align: 'center',
      render: (_, record) => (
        <div>
          <Tooltip title={t('setting.bindRole')}>
            <Button
              type="text"
              onClick={() => showBindRoleModal(record)}
              style={{ marginRight: 8 }}
            >
              <TeamOutlined />
            </Button>
          </Tooltip>
          <Tooltip title={t('common.delete')}>
            <Button
              type="text"
              onClick={handleDeleteTenantUser(record.user_id)}
            >
              <DeleteOutlined />
            </Button>
          </Tooltip>
        </div>
      ),
    },
  ];

  return (
    <>
      <Table<ITenantUser>
        rowKey={'user_id'}
        columns={columns}
        dataSource={data}
        loading={loading}
        pagination={false}
      />

      <Modal
        title={t('setting.bindRole')}
        open={bindRoleModalVisible}
        onCancel={handleBindRoleCancel}
        footer={null}
      >
        {currentUser && (
          <div>
            <h3>{currentUser.nickname}</h3>
            <div style={{ marginTop: 16 }}>
              <h4>{t('setting.currentRoles')}</h4>
              {/* 这里显示已绑定角色和删除按钮 */}
              {(userRolesMap[currentUser.user_id] || []).map((role) => (
                <Tag
                  key={role.id}
                  color="blue"
                  closable
                  style={{ marginBottom: 8 }}
                  onClose={
                    roleActionInProgress
                      ? undefined
                      : () => handleRemoveRole(currentUser.user_id, role.id)
                  }
                >
                  {role.name}
                </Tag>
              ))}
              {(userRolesMap[currentUser.user_id] || []).length === 0 && (
                <div>{t('setting.noRoles')}</div>
              )}
            </div>
            <div style={{ marginTop: 16 }}>
              <h4>{t('setting.availableRoles')}</h4>
              {/* 这里显示可选角色列表 */}
              {roles
                .filter(
                  (role) =>
                    !(userRolesMap[currentUser.user_id] || []).some(
                      (ur) => ur.id === role.id,
                    ),
                )
                .map((role) => (
                  <Tag
                    key={role.id}
                    style={{
                      marginBottom: 8,
                      cursor: roleActionInProgress ? 'not-allowed' : 'pointer',
                      opacity: roleActionInProgress ? 0.5 : 1,
                    }}
                    onClick={
                      roleActionInProgress
                        ? undefined
                        : () => handleAddRole(currentUser.user_id, role)
                    }
                  >
                    + {role.name}
                  </Tag>
                ))}
              {roles.filter(
                (role) =>
                  !(userRolesMap[currentUser.user_id] || []).some(
                    (ur) => ur.id === role.id,
                  ),
              ).length === 0 && <div>{t('setting.allRolesAssigned')}</div>}
            </div>
          </div>
        )}
      </Modal>
    </>
  );
};

export default UserTable;
