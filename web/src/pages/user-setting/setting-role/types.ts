export interface IRoleUser {
    id: string;
    username: string;
    avatar?: string;
    email: string;
  }
  
  export interface IRole {
    id: string;
    name: string;
    description?: string;
    tenant_id: string; // 角色所属的租户ID
    created_by: string;
    created_time: number;
    updated_time: number;
    permissions: IPermission[];
    users?: IRoleUser[];
  }
  
  export interface IPermission {
    id: string;
    resource_type: 'knowledgebase';
    resource_id: string;
    resource_name: string;
    permission_type: 'read' | 'write' | 'admin';
  }
  
  export enum PermissionScope {
    OWNER = 'owner', // 只有我
    TEAM = 'team', // 团队
    ROLE = 'role', // 指定角色
  }
  
  export enum PermissionType {
    READ = 'read',
    WRITE = 'write',
    ADMIN = 'admin',
  }
  