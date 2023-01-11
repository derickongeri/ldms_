from django import forms
from ldms.models import SystemSettings

class SystemSettingsForm(forms.ModelForm):
    email_host_password = forms.CharField(widget=forms.PasswordInput)

    class Meta:
        model = SystemSettings
        fields = '__all__' # ('name', 'email', 'password', 'instrument_purchase', 'house_no', 'address_line1', 'address_line2', 'telephone', 'zip_code', 'state', 'country')
