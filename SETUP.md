## Prerequisites

* Python >=3.6
* Install postgres
* Install postgis extension <pre> sudo apt-get install postgis </pre>
* Install docker
* Install gdal libraries 
    <pre>
        sudo apt-get install binutils libproj-dev gdal-bin
    </pre>
* Create a python virtual env

## Steps to set up the project quickly in a devevelopment environment

* Ensure Python >=3.6 is installed
* Install docker
* Install gdal libraries 
    <pre>
        sudo apt-get install binutils libproj-dev gdal-bin
    </pre>
* Clone the repo https://gitlab.com/locateit/oss-land-degradation-monitoring-service/oss-ldms.git
* Set up a virtual env with Python3 as the base interpreter
* Activate the virtual env
* cd to the backend directory in the code repository location
* Run <pre>pip install -r requirements.txt </pre>
* Pull postgres docker image
    <pre>
        docker pull kartoza/postgis:9.6-2.4
    </pre>
* Create a ~/postgres_data folder to persist the db data created by the Postgres container
* Add current user to docker group to enable running docker daemon without root privileges. Logout and relogin for these changes to be applied
<pre>
    $ sudo usermod -aG docker $USER
</pre>

* Start the Postgres container
<pre>
    docker run -d -v $HOME/postgres_data:/var/lib/postgresql kartoza/postgis
    $ docker run -v $HOME/postgres_data:/var/lib/postgresql --name=postgis -d -e POSTGRES_USER=ldms_user -e POSTGRES_PASS=ldms123 -e POSTGRES_DBNAME=oss_ldms -p 5432:5432 kartoza/postgis:9.6-2.4
</pre>
After running the command, you’ll have a PostgreSQL server listening on the 5432 port with a database called **gis**. The database uses the **ldms_user** username and the **ldms123** as the password
* cd to the backend directory in the code repository location and run the command below to start the development server. MAke sure the virtual env is activated
<pre> python manage.py runserver </pre>
* If all is well, the server will start Ok but will complain about migrations that are unapplied. Stop the server by pressing CTRL+C.
* To apply the migrations, run <pre> python manage.py migrate </pre>
* Start the development server and you can now load the system using http://0.0.0.0:8000
* You can also perform other manipulations like creating Django admin superuser <pre> python manage.py createsuperuser </pre>

**NB**: If you are setting up in a VPS and may want to expose port 80, you will encounter an error that "You do not have access to that port". A workaround is to run the command as python manage.py runserver $IP:$PORT e.g <pre> python manage.py runserver 0.0.0.0:8000</pre>

## Postgres Configuration

1. Log in to postgres
<pre> sudo -u postgres psql </pre>

1. Create database
<pre>
potgres=# CREATE DATABASE oss_ldms;
</pre>

1. Create database user
<pre>
potgres=# CREATE USER ldms_user WITH PASSWORD 'ldms123';
</pre>

1. Add PostGIS extension
<pre>
potgres=#  CREATE EXTENSION postgis;
</pre>

1. Set default encoding to UTF-8
<pre>
potgres=# ALTER ROLE ldms_user SET client_encoding TO 'utf8';
</pre>

1. Set the default transaction isolation scheme to "read committed", which blocks reads from uncommitted transactions.
<pre>
potgres=# ALTER ROLE ldms_user SET default_transaction_isolation TO 'read committed';
</pre>

1. Set timezone to UTC
<pre>
potgres=# ALTER ROLE ldms_user SET timezone TO 'UTC';
</pre>

1. Make user as superuser
<pre>
postgres=# ALTER ROLE ldms_user SUPERUSER;
</pre>

1. Grant user database privileges
<pre>
postgres=# GRANT ALL PRIVILEGES ON DATABASE oss_ldms TO ldms_user;
</pre>

1. Indicate where static files will be placed. This is necessary so that Nginx can handle requests for these items.Add the following to the bottom of the settings.py file.

<pre>
STATIC_URL = '/static/'
STATIC_ROOT = os.path.join(BASE_DIR, 'static/')
</pre>

1. Collect all the static content into the directory we configured.The static files will be placed in a directory called static within the project directory.

<pre>
python manage.py collectstatic
</pre>

1. Install django-rest-framework
<pre>
pip install djangorestframework
</pre>

1. Install django-rest-framework-gis
<pre>
pip install djangorestframework-gis
</pre>

1. Add postgis extension to your database;

<pre>
sudo -u postgres psql -d oss_ldms

oss_ldms=# CREATE EXTENSION POSTGIS;
</pre>

1. Run these queries before importing shapefiles

<pre>
Alter table ldms_adminlevelzero alter column cpu drop not null, alter column geom drop not null;
</pre>

<pre>
Alter table ldms_adminlevelone 
    alter column cpu drop not null, 
    alter column varname_1 drop not null, 
    alter column nl_name_1 drop not null, 
    alter column type_1 drop not null, 
    alter column engtype_1 drop not null, 
    alter column hasc_1 drop not null, 
    alter column cpu drop not null, 
    alter column geom drop not null, 
    alter column gid_1 drop not null, 
    alter column cc_1 drop not null;
</pre>

<pre>
Alter table ldms_adminleveltwo 
    alter column nl_name_1 drop not null, 
    alter column varname_2 drop not null, 
    alter column nl_name_2 drop not null, 
    alter column type_2 drop not null, 
    alter column engtype_2 drop not null, 
    alter column hasc_2 drop not null, 
    alter column cpu drop not null,
    alter column geom drop not null, 
    alter column cc_2 drop not null;
</pre>

# Deployment for production

Refer to **DEPLOY.md** located under **backend/deploy** directory

# Increase server timeout

Refer to **DEPLOY.md** located under **backend/deploy** directory

# Improve Pandas performance

https://engineering.upside.com/a-beginners-guide-to-optimizing-pandas-code-for-speed-c09ef2c6a4d6

# Dump postgres database

See https://www.prisma.io/dataguide/postgresql/inserting-and-modifying-data/importing-and-exporting-data-in-postgresql


> pg_dump -h 127.0.0.1 -U ldms_user oss_ldms > ~/app/oss_ldms.sql

**NB**. If within a Docker container, ensure you run the **exec** command before running the above command, e.g

> docker-compose -f docker-compose.prod.yml exec db bash
(Where db is the docker service name)

> pg_dump -h 127.0.0.1 -U rcmrd_user rcmrd > /var/lib/postgresql/data/rcmrd_backup.sql

* This will store the backup file in the shared volumes. So you can just directly copy the file from that shared volume. You can navigate to the host volume like in the example below:

> ls /var/lib/docker/volumes/rcmrd_site_postgres_data/_data

You can zip the sql file by running 

> zip oss_ldms_backup_20210313.zip oss_ldms_backup_20210313.sql