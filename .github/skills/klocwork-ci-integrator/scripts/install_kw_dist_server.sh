#!/bin/bash

sudo systemctl stop kw_dist_server.service
sudo systemctl disable kw_dist_server.service
sudo systemctl daemon-reload
sudo rm -f /etc/systemd/system/kw_dist_server.service
sudo cat > /etc/systemd/system/kw_dist_server.service << EOF
[Unit]
Description=KW distributed build server systemd service.

[Service]
Type=simple
ExecStart=/bin/sh /home/sys_sysfw/kw_dist/bin/kwdist --web-host klocwork-igk2.devtools.intel.com --web-port 8080 --web-ssl
Restart=always
# Restart service after 10 seconds
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF
sudo chmod 644 /etc/systemd/system/kw_dist_server.service
sudo systemctl enable kw_dist_server.service
