#!/bin/bash

if [ $# -eq 0 ]
  then
    echo "No arguments supplied. Please enter server host name or IP address"
    exit 1
fi

sudo systemctl stop kw_dist_agent.service
sudo systemctl disable kw_dist_agent.service
sudo systemctl daemon-reload
sudo rm -f /etc/systemd/system/kw_dist_agent.service
sudo cat > /etc/systemd/system/kw_dist_agent.service << EOF
[Unit]
Description=KW distributed build agent systemd service.
After=network-online.target

[Service]
Type=simple
ExecStart=/bin/sh /home/sys_sysfw/kw_dist/bin/kwagent --host $1 -j 5
Restart=always
# Restart service after 10 seconds
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo chmod 644 /etc/systemd/system/kw_dist_agent.service
sudo systemctl enable kw_dist_agent.service


