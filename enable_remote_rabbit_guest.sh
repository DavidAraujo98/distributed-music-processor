#!/bin/bash

# If config file not existant, one will be created
sudo touch /etc/rabbitmq/rabbitmq.conf

# Set the permission for the guest to connect from a remote host
sudo echo "loopback_users = none" >> /etc/rabbitmq/rabbitmq.conf

# Will set the variable at every login
sudo echo "export RABBITMQ_CONFIG_FILE="/etc/rabbitmq/rabbitmq.conf"" >> ~/.profile

# Will set the variable for the current section,
# after that it will be redundant to the one set before
sudo echo "export RABBITMQ_CONFIG_FILE="/etc/rabbitmq/rabbitmq.conf"" >> ~/.bashrc

# Restarts rabbitmq-server service
sudo systemctl restart rabbitmq-server

# Allows rabbitmq and api through ufw firewall (common on debian)
sudo ufw allow 5672     # RabbitMQ port
sudo ufw allow 15672    # RabbitMQ Management port
sudo ufw allow 8000     # Flask/FastAPI ports

# Enable rabbitmqadmin with login
## username -   guest
## password -   guest
sudo rabbitmq-plugins enable rabbitmq_management

# Opens RabbitMQ menagement console in default browser
xdg-open http://localhost:15672/
