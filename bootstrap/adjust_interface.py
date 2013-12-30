#!/usr/bin/python

f = open('/etc/network/interfaces','a')
f.write("""
allow-hotplug eth1
iface eth1 inet static
  address 192.168.42.1
  netmask 255.255.255.0
""")
f.close()

f = open('/etc/sysctl.conf','a')
f.write("""
net.ipv4.ip_forward=1
""")
f.close()


