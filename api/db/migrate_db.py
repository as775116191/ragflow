from api.db.db_models import DB, migrate, migrator

# 添加Role表的tenant_id字段迁移
try:
    # 首先检查是否已经存在该字段
    with DB.atomic():
        migrate(migrator.add_column("role", "tenant_id", 
                CharField(max_length=32, null=False, 
                help_text="Tenant ID this role belongs to", 
                index=True)))
except Exception as e:
    print(f"Migration for role.tenant_id already exists or error: {e}")

# 初始化现有数据的tenant_id字段
try:
    from api.db.db_models import Role, User
    from api.db import StatusEnum
    
    with DB.atomic():
        # 获取所有没有tenant_id的角色
        roles_to_update = Role.select().where(
            (Role.tenant_id.is_null(True)) & 
            (Role.status == StatusEnum.VALID.value)
        )
        
        # 更新每个角色的tenant_id为创建者的ID
        for role in roles_to_update:
            Role.update(tenant_id=role.created_by).where(Role.id == role.id).execute()
            
        print(f"Updated tenant_id for {len(list(roles_to_update))} existing roles")
except Exception as e:
    print(f"Error updating existing role records: {e}") 