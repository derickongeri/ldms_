from django.db import migrations

class Migration(DataMigration):
    """
    This should be added as a migration to ensure
    it is executed. The code copies users from the 
    default Django User model to the Custom User model
    
    # appname/migrations/000X_copy_auth_user_data.py

    """
    def forwards(self, orm):
        "Write your forwards methods here."
        for old_u in orm['auth.User'].objects.all():
            new_u = orm.CustomUser.objects.create(
                        date_joined=old_u.date_joined,
                        email=old_u.email and old_u.email or '%s@example.com' % old_u.username,
                        first_name=old_u.first_name,
                        id=old_u.id,
                        is_active=old_u.is_active,
                        is_staff=old_u.is_staff,
                        is_admin=old_u.is_superuser,
                        is_superuser=old_u.is_superuser,
                        last_login=old_u.last_login,
                        last_name=old_u.last_name,
                        password=old_u.password)
            for perm in old_u.user_permissions.all():
                new_u.user_permissions.add(perm)
            for group in old_u.groups.all():
                new_u.groups.add(group)
