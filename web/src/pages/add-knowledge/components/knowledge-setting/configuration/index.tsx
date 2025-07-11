import { OneDriveSync } from '@/components/onedrive-sync';
import { OutlookMailSync } from '@/components/outlook-mail-sync';
import { DocumentParserType } from '@/constants/knowledge';
import { useTranslate } from '@/hooks/common-hooks';
import { useRoleList } from '@/pages/user-setting/setting-role/hooks';
import { normFile } from '@/utils/file-util';
import { PlusOutlined } from '@ant-design/icons';
import { Button, Form, Input, Radio, Select, Space, Upload } from 'antd';
import { FormInstance } from 'antd/lib';
import { useEffect, useMemo, useState } from 'react';
import {
  useFetchKnowledgeConfigurationOnMount,
  useSubmitKnowledgeConfiguration,
} from '../hooks';
import { AudioConfiguration } from './audio';
import { BookConfiguration } from './book';
import { EmailConfiguration } from './email';
import { KnowledgeGraphConfiguration } from './knowledge-graph';
import { LawsConfiguration } from './laws';
import { ManualConfiguration } from './manual';
import { NaiveConfiguration } from './naive';
import { OneConfiguration } from './one';
import { PaperConfiguration } from './paper';
import { PictureConfiguration } from './picture';
import { PresentationConfiguration } from './presentation';
import { QAConfiguration } from './qa';
import { ResumeConfiguration } from './resume';
import { TableConfiguration } from './table';
import { TagConfiguration } from './tag';

import styles from '../index.less';

const ConfigurationComponentMap = {
  [DocumentParserType.Naive]: NaiveConfiguration,
  [DocumentParserType.Qa]: QAConfiguration,
  [DocumentParserType.Resume]: ResumeConfiguration,
  [DocumentParserType.Manual]: ManualConfiguration,
  [DocumentParserType.Table]: TableConfiguration,
  [DocumentParserType.Paper]: PaperConfiguration,
  [DocumentParserType.Book]: BookConfiguration,
  [DocumentParserType.Laws]: LawsConfiguration,
  [DocumentParserType.Presentation]: PresentationConfiguration,
  [DocumentParserType.Picture]: PictureConfiguration,
  [DocumentParserType.One]: OneConfiguration,
  [DocumentParserType.Audio]: AudioConfiguration,
  [DocumentParserType.Email]: EmailConfiguration,
  [DocumentParserType.Tag]: TagConfiguration,
  [DocumentParserType.KnowledgeGraph]: KnowledgeGraphConfiguration,
};

function EmptyComponent() {
  return <div></div>;
}

export const ConfigurationForm = ({ form }: { form: FormInstance }) => {
  const { submitKnowledgeConfiguration, submitLoading, navigateToDataset } =
    useSubmitKnowledgeConfiguration(form);
  const { t } = useTranslate('knowledgeConfiguration');
  const { roles } = useRoleList();

  const [finalParserId, setFinalParserId] = useState<DocumentParserType>();
  const knowledgeDetails = useFetchKnowledgeConfigurationOnMount(form);
  const parserId: DocumentParserType = Form.useWatch('parser_id', form);
  const permission = Form.useWatch('permission', form);

  const ConfigurationComponent = useMemo(() => {
    return finalParserId
      ? ConfigurationComponentMap[finalParserId]
      : EmptyComponent;
  }, [finalParserId]);

  useEffect(() => {
    setFinalParserId(parserId);
  }, [parserId]);

  useEffect(() => {
    setFinalParserId(knowledgeDetails.parser_id as DocumentParserType);
  }, [knowledgeDetails.parser_id]);

  return (
    <Form form={form} name="validateOnly" layout="vertical" autoComplete="off">
      <Form.Item name="name" label={t('name')} rules={[{ required: true }]}>
        <Input />
      </Form.Item>
      <Form.Item
        name="avatar"
        label={t('photo')}
        valuePropName="fileList"
        getValueFromEvent={normFile}
      >
        <Upload
          listType="picture-card"
          maxCount={1}
          beforeUpload={() => false}
          showUploadList={{ showPreviewIcon: false, showRemoveIcon: false }}
        >
          <button style={{ border: 0, background: 'none' }} type="button">
            <PlusOutlined />
            <div style={{ marginTop: 8 }}>{t('upload')}</div>
          </button>
        </Upload>
      </Form.Item>
      <Form.Item name="description" label={t('description')}>
        <Input />
      </Form.Item>
      <Form.Item
        name="permission"
        label={t('permissions')}
        tooltip={t('permissionsTip')}
        rules={[{ required: true }]}
      >
        <Radio.Group>
          <Radio value="me">{t('me')}</Radio>
          <Radio value="team">{t('team')}</Radio>
          <Radio value="role">{t('role')}</Radio>
        </Radio.Group>
      </Form.Item>

      {permission === 'role' && (
        <Form.Item
          name="role_ids"
          label={t('selectRoles')}
          tooltip={t('selectRolesTooltip')}
          rules={[
            {
              required: permission === 'role',
              message: t('pleaseSelectRoles'),
            },
          ]}
        >
          <Select
            mode="multiple"
            placeholder={t('selectRolesPlaceholder')}
            style={{ width: '100%' }}
            options={roles.map((role) => ({
              label: role.name,
              value: role.id,
            }))}
          />
        </Form.Item>
      )}

      <ConfigurationComponent></ConfigurationComponent>

      <Form.Item>
        <OutlookMailSync />
      </Form.Item>

      <Form.Item>
        <OneDriveSync />
      </Form.Item>

      <Form.Item>
        <div className={styles.buttonWrapper}>
          <Space>
            <Button size={'middle'} onClick={navigateToDataset}>
              {t('cancel')}
            </Button>
            <Button
              type="primary"
              size={'middle'}
              loading={submitLoading}
              onClick={submitKnowledgeConfiguration}
            >
              {t('save')}
            </Button>
          </Space>
        </div>
      </Form.Item>
    </Form>
  );
};
