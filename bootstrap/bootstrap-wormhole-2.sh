#!/bin/sh

# copy config files
cp dhcpd.conf /etc/dhcp/
cp hostapd.conf /etc/hostapd/hostapd.conf
cp isc-dhcp-server /etc/default/
cp iptables /etc/network/if-pre-up.d/iptables
chmod +x /etc/network/if-pre-up.d/iptables

# web stuff
cp gunicorn_supervisor.conf /etc/supervisor/conf.d/gunicorn.conf
rm /etc/nginx/sites-enabled/default
cp nginx_wormhole.conf /etc/nginx/sites-enabled/wormhole

update-rc.d isc-dhcp-server enable
service hostapd start
service supervisor stop && service supervisor start

sudo shutdown -r now && exit