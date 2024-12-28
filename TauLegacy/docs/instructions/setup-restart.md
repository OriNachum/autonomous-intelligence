# Setting up auto-restart tau

## start_apps executable
Ensure the file start_apps.sh is executable:
`chmod +x /home/pi/start_apps.sh`

## update the service file

Create a `service_apps.service` at `/etc/systemd/system/start_apps.service`
### Content: 
```service
[Unit]
Description=Start Multiple Applications on Startup
After=network.target

[Service]
Type=simple
ExecStart=/bin/bash /home/tau/git/autonomous-intelligence/start_apps.sh
Restart=always
User=pi
Environment=DISPLAY=:0
WorkingDirectory=/home/pi

[Install]
WantedBy=multi-user.target
```

### Instructions:

#### Reload systemd to apply changes
`sudo systemctl daemon-reload`

#### Restart the service
`sudo systemctl restart start_apps.service`

#### Enable the service to run on startup
`sudo systemctl enable start_apps.service`

#### Check the status of the service
`sudo systemctl status start_apps.service`

