import { useTranslate } from '@/hooks/common-hooks';
import { PlusOutlined } from '@ant-design/icons';
import {
  Button,
  Card,
  Divider,
  Empty,
  Form,
  Input,
  List,
  Modal,
  Popconfirm,
  Spin,
  Typography,
} from 'antd';
import React, { useState } from 'react';
import RoleDetail from './components/RoleDetail';
import { useRoleList } from './hooks';
import styles from './index.less';
import { IRole } from './types';

const { Title, Text } = Typography;

const UserSettingRole: React.FC = () => {
  const { t } = useTranslate('setting');
  const { loading, roles, handleCreateRole, handleDeleteRole } = useRoleList();
  const [isModalVisible, setIsModalVisible] = useState(false);
  const [form] = Form.useForm();
  const [selectedRoleId, setSelectedRoleId] = useState<string | null>(null);

  const handleCreateClick = () => {
    form.resetFields();
    setIsModalVisible(true);
  };

  const handleModalOk = async () => {
    try {
      const values = await form.validateFields();
      const success = await handleCreateRole(values);
      if (success) {
        setIsModalVisible(false);
      }
    } catch (error) {
      console.error('Form validation failed:', error);
    }
  };

  const handleModalCancel = () => {
    setIsModalVisible(false);
  };

  const handleRoleClick = (roleId: string) => {
    setSelectedRoleId(roleId);
  };

  const handleBackToList = () => {
    setSelectedRoleId(null);
  };

  // 如果选择了角色，显示角色详情
  if (selectedRoleId) {
    return <RoleDetail roleId={selectedRoleId} onBack={handleBackToList} />;
  }

  return (
    <div className={styles.roleWrapper}>
      <Card bordered={false}>
        <div
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            marginBottom: 16,
          }}
        >
          <Title level={4}>{t('role')}</Title>
          <Button
            type="primary"
            icon={<PlusOutlined />}
            onClick={handleCreateClick}
          >
            {t('add')}
          </Button>
        </div>
        <Text type="secondary" style={{ display: 'block', marginBottom: 24 }}>
          {t('roleDescription')}
        </Text>
        <Divider />

        <Spin spinning={loading}>
          {roles && roles.length > 0 ? (
            <List
              dataSource={roles}
              renderItem={(role: IRole) => (
                <List.Item
                  key={role.id}
                  actions={[
                    <Popconfirm
                      key="delete"
                      title={t('sureDelete')}
                      onConfirm={() => handleDeleteRole(role.id)}
                      okText={t('agree')}
                      cancelText={t('cancel')}
                    >
                      <Button type="link" danger>
                        {t('delete')}
                      </Button>
                    </Popconfirm>,
                  ]}
                >
                  <List.Item.Meta
                    title={
                      <a onClick={() => handleRoleClick(role.id)}>
                        {role.name}
                      </a>
                    }
                    description={role.description || '-'}
                  />
                </List.Item>
              )}
            />
          ) : (
            <Empty
              description={<span>{t('noData')}</span>}
              image={Empty.PRESENTED_IMAGE_SIMPLE}
            />
          )}
        </Spin>
      </Card>

      <Modal
        title={t('add')}
        open={isModalVisible}
        onOk={handleModalOk}
        onCancel={handleModalCancel}
        destroyOnClose
      >
        <Form form={form} layout="vertical">
          <Form.Item
            name="name"
            label={t('name')}
            rules={[{ required: true, message: t('nameRequired') }]}
          >
            <Input placeholder={t('namePlaceholder')} />
          </Form.Item>
          <Form.Item name="description" label={t('description')}>
            <Input.TextArea
              rows={4}
              placeholder={t('descriptionPlaceholder')}
            />
          </Form.Item>
        </Form>
      </Modal>
    </div>
  );
};

export default UserSettingRole;
