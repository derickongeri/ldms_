from django.core.mail import EmailMessage, send_mail
from email.message import EmailMessage as CoreEmailMessage
from django.conf import settings
from ldms.utils.log_util import log_error
import smtplib# Import smtplib library to send email in python
from ldms.utils.settings_util import get_settings
from email.utils import formataddr
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

def send(subject, message, recipients):
	"""Send email"""
	return send_email_core(subject, message, recipients)
	# # if type(recipients) != list:
	# # 	recipients = [recipients] 
	# if type(recipients) != list:
	# 	recipients = [recipients]
	# res = None
	# for recipient in recipients:
	# 	res = send_email_core(subject, message, recipient)
	# return res
	# if type(recipients) != list:
	# 	recipients = [recipients] 

	# # email = EmailMessage(
	# # 		subject=subject, 
	# # 		body=message, 
	# # 		from_email=settings.EMAIL_HOST_USER, 
	# # 		to=recipients
	# # )	
	# # return email.send()
	# if not isinstance(message, CoreEmailMessage):
	# 	message = message.as_string()
	# else:	
	# 	message = message
	# try:
	# 	return send_mail(subject=subject, 
	# 			message='', # message, 
	# 			from_email=settings.EMAIL_HOST_USER, 
	# 			recipient_list=recipients,
	# 			auth_user=settings.EMAIL_HOST_USER,
	# 			auth_password=settings.EMAIL_HOST_PASSWORD,
	# 			html_message=message)
	# except Exception as e:
	# 	log_error(str(e))
	# 	pass

def send_email_core(subject, message, recipients):
	"""Send email"""
	if type(recipients) != list:
		recipients = [recipients]

	setts = get_settings()
	if isinstance(message, CoreEmailMessage):
		message['subject'] = subject
		message['From'] = formataddr((setts.email_from_name, setts.email_from_address))
		email = message.as_string()
	else:
		email = MIMEMultipart()
		email['From'] = '{0} <{1}>'.format(setts.email_from_name, setts.email_from_address)
		email['To'] = ", ".join(recipients)
		email['Subject'] = subject
		email.attach(MIMEText(message))
		email = email.as_string()
		
	if setts.email_host_port:
		settings.EMAIL_HOST = setts.email_host
		settings.EMAIL_HOST_PASSWORD = setts.email_host_password
		settings.EMAIL_HOST_USER = setts.email_host_user
		settings.EMAIL_PORT = setts.email_host_port
		settings.EMAIL_USE_TLS = setts.email_host_protocol=="TLS"
		settings.EMAIL_USE_SSL = setts.email_host_protocol=="SSL"	

	try:
		print("Sending email to {0}".format(recipients))
		# Create an smtplib.SMTP object to send the email.
		smtp = smtplib.SMTP_SSL(settings.EMAIL_HOST, port=settings.EMAIL_PORT)
		smtp.ehlo()
		# Login to the SMTP server with username and password.
		smtp.login(settings.EMAIL_HOST_USER, settings.EMAIL_HOST_PASSWORD)
		
		# Send email with the smtp object sendmail method.
		send_errors = smtp.sendmail(setts.email_from_address, recipients, email)
		# send_errors = smtp.sendmail(settings.EMAIL_HOST_USER, recipients, email)
		# Quit the SMTP server after sending the email.
		smtp.quit()
		return not send_errors
	except Exception as e:
		print(str(e))
		log_error(str(e))
		pass