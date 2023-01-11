from ldms.models import SystemSettings

def get_settings():
    """
    Load System Settings
    """
    setts = SystemSettings.load()
    return setts