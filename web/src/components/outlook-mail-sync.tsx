import { useTranslate } from '@/hooks/common-hooks';
import { Form, Input, Switch } from 'antd';
import { DatasetConfigurationContainer } from './dataset-configuration-container';

export function OutlookMailSync() {
  const { t } = useTranslate('knowledgeConfiguration');

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
        {({ getFieldValue }) => {
          // 直接从表单中获取当前值
          const syncEnabled = getFieldValue([
            'parser_config',
            'outlook_sync_enabled',
          ]);

          return (
            <>
              <Form.Item
                label={t('outlookSync')}
                tooltip={t('outlookSyncTip')}
                name={['parser_config', 'outlook_sync_enabled']}
                valuePropName="checked"
              >
                <Switch />
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
                </>
              )}
            </>
          );
        }}
      </Form.Item>
    </DatasetConfigurationContainer>
  );
}
