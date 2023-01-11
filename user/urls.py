from django.conf.urls import url
from user.views import UserRegistrationView, UserLoginView
from user.views import UserRetrieveView, UserUpdateView
from user.views import ChangePasswordView, UserUpdateView
from user.views import RequestResetForgottenPasswordView
from user.views import ResetForgottenPasswordView
from user.views import UserList
from user.views import UserAccountActivationView
from django.urls import path

useraccount_activate = UserAccountActivationView.as_view({
	'get': 'activate'
})

request_reset_pwd = RequestResetForgottenPasswordView.as_view(actions={
	'post': 'request_password_reset'
})

reset_pwd = ResetForgottenPasswordView.as_view(actions={
	'post': 'reset_password'
})

"""Do not forget the trailing / in the url"""
urlpatterns = [
    url(r'^signup/', UserRegistrationView.as_view()),
    url(r'^login/', UserLoginView.as_view()),
    #url(r'^profile', UserProfileView.as_view()),
    # url(r'^user', UserRetrieveUpdateView.as_view()),
    url(r'^user/', UserRetrieveView.as_view()),
    url(r'^users/', UserList.as_view()),
    url(r'^requestpwdreset/', request_reset_pwd),
    url(r'^resetpwd/', reset_pwd),
    url(r'^changepwd/', ChangePasswordView.as_view()),
    url(r'^updateuser/', UserUpdateView.as_view()),
    path(r'activate/<uidb64>/<token>/', useraccount_activate, name='activate')
    # url(r'^activate/(?P<uidb64>[0-9A-Za-z_\-]+)/(?P<token>[0-9A-Za-z]{1,13}-[0-9A-Za-z]{1,20})/$',UserAccountActivationView.as_view(), name='activate')
]