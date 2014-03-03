#!/bin/sh

# change hostname
CURRENT_HOSTNAME=`cat /etc/hostname | tr -d " \t\n\r"`
NEW_HOSTNAME='wormhole'
echo $NEW_HOSTNAME > /etc/hostname
sed -i "s/127.0.1.1.*$CURRENT_HOSTNAME/127.0.1.1\t$NEW_HOSTNAME/g" /etc/hosts

# install packages
apt-get install -y hostapd memcached openvpn isc-dhcp-server nginx supervisor

# networking
cat ip_forward | tee -a /etc/sysctl.conf
cp interfaces /etc/network/interfaces

# change hostapd binary
service hostapd stop
mv /usr/sbin/hostapd /usr/sbin/hostapd.ORIG 
cp hostapd /usr/sbin
chmod 755 /usr/sbin/hostapd
cp hostapd.conf /etc/hostapd/hostapd.conf
cp hostapd_initd /etc/init.d/hostapd
chmod 755 /etc/init.d/hostapd

sudo shutdown -r now && exit

