from user.utils import email_util 
from django.conf import settings
from django.core.mail import EmailMessage, send_mail
from ldms.utils.settings_util import get_settings

def send_email(subject, message, recipients):
	setts = get_settings()
	if setts.email_host_port:
		settings.EMAIL_HOST = setts.email_host
		settings.EMAIL_HOST_PASSWORD = setts.email_host_password
		settings.EMAIL_HOST_USER = setts.email_host_user
		settings.EMAIL_PORT = setts.email_host_port
		settings.EMAIL_USE_TLS = setts.email_host_protocol=="TLS"
		settings.EMAIL_USE_SSL = setts.email_host_protocol=="SSL"		
	# return send_mail(subject, message, 
	# 				from_email=settings.DEFAULT_FROM_EMAIL, 
	# 				recipients, 
	# 				fail_silently=False, 
	# 				auth_user=None, 
	# 				auth_password=None, 
	# 				connection=None, 
	# 				html_message=None)
	return email_util.send(subject, message, recipients)