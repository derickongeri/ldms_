# Deployment for production <Native Setup>

Refer to **DEPLOY.md** located under **backend/deploy** directory

Refer to https://medium.com/analytics-vidhya/dajngo-with-nginx-gunicorn-aaf8431dc9e0
Refer to https://www.linode.com/docs/web-servers/nginx/how-to-configure-nginx/

## Prerequisites

* Port 22, 80, 8000 must be open on the server.

## Setup GUnicorn

* Install GUnicorn in the virtual environment
 <pre>pip install gunicorn</pre>

* Edit the gunicorn_start script. The script is located as detailed in the gunicorn_start script. **The paths specified in the script must be edited accordingly**. Normally, you may only have to edit these lines
 <pre> PROJECT_PARENT_DIR=/home/nyaga/django-apps </pre>
 <pre> VIRTUAL_ENV_BIN=/home/nyaga/virtualenvs/geoDjangoEnv/bin </pre>

* Remember to set the script as executable
 <pre> sudo chmod u+x gunicorn_start </pre>

* Test gunicorn_start script
 <pre> gunicorn_start </pre>

* Stop the execution of gunicorn_start script by pressing CTRL+C keys

* Create the file to store log messages, although the script will auto create this folder. Make sure you are at $PROJECT_HOME path
 <pre> mkdir logs </pre>

 ### Setting up GUnicorn to auto start on boot

* Create a file named **/etc/systemd/system/oss_ldms.service** by running the command below to run the gunicorn_start on boot 

<pre> sudo nano /etc/systemd/system/oss_ldms.service </pre>

* Paste the contents of gunicorn.service into the service and edit the section below

<pre> ExecStart=/home/nyaga/app/oss_ldms/backend/deploy/gunicorn_start </pre>  

* Make sure the gunicorn_start script is set as executable by running 

<pre> sudo chmod u+x gunicorn_start </pre>

* Enable the service to run on boot

<pre> sudo systemctl enable oss_ldms.service </pre>

* Start the service by running the command below

<pre> sudo systemctl start oss_ldms.service </pre>

* You can check the status of the service by running the command below. The service needs to be running otherwise Nginx will show error 404 not found.

<pre> sudo systemctl status oss_ldms.service </pre>

 ## Setup NGinx

* Install Nginx
<pre>
    sudo apt-get install nginx
    sudo service nginx start
</pre>

* Verify that Nginx is working by typing 0.0.0.0 on the browser

* Create a new nginx server configuration file located in Nginx sites-available directory. By default, there is only one conf file named default that has a basic setup for NGINX. You can either modify it or create a new one. In our case, we disable the default site by deleting the symlink to delete it since it will be the default site that will be served. But we want our site to be served by default:

<pre>
    sudo unlink /etc/nginx/sites-enabled/default
</pre>

<pre>
    sudo nano /etc/nginx/sites-available/oss_ldms
</pre>

* Replace the contents of /etc/nginx/sites-available/oss_ldms with the contents of the deploy/nginx_conf. **Take note of some of the paths that are specified here that must be consistent with the paths specified when starting GUnicorn, e.g the location of the sock file and the log files. The location of the files must also be edited accordingly**

* Create a symbolic link in the sites-enabled folder

<pre>
    sudo ln -s /etc/nginx/sites-available/oss_ldms /etc/nginx/sites-enabled/oss_ldms
</pre>

* Restart Nginx

<pre> sudo service nginx restart </pre>

* Open the server url to view the django application

<pre> http://SERVER_URL </pre>

* If the static files are not loading, activate the virtual environment, navigate to the location of the DJango project files and run 

<pre> python manage.py collectstatic </pre>

* Restart the server to verify that all is working as expected

# Increase server timeout

Refer to https://medium.com/@paragsharma.py/504-gateway-timeout-django-gunicorn-nginx-4570deaf0922

1. Update ExecStart in the gunicorn_start script to be as below:

<pre>
exec $VIRTUAL_ENV_BIN/gunicorn ${DJANGO_WSGI_MODULE}:application \
--name $NAME \
--workers $NUM_WORKERS \
--user=$USER --group=$GROUP \
--bind=unix:$SOCKFILE \
--log-level=debug \
--timeout=300 \
--log-file=-
</pre>

* timeout=300 means 5 minutes. Its preferred you increase to 10 minutes (600 seconds)

2. Update Nginx params

<pre>sudo nano /etc/nginx/proxy_params</pre>

Add these parameters:
<pre>
proxy_connect_timeout   300;
proxy_send_timeout      300;
proxy_read_timeout      300;
</pre>

# Deployment for production

* Install supervisorctld <pre>sudo apt-get install supervisord or sudo pip install supervisor</pre>
* Create a symbolic link to the conf file
<pre> sudo ln -s /home/nyaga/app/oss_ldms/backend/deploy/supervisor_prod.conf /etc/supervisor/conf.d/oss_ldms </pre>

* Set up supervisor
<pre>
1. sudo supervisorctl
2. reread
3. add oss_ldms-web
3. update
4. start all
</pre>

* To start or stop all processes, run <pre> sudo supervisorctl start|stop all</pre>

# Deployment for production <Docker Container Setup>

### Coming soon