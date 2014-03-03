#!/bin/sh

# change hostname
CURRENT_HOSTNAME=`cat /etc/hostname | tr -d " \t\n\r"`
NEW_HOSTNAME='wormhole'
echo $NEW_HOSTNAME > /etc/hostname
sed -i "s/127.0.1.1.*$CURRENT_HOSTNAME/127.0.1.1\t$NEW_HOSTNAME/g" /etc/hosts

# install packages
apt-get install -y hostapd memcached openvpn isc-dhcp-server nginx supervisor

# IP forwarding
cat ip_forward | tee -a /etc/sysctl.conf
sh -c "echo 1 > /proc/sys/net/ipv4/ip_forward"

# change hostapd binary
service hostapd stop
mv /usr/sbin/hostapd /usr/sbin/hostapd.ORIG 
cp hostapd /usr/sbin
chmod 755 /usr/sbin/hostapd
cp hostapd.conf /etc/hostapd/hostapd.conf
cp hostapd_initd /etc/init.d/hostapd
chmod 755 /etc/init.d/hostapd

# copy config files
cp interfaces /etc/network/interfaces
cp dhcpd.conf /etc/dhcp/
cp hostapd.conf /etc/hostapd/hostapd.conf
cp isc-dhcp-server /etc/default/
cp iptables /etc/network/if-pre-up.d/iptables
chmod +x /etc/network/if-pre-up.d/iptables

# web stuff
cp gunicorn_supervisor.conf /etc/supervisor/conf.d/gunicorn.conf
rm /etc/nginx/sites-enabled/default
cp nginx_wormhole.conf /etc/nginx/sites-enabled/wormhole

ifconfig eth1 192.168.42.1
ifconfig wlan0 192.168.43.1

update-rc.d isc-dhcp-server enable
service hostapd start
service supervisor stop && service supervisor start
