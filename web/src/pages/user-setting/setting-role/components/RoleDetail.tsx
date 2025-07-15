import { useTranslate } from '@/hooks/common-hooks';
import { ArrowLeftOutlined } from '@ant-design/icons';
import { Button, Card, Spin, Typography } from 'antd';
import React from 'react';
import { useRoleDetail } from '../hooks';

const { Title, Text } = Typography;

interface RoleDetailProps {
  roleId: string;
  onBack: () => void;
}

const RoleDetail: React.FC<RoleDetailProps> = ({ roleId, onBack }) => {
  const { t } = useTranslate('setting');
  const { loading, role } = useRoleDetail(roleId);

  return (
    <Card bordered={false}>
      <div style={{ marginBottom: 16 }}>
        <Button
          type="text"
          icon={<ArrowLeftOutlined />}
          onClick={onBack}
          style={{ marginBottom: 16 }}
        >
          {t('back')}
        </Button>
        <Title level={4}>{role?.name || t('roleDetail')}</Title>
      </div>

      <Spin spinning={loading}>
        {role && (
          <div>
            <div style={{ marginBottom: 16 }}>
              <Text strong>{t('name')}: </Text>
              <Text>{role.name}</Text>
            </div>
            <div style={{ marginBottom: 16 }}>
              <Text strong>{t('description')}: </Text>
              <Text>{role.description || '-'}</Text>
            </div>
            <div style={{ marginBottom: 16 }}>
              <Text strong>{t('createdTime')}: </Text>
              <Text>{new Date(role.created_time).toLocaleString()}</Text>
            </div>
            <div style={{ marginBottom: 16 }}>
              <Text strong>{t('updatedTime')}: </Text>
              <Text>{new Date(role.updated_time).toLocaleString()}</Text>
            </div>
          </div>
        )}
      </Spin>
    </Card>
  );
};

export default RoleDetail;
