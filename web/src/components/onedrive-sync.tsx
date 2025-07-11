import { useTranslate } from '@/hooks/common-hooks';
import request from '@/utils/request';
import { SyncOutlined } from '@ant-design/icons';
import { Button, Form, Input, Switch, Tooltip, message } from 'antd';
import { useEffect, useState } from 'react';
import { useParams } from 'react-router-dom';
import { DatasetConfigurationContainer } from './dataset-configuration-container';

export function OneDriveSync() {
  const { t } = useTranslate('knowledgeConfiguration');
  const { id: kbId } = useParams<{ id: string }>();
  const [syncing, setSyncing] = useState(false);
  const [syncType, setSyncType] = useState<string | null>(null);

  // 定期检查同步状态
  useEffect(() => {
    if (!kbId) return;

    // 初始检查
    checkSyncStatus();

    // 每5秒检查一次
    const intervalId = setInterval(checkSyncStatus, 5000);

    return () => clearInterval(intervalId);
  }, [kbId]);

  // 检查同步状态
  const checkSyncStatus = async () => {
    if (!kbId) return;

    try {
      const res = await request(`/api/kb/sync_status?kb_id=${kbId}`);
      if (res.data?.is_syncing) {
        setSyncing(true);
        setSyncType(res.data.sync_type);
      } else {
        setSyncing(false);
        setSyncType(null);
      }
    } catch (error) {
      console.error('Failed to check sync status:', error);
    }
  };

  // 触发同步
  const triggerSync = async () => {
    if (!kbId) return;

    try {
      const res = await request('/api/kb/trigger_sync', {
        method: 'POST',
        data: {
          kb_id: kbId,
          sync_type: 'onedrive',
        },
      });

      if (res.data) {
        message.success(t('syncStarted'));
        setSyncing(true);
        setSyncType('onedrive');
      } else {
        message.error(res.message || t('syncFailed'));
      }
    } catch (error) {
      console.error('Failed to trigger sync:', error);
      message.error(t('syncFailed'));
    }
  };

  // 取消同步
  const cancelSync = async () => {
    if (!kbId) return;

    try {
      const res = await request('/api/kb/cancel_sync', {
        method: 'POST',
        data: {
          kb_id: kbId,
        },
      });

      if (res.data) {
        message.success(t('syncCancelled'));
      } else {
        message.error(res.message || t('cancelFailed'));
      }
    } catch (error) {
      console.error('Failed to cancel sync:', error);
      message.error(t('cancelFailed'));
    }
  };

  return (
    <DatasetConfigurationContainer>
      <Form.Item
        shouldUpdate={(prevValues, currentValues) => {
          return (
            prevValues?.parser_config?.onedrive_sync_enabled !==
            currentValues?.parser_config?.onedrive_sync_enabled
          );
        }}
        noStyle
      >
        {({ getFieldValue, setFieldsValue }) => {
          // 直接从表单中获取当前值
          const syncEnabled = getFieldValue([
            'parser_config',
            'onedrive_sync_enabled',
          ]);

          // 处理开关状态变化
          const handleSyncChange = (checked: boolean) => {
            if (!checked && syncing && syncType === 'onedrive') {
              // 如果正在同步且用户尝试关闭开关，弹出确认
              if (window.confirm(t('confirmCancelSync'))) {
                cancelSync();
              } else {
                // 用户取消操作，恢复开关状态
                setFieldsValue({
                  parser_config: {
                    ...getFieldValue('parser_config'),
                    onedrive_sync_enabled: true,
                  },
                });
                return;
              }
            }

            // 如果是从关闭到开启，且已配置邮箱，触发同步
            if (checked && !syncEnabled) {
              const email = getFieldValue(['parser_config', 'onedrive_email']);
              if (email) {
                // 延迟触发同步，等表单保存后
                setTimeout(() => triggerSync(), 1000);
              }
            }
          };

          return (
            <>
              <Form.Item
                label={
                  <span>
                    {t('onedriveSync')}
                    {syncing && syncType === 'onedrive' && (
                      <Tooltip title={t('syncInProgress')}>
                        <SyncOutlined
                          spin
                          style={{ marginLeft: 8, color: '#1890ff' }}
                        />
                      </Tooltip>
                    )}
                  </span>
                }
                tooltip={t('onedriveSyncTip')}
                name={['parser_config', 'onedrive_sync_enabled']}
                valuePropName="checked"
              >
                <Switch onChange={handleSyncChange} />
              </Form.Item>

              {syncEnabled && (
                <>
                  <Form.Item
                    label={t('onedriveEmail')}
                    tooltip={t('onedriveEmailTip')}
                    name={['parser_config', 'onedrive_email']}
                    rules={[
                      {
                        type: 'email',
                        message: t('onedriveEmailFormatError'),
                      },
                      {
                        required: syncEnabled,
                        message: t('onedriveEmailRequired'),
                      },
                    ]}
                  >
                    <Input placeholder={t('onedriveEmailPlaceholder')} />
                  </Form.Item>

                  {syncing && syncType === 'onedrive' ? (
                    <Form.Item>
                      <Button
                        type="default"
                        danger
                        onClick={cancelSync}
                        icon={<SyncOutlined spin />}
                      >
                        {t('cancelSync')}
                      </Button>
                    </Form.Item>
                  ) : (
                    <Form.Item>
                      <Button
                        type="primary"
                        onClick={triggerSync}
                        icon={<SyncOutlined />}
                      >
                        {t('syncNow')}
                      </Button>
                    </Form.Item>
                  )}
                </>
              )}
            </>
          );
        }}
      </Form.Item>
    </DatasetConfigurationContainer>
  );
}
