import { useTranslate } from '@/hooks/common-hooks';
import request from '@/utils/request';
import { SyncOutlined } from '@ant-design/icons';
import { Button, Form, Input, Switch, Tooltip, message } from 'antd';
import { useEffect, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { DatasetConfigurationContainer } from './dataset-configuration-container';

export function OutlookMailSync() {
  const { t } = useTranslate('knowledgeConfiguration');
  const [searchParams] = useSearchParams();
  const kbId = searchParams.get('id');
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
    if (!kbId) {
      console.log('checkSyncStatus: kbId is missing, skipping');
      return;
    }

    try {
      const res = await request(`/v1/api/kb/sync_status?kb_id=${kbId}`);
      if (res.data?.is_syncing) {
        setSyncing(true);
        setSyncType(res.data.sync_type);
      } else {
        setSyncing(false);
        setSyncType(null);
      }
    } catch (error) {
      console.error('Failed to check sync status:', error);
      // 如果是404错误，说明同步功能可能没有启用，静默处理
      if ((error as any)?.response?.status === 404) {
        setSyncing(false);
        setSyncType(null);
      }
    }
  };

  // 触发同步
  const triggerSync = async (email?: string, folder_name?: string) => {
    if (!kbId) {
      console.error('kbId is missing');
      return;
    }

    try {
      const res = await request('/v1/api/kb/trigger_sync', {
        method: 'POST',
        data: {
          kb_id: kbId,
          sync_type: 'outlook',
          email: email,
          folder_name: folder_name,
        },
      });

      if (res.data) {
        message.success(t('syncStarted'));
        setSyncing(true);
        setSyncType('outlook');
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
      const res = await request('/v1/api/kb/cancel_sync', {
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
            prevValues?.parser_config?.outlook_sync_enabled !==
            currentValues?.parser_config?.outlook_sync_enabled
          );
        }}
        noStyle
      >
        {({ getFieldValue, setFieldsValue }) => {
          // 直接从表单中获取当前值
          const syncEnabled = getFieldValue([
            'parser_config',
            'outlook_sync_enabled',
          ]);

          // console.log('syncEnabled:', syncEnabled, 'syncing:', syncing, 'syncType:', syncType);

          // 处理开关状态变化
          const handleSyncChange = (checked: boolean) => {
            if (!checked && syncing && syncType === 'outlook') {
              // 如果正在同步且用户尝试关闭开关，弹出确认
              if (window.confirm(t('confirmCancelSync'))) {
                cancelSync();
              } else {
                // 用户取消操作，恢复开关状态
                setFieldsValue({
                  parser_config: {
                    ...getFieldValue('parser_config'),
                    outlook_sync_enabled: true,
                  },
                });
                return;
              }
            }
            // 移除了自动同步逻辑，现在只通过立即同步按钮触发
          };

          return (
            <>
              <Form.Item
                label={
                  <span>
                    {t('outlookSync')}
                    {syncing && syncType === 'outlook' && (
                      <Tooltip title={t('syncInProgress')}>
                        <SyncOutlined
                          spin
                          style={{ marginLeft: 8, color: '#1890ff' }}
                        />
                      </Tooltip>
                    )}
                  </span>
                }
                tooltip={t('outlookSyncTip')}
                name={['parser_config', 'outlook_sync_enabled']}
                valuePropName="checked"
              >
                <Switch onChange={handleSyncChange} />
              </Form.Item>

              {syncEnabled && (
                <>
                  <Form.Item
                    label={t('outlookEmail')}
                    tooltip={t('outlookEmailTip')}
                    name={['parser_config', 'outlook_email']}
                    rules={[
                      {
                        type: 'email',
                        message: t('outlookEmailFormatError'),
                      },
                      {
                        required: syncEnabled,
                        message: t('outlookEmailRequired'),
                      },
                    ]}
                  >
                    <Input placeholder={t('outlookEmailPlaceholder')} />
                  </Form.Item>

                  <Form.Item
                    label={t('outlookFolder')}
                    tooltip={t('outlookFolderTip')}
                    name={['parser_config', 'outlook_folder']}
                    rules={[
                      {
                        required: syncEnabled,
                        message: t('outlookFolderRequired'),
                      },
                    ]}
                  >
                    <Input placeholder={t('outlookFolderPlaceholder')} />
                  </Form.Item>

                  {syncing && syncType === 'outlook' ? (
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
                        onClick={() => {
                          // 获取表单中的邮箱和文件夹值
                          const email = getFieldValue([
                            'parser_config',
                            'outlook_email',
                          ]);
                          const folder_name = getFieldValue([
                            'parser_config',
                            'outlook_folder',
                          ]);
                          triggerSync(email, folder_name);
                        }}
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
