# change hostname
CURRENT_HOSTNAME=`cat /etc/hostname | tr -d " \t\n\r"`
NEW_HOSTNAME='wormhole'
echo $NEW_HOSTNAME > /etc/hostname
sed -i "s/127.0.1.1.*$CURRENT_HOSTNAME/127.0.1.1\t$NEW_HOSTNAME/g" /etc/hosts

# disable interfaces
ifdown wlan0
ifdown eth1

# install packages
apt-get install -y hostapd memcached openvpn isc-dhcp-server
pip install web.py boto python-memcached

# IP forwarding
cat ip_forward | tee -a /etc/sysctl.conf
sh -c "echo 1 > /proc/sys/net/ipv4/ip_forward"

# change hostapd binary
service hostapd stop
mv /usr/sbin/hostapd /usr/sbin/hostapd.ORIG 
mv hostapd /usr/sbin
chmod 755 /usr/sbin/hostapd

# copy config files
cp interfaces /etc/network/interfaces
cp dhcpd.conf /etc/dhcp/
cp hostapd.conf /etc/hostapd/hostapd.conf
cp isc-dhcp-server /etc/default/
cp iptables /etc/network/if-pre-up.d/iptables
chmod +x /etc/network/if-pre-up.d/iptables

ifup wlan0
ifup eth1
ifconfig eth1 192.168.42.1
ifconfig wlan0 192.168.43.1

update-rc.d isc-dhcp-server enable
service hostapd start
