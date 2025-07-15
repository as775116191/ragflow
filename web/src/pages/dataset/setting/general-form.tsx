import { FormContainer } from '@/components/form-container';
import { Avatar, AvatarFallback, AvatarImage } from '@/components/ui/avatar';
import { Button } from '@/components/ui/button';
import {
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { RadioGroup, RadioGroupItem } from '@/components/ui/radio-group';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { useUpdateKnowledge } from '@/hooks/knowledge-hooks';
import { fetchRoles } from '@/pages/user-setting/setting-role/service';
import { IRole } from '@/pages/user-setting/setting-role/types';
import { transformFile2Base64 } from '@/utils/file-util';
import { Loader2Icon, Pencil, Upload } from 'lucide-react';
import { useEffect, useMemo, useState } from 'react';
import { useFormContext } from 'react-hook-form';
import { useTranslation } from 'react-i18next';
import { useParams } from 'umi';

export function GeneralForm() {
  const form = useFormContext();
  const { t } = useTranslation();
  const [roles, setRoles] = useState<IRole[]>([]);
  const [loading, setLoading] = useState(false);

  // 获取角色列表
  useEffect(() => {
    const getRoles = async () => {
      try {
        setLoading(true);
        const response = await fetchRoles();
        setRoles(response.data || []);
      } catch (error) {
        console.error('Failed to fetch roles:', error);
      } finally {
        setLoading(false);
      }
    };

    getRoles();
  }, []);
  const [avatarFile, setAvatarFile] = useState<File | null>(null);
  const [avatarBase64Str, setAvatarBase64Str] = useState(''); // Avatar Image base64

  const { saveKnowledgeConfiguration, loading: submitLoading } =
    useUpdateKnowledge();

  const defaultValues = useMemo(
    () => form.formState.defaultValues ?? {},
    [form.formState.defaultValues],
  );
  const parser_id = defaultValues['parser_id'];
  const { id: kb_id } = useParams();

  // init avatar file if it exists in defaultValues
  useEffect(() => {
    if (!avatarFile) {
      let avatarList = defaultValues['avatar'];
      if (avatarList && avatarList.length > 0) {
        setAvatarBase64Str(avatarList[0].thumbUrl);
      }
    }
  }, [avatarFile, defaultValues]);

  // input[type=file] on change event, get img base64
  useEffect(() => {
    if (avatarFile) {
      (async () => {
        // make use of img compression transformFile2Base64
        setAvatarBase64Str(await transformFile2Base64(avatarFile));
      })();
    }
  }, [avatarFile]);

  return (
    <>
      <FormContainer className="space-y-10 p-10">
        <FormField
          control={form.control}
          name="name"
          render={({ field }) => (
            <FormItem className="items-center space-y-0">
              <div className="flex">
                <FormLabel className="text-sm text-muted-foreground whitespace-nowrap w-1/4">
                  <span className="text-red-600">*</span>
                  {t('common.name')}
                </FormLabel>
                <FormControl className="w-3/4">
                  <Input {...field}></Input>
                </FormControl>
              </div>
              <div className="flex pt-1">
                <div className="w-1/4"></div>
                <FormMessage />
              </div>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="avatar"
          render={() => (
            <FormItem className="items-center space-y-0">
              <div className="flex">
                <FormLabel className="text-sm text-muted-foreground whitespace-nowrap w-1/4">
                  {t('setting.avatar')}
                </FormLabel>
                <FormControl className="w-3/4">
                  <div className="flex justify-start items-end space-x-2">
                    <div className="relative group">
                      {!avatarBase64Str ? (
                        <div className="w-[64px] h-[64px] grid place-content-center border border-dashed	rounded-md">
                          <div className="flex flex-col items-center">
                            <Upload />
                            <p>{t('common.upload')}</p>
                          </div>
                        </div>
                      ) : (
                        <div className="w-[64px] h-[64px] relative grid place-content-center">
                          <Avatar className="w-[64px] h-[64px] rounded-md">
                            <AvatarImage
                              className=" block"
                              src={avatarBase64Str}
                              alt=""
                            />
                            <AvatarFallback></AvatarFallback>
                          </Avatar>
                          <div className="absolute inset-0 bg-[#000]/20 group-hover:bg-[#000]/60">
                            <Pencil
                              size={20}
                              className="absolute right-2 bottom-0 opacity-50 hidden group-hover:block"
                            />
                          </div>
                        </div>
                      )}
                      <Input
                        placeholder=""
                        // {...field}
                        type="file"
                        title=""
                        accept="image/*"
                        className="absolute top-0 left-0 w-full h-full opacity-0 cursor-pointer"
                        onChange={(ev) => {
                          const file = ev.target?.files?.[0];
                          if (
                            /\.(jpg|jpeg|png|webp|bmp)$/i.test(file?.name ?? '')
                          ) {
                            setAvatarFile(file!);
                          }
                          ev.target.value = '';
                        }}
                      />
                    </div>
                    <div className="margin-1 text-muted-foreground">
                      {t('knowledgeConfiguration.photoTip')}
                    </div>
                  </div>
                </FormControl>
              </div>
              <div className="flex pt-1">
                <div className="w-1/4"></div>
                <FormMessage />
              </div>
            </FormItem>
          )}
        />
        <FormField
          control={form.control}
          name="description"
          render={({ field }) => {
            // null initialize empty string
            if (typeof field.value === 'object' && !field.value) {
              form.setValue('description', '  ');
            }
            return (
              <FormItem className="items-center space-y-0">
                <div className="flex">
                  <FormLabel className="text-sm text-muted-foreground whitespace-nowrap w-1/4">
                    {t('flow.description')}
                  </FormLabel>
                  <FormControl className="w-3/4">
                    <Input {...field}></Input>
                  </FormControl>
                </div>
                <div className="flex pt-1">
                  <div className="w-1/4"></div>
                  <FormMessage />
                </div>
              </FormItem>
            );
          }}
        />
      </FormContainer>
      <div className="text-right pt-4 flex justify-end gap-3">
        <Button
          type="reset"
          className="bg-transparent text-color-white hover:bg-transparent border-gray-500 border-[1px]"
          onClick={() => {
            form.reset();
          }}
        >
          {t('knowledgeConfiguration.cancel')}
        </Button>
        <Button
          type="button"
          disabled={submitLoading}
          onClick={() => {
            (async () => {
              let isValidate = await form.formControl.trigger('name');
              const { name, description } = form.formState.values;
              const avatar = avatarBase64Str;
              if (isValidate) {
                saveKnowledgeConfiguration({
                  kb_id,
                  parser_id,
                  name,
                  description,
                  avatar,
                });
              }
            })();
          }}
        >
          {submitLoading && <Loader2Icon className="animate-spin" />}
          {t('knowledgeConfiguration.save')}
        </Button>
      </div>
      <FormField
        control={form.control}
        name="type"
        render={({ field }) => (
          <FormItem className="space-y-3">
            <FormLabel tooltip={t('knowledgeConfiguration.permissionsTip')}>
              {t('knowledgeConfiguration.permissions')}
            </FormLabel>
            <FormControl>
              <RadioGroup
                onValueChange={(value) => {
                  field.onChange(value);
                  // 如果不是角色类型，清除角色ID
                  if (value !== 'role') {
                    form.setValue('roleId', '');
                  }
                }}
                defaultValue={field.value}
                className="flex flex-col space-y-1"
              >
                <FormItem className="flex items-center space-x-3 space-y-0">
                  <FormControl>
                    <RadioGroupItem value="me" />
                  </FormControl>
                  <FormLabel className="font-normal">
                    {t('knowledgeConfiguration.me')}
                  </FormLabel>
                </FormItem>
                <FormItem className="flex items-center space-x-3 space-y-0">
                  <FormControl>
                    <RadioGroupItem value="team" />
                  </FormControl>
                  <FormLabel className="font-normal">
                    {t('knowledgeConfiguration.team')}
                  </FormLabel>
                </FormItem>
                <FormItem className="flex items-center space-x-3 space-y-0">
                  <FormControl>
                    <RadioGroupItem value="role" />
                  </FormControl>
                  <FormLabel className="font-normal">
                    {t('setting.role')}
                  </FormLabel>
                </FormItem>
              </RadioGroup>
            </FormControl>
            <FormMessage />
          </FormItem>
        )}
      />

      {/* 角色选择框，只在选择"角色"权限时显示 */}
      {form.watch('type') === 'role' && (
        <FormField
          control={form.control}
          name="roleId"
          render={({ field }) => (
            <FormItem>
              <FormLabel>{t('setting.role')}</FormLabel>
              <Select
                onValueChange={field.onChange}
                defaultValue={field.value}
                disabled={loading}
              >
                <FormControl>
                  <SelectTrigger>
                    <SelectValue placeholder={t('common.pleaseSelect')} />
                  </SelectTrigger>
                </FormControl>
                <SelectContent>
                  {roles.map((role) => (
                    <SelectItem key={role.id} value={role.id}>
                      {role.name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <FormMessage />
            </FormItem>
          )}
        />
      )}
    </>
  );
}
