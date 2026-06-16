#!/bin/bash
set -e

# Allow external connections
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" /etc/postgresql/14/main/postgresql.conf
echo "host all all 0.0.0.0/0 md5" >> /etc/postgresql/14/main/pg_hba.conf

systemctl restart postgresql

# Create user and database
sudo -u postgres psql -c "CREATE USER babyapp WITH PASSWORD 'babypass';"
sudo -u postgres psql -c "CREATE DATABASE babyfoods OWNER babyapp;"

echo "DONE"
