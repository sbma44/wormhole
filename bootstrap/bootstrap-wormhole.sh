# change hostname
CURRENT_HOSTNAME=`cat /etc/hostname | tr -d " \t\n\r"`
NEW_HOSTNAME='wormhole'
echo $NEW_HOSTNAME > /etc/hostname
sed -i "s/127.0.1.1.*$CURRENT_HOSTNAME/127.0.1.1\t$NEW_HOSTNAME/g" /etc/hosts

apt-get install -y memcached openvpn isc-dhcp-server
pip install web.py boto python-memcached

cp dhcpd.conf /etc/dhcp/
cp isc-dhcp-server /etc/default/
cp iptables /etc/network/if-pre-up.d/iptables
chmod +x /etc/network/if-pre-up.d/iptables

update-rc.d isc-dhcp-server enable
