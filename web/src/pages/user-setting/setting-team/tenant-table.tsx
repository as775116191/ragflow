import { useFetchUserInfo, useListTenant } from '@/hooks/user-setting-hooks';
import { ITenant } from '@/interfaces/database/user-setting';
import { getUserRoles } from '@/services/user-service';
import { formatDate } from '@/utils/date';
import type { TableProps } from 'antd';
import { Button, Space, Table, Tag, Tooltip } from 'antd';
import { useEffect, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { TenantRole } from '../constants';
import { IRole } from '../setting-role/types';
import { useHandleAgreeTenant, useHandleQuitUser } from './hooks';

const TenantTable = () => {
  const { t } = useTranslation();
  const { data, loading } = useListTenant();
  const { handleAgree } = useHandleAgreeTenant();
  const { data: user } = useFetchUserInfo();
  const { handleQuitTenantUser } = useHandleQuitUser();
  const [userRoles, setUserRoles] = useState<Record<string, IRole[]>>({});

  // 角色标签颜色映射
  const roleColorMap = {
    [TenantRole.Owner]: 'red',
    [TenantRole.Normal]: 'green',
    [TenantRole.Admin]: 'orange',
  };

  // 获取用户在每个租户中的角色
  useEffect(() => {
    const fetchUserRolesForTenants = async () => {
      if (!data || data.length === 0) return;

      const rolesMap: Record<string, IRole[]> = {};

      for (const tenant of data) {
        try {
          // 获取当前用户在特定租户中的角色
          const response = await getUserRoles();
          const userAllRoles = response.data?.data?.roles || [];

          // 过滤出属于该租户的角色中，当前用户拥有的角色
          // 角色表新增了tenant_id字段用于标识角色所属的工作空间
          rolesMap[tenant.tenant_id] = userAllRoles.filter(
            (role: IRole) => role.tenant_id === tenant.tenant_id,
          );
        } catch (error) {
          console.error(`获取租户 ${tenant.tenant_id} 的角色失败:`, error);
          rolesMap[tenant.tenant_id] = [];
        }
      }

      setUserRoles(rolesMap);
    };

    fetchUserRolesForTenants();
  }, [data, user.id]);

  const columns: TableProps<ITenant>['columns'] = [
    {
      title: t('common.name'),
      dataIndex: 'nickname',
      key: 'nickname',
    },
    {
      title: t('setting.email'),
      dataIndex: 'email',
      key: 'email',
    },
    {
      title: t('setting.teamStatus'),
      dataIndex: 'role',
      key: 'role',
      render: (role) => (
        <Tag color={roleColorMap[role as keyof typeof roleColorMap]}>
          {t(`setting.${role}`)}
        </Tag>
      ),
    },
    {
      title: t('setting.userRoles'),
      key: 'userRoles',
      render: (_, record) => {
        const tenantRoles = userRoles[record.tenant_id] || [];
        return (
          <div>
            {tenantRoles.length > 0 ? (
              tenantRoles.map((role) => (
                <Tooltip key={role.id} title={role.description || ''}>
                  <Tag color="blue" style={{ margin: '2px' }}>
                    {role.name}
                  </Tag>
                </Tooltip>
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
      render(value) {
        return formatDate(value);
      },
    },
    {
      title: t('common.action'),
      key: 'action',
      render: (_, { role, tenant_id }) => {
        if (role === TenantRole.Admin) {
          return (
            <Space>
              <Button type="link" onClick={handleAgree(tenant_id, true)}>
                {t(`setting.agree`)}
              </Button>
              <Button type="link" onClick={handleAgree(tenant_id, false)}>
                {t(`setting.refuse`)}
              </Button>
            </Space>
          );
        } else if (role === TenantRole.Normal && user.id !== tenant_id) {
          return (
            <Button
              type="link"
              onClick={handleQuitTenantUser(user.id, tenant_id)}
            >
              {t('setting.quit')}
            </Button>
          );
        }
      },
    },
  ];

  return (
    <Table<ITenant>
      columns={columns}
      dataSource={data}
      rowKey={'tenant_id'}
      loading={loading}
      pagination={false}
    />
  );
};

export default TenantTable;
