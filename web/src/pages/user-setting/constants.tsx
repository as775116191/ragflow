import {
  ApiIcon,
  LogOutIcon,
  ModelProviderIcon,
  PasswordIcon,
  ProfileIcon,
  TeamIcon,
} from '@/assets/icon/Icon';
import { LLMFactory } from '@/constants/llm';
import { UserSettingRouteKey } from '@/constants/setting';
import { MonitorOutlined, UserSwitchOutlined } from '@ant-design/icons';

export const UserSettingIconMap = {
  [UserSettingRouteKey.Profile]: <ProfileIcon />,
  [UserSettingRouteKey.Password]: <PasswordIcon />,
  [UserSettingRouteKey.Model]: <ModelProviderIcon />,
  [UserSettingRouteKey.System]: <MonitorOutlined style={{ fontSize: 24 }} />,
  [UserSettingRouteKey.Team]: <TeamIcon />,
  [UserSettingRouteKey.Role]: <UserSwitchOutlined style={{ fontSize: 24 }} />,
  [UserSettingRouteKey.Logout]: <LogOutIcon />,
  [UserSettingRouteKey.Api]: <ApiIcon />,
};

export * from '@/constants/setting';

export const LocalLlmFactories = [
  LLMFactory.Ollama,
  LLMFactory.Xinference,
  LLMFactory.LocalAI,
  LLMFactory.LMStudio,
  LLMFactory.OpenAiAPICompatible,
  LLMFactory.TogetherAI,
  LLMFactory.Replicate,
  LLMFactory.OpenRouter,
  LLMFactory.HuggingFace,
  LLMFactory.GPUStack,
  LLMFactory.ModelScope,
  LLMFactory.VLLM,
];

export enum TenantRole {
  Owner = 'owner',
  Admin = 'admin',
  Normal = 'normal',
}
