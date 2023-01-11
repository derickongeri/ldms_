from django.apps import AppConfig


class LdmsConfig(AppConfig):
    name = 'ldms'

    def ready(self):
        import ldms.signals