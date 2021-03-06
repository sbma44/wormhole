import boto.ec2
import os, sys, time, sqlite3, subprocess, json
from settings import *
from threading import Thread
from urllib import urlopen
from threading  import Thread
from uuid import getnode as get_mac_id
import envoy
try:
    from Queue import Queue, Empty
except ImportError:
    from queue import Queue, Empty  # python 3.x

ON_POSIX = 'posix' in sys.builtin_module_names

def enqueue_output(out, queue):
    for line in iter(out.readline, b''):
        queue.put(line)
    out.close()

def get_valid_regions():
	r = Wormhole.REGIONS.copy()
	for k in Wormhole.REGIONS:
		if len(Wormhole.REGIONS[k].get('ami_id', ''))==0:
			del r[k]
	return r

class Wormhole(object):
	"""Creates EC2 instances for OpenVPN tunneling"""
	def __init__(self, region='us-west-1', aws_access_key=None, aws_secret_key=None, aws_key_directory='.'):
		super(Wormhole, self).__init__()		

		if not self.REGIONS.get(region):
			raise Exception('Invalid AWS region.')

		if len(self.REGIONS.get(region, {}).get('ami_id', ''))==0:
			raise Exception('Wormhole AMI not yet available in region %s.' % region)

		if None in (aws_access_key, aws_secret_key): 
			(aws_access_key, aws_secret_key) = (os.getenv('AWS_ACCESS_KEY'), os.getenv('AWS_SECRET_KEY'))
		self.conn = boto.ec2.connect_to_region(region, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)					
		self.region = region
		self.security_group = None
		self.aws_key_directory = aws_key_directory
		self.key_pair = None
		self.key_pair_name = 'keypair_%s' % region
		self.public_ip = None
		self.reservation = None	
		self.aws_access_key = aws_access_key
		self.aws_secret_key = aws_secret_key
		self.system_id = get_mac_id()

	def validate_credentials(self):
		try:
			self.conn.get_all_regions()
		except:
			return False
		return True

	def stop_all_global_instances(self):
		for (region_id, region_values) in self.REGIONS.items():
			ami_id = region_values.get('ami_id', '')
			if len(ami_id)==0:
				continue
			wh = Wormhole(region_id, self.aws_access_key, self.aws_secret_key)
			for instance in wh.conn.get_only_instances():
				system_id = instance.tags.get('wormhole-system-id')
				if system_id==self.system_id and instance.image_id==ami_id:
					instance.terminate()

	def get_public_ip(self):
		# TODO: make this use a secure service that you control
		self.public_ip = urlopen('http://bot.whatismyipaddress.com/').read().strip()
		return self.public_ip

	def _get_or_create_security_group(self):
		# clean up whatever wormhole security groups we can
		security_groups = self.conn.get_all_security_groups()
		for wormhole_sg in security_groups:			
			if wormhole_sg.name.startswith(self.SECURITY_GROUP_NAME):
				try:
					wormhole_sg.delete()
				except:
					print "Tried to delete security group %s but could not" % wormhole_sg.name
		
		novel_security_group_name = "%s-%s" % (self.SECURITY_GROUP_NAME, str(int(time.time())))
		self.security_group = self.conn.create_security_group(novel_security_group_name, 'Wormhole VPN project')
		self.security_group.authorize(ip_protocol='tcp', from_port=22, to_port=22, cidr_ip='0.0.0.0/0')
		return self.security_group	

	def _key_path(self):
		return self.aws_key_directory
		#return "%s/keypair_%s.pem" % (self.aws_key_directory, self.region)

	def create_key_pair_if_necessary(self):
		for kp in self.conn.get_all_key_pairs():
			if kp.name==self.key_pair_name:
				self.key_pair = kp

		# have we got both the KP record and the .pem file? if so, we're fine
		if self.key_pair is not None and os.path.exists(self._key_path()):
			return self.key_pair
		
		# if not, delete broken half-KPs
		elif self.key_pair is not None:
			self.key_pair.delete()
		elif os.path.exists('%s/%s.pem' % (self._key_path(), self.key_pair_name)):
			os.unlink('%s/%s.pem' % (self._key_path(), self.key_pair_name))

		self.key_pair = self.conn.create_key_pair(self.key_pair_name)
		self.key_pair.save(self._key_path())
		
		return self.key_pair

	def enable_access(self):
		if self.security_group is None:
			self._get_or_create_security_group()
		self.security_group.authorize(ip_protocol='udp', from_port=self.OPENVPN_PORT, to_port=self.OPENVPN_PORT, cidr_ip='%s/32' % self.get_public_ip())

	def disable_access(self):
		if self.security_group is None:
			self._get_or_create_security_group()
		if self.public_ip is None:
			self.get_public_ip()
		self.security_group.revoke(ip_protocol='udp', from_port=self.OPENVPN_PORT, to_port=self.OPENVPN_PORT, cidr_ip='%s/32' % self.public_ip)

	def start_instance(self, tags={}):
		print 'Setting up key pair...'
		self.create_key_pair_if_necessary()
		
		print 'Configuring security rule...'
		self.enable_access()		

		print 'Launching instance...'
		self.reservation = self.conn.run_instances(self.REGIONS[self.region]['ami_id'], key_name=self.key_pair_name, instance_type=self.INSTANCE_SIZE, security_groups=[self.security_group.name])
		self.instance = self.reservation.instances[0]

		tags['wormhole-system-id'] = self.system_id
		for (t, t_value) in tags.items():
			self.instance.add_tag(t, t_value)		

		print 'Waiting for instance...'
		while self.instance.state!='running':
			time.sleep(5)
			self.instance.update()
		
		print 'Instance is running.'
		self.instance_ip = self.instance.ip_address

	def start_openvpn(self):
		# openvpn process call
		openvpn_call = [
			'openvpn',
			'--client',
			'--dev', 'tun',
			'--proto', 'udp',
			'--remote',	self.instance_ip, self.OPENVPN_PORT,
			'--resolv-retry', 'infinite',
			'--nobind',
			'--persist-key',
			'--persist-tun',
			'--ca',	'ca.crt',
			'--cert', 'client.crt',
			'--key', 'client.key',
			'--comp-lzo',
			'--verb', '3',
			'--cd',	OPENVPN_DIRECTORY,
			#'--setenv', 'test_key', 'test_value'
		]

		self.tunnel_process = subprocess.Popen(map(lambda x: str(x), openvpn_call), stdout=subprocess.PIPE, bufsize=1, close_fds=ON_POSIX)
		self.tunnel_process_stdout = ''		
		self.tunnel_message_queue = Queue()
		
		t = Thread(target=enqueue_output, args=(self.tunnel_process.stdout, self.tunnel_message_queue))
		t.daemon = True # thread dies with the program
		t.start()

	def stop_openvpn(self):
		self.tunnel_process.terminate()
		self.tunnel_process.wait()

	def start_routing(self):
		f = open('iptables-tunnel.rules', 'r')
		rules = f.read()
		f.close()
		envoy.run('/sbin/iptables-restore -c', data=rules, timeout=2)

	def stop_routing(self):
		f = open('iptables-nat.rules', 'r')
		rules = f.read()
		f.close()
		envoy.run('/sbin/iptables-restore -c', data=rules, timeout=2)

	def check_tunnel_status(self):				
		# read line without blocking
		while True:
			try:
				line = self.tunnel_message_queue.get_nowait()
			except Empty:
				break
			else: # got line
				self.tunnel_process_stdout += line

		if 'initialization sequence completed' in self.tunnel_process_stdout.lower():
			return 'ready'
		else:
			return 'working'

	def stop_instance(self):
		self.disable_access()
		self.instance.terminate()
		try:
			self.security_group.delete()
		except:
			pass

	REGIONS = {
		'us-east-1': {
			u'ami_id': u'',
	  		u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.us-east-1.amazonaws.com',
			u'lat': u'38.13',
			u'lon': u'-78.45',
			u'name': u'US East (Northern Virginia) Region',
			u'short_name': u'Virginia'
		},
 		'us-west-2': {
	 		u'ami_id': u'',
	  		u'connection_type': u'HTTP and HTTPS',
	  		u'domain': u'ec2.us-west-2.amazonaws.com',
			u'lat': u'46.15',
			u'lon': u'-123.88',
			u'name': u'US West (Oregon) Region',
			u'short_name': u'Oregon'
		},
		'us-west-1': {
			u'ami_id': u'ami-921320d7',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.us-west-1.amazonaws.com',
			u'lat': u'41.48',
			u'lon': u'-120.53',
			u'name': u'US West (Northern California) Region',
			u'short_name': u'California'
		},
		'eu-west-1': {
			u'ami_id': u'ami-381deb4f',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.eu-west-1.amazonaws.com',
			u'lat': u'53.0',
			u'lon': u'-8.0',
			u'name': u'EU (Ireland) Region',
			u'short_name': u'Ireland'
		},
		'ap-southeast-1': {
			u'ami_id': u'',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.ap-southeast-1.amazonaws.com',
			u'id': u'',
			u'lat': u'1.37',
			u'lon': u'103.8',
			u'name': u'Asia Pacific (Singapore) Region',
			u'short_name': u'Singapore'
		},
		'ap-southeast-2': {
			u'ami_id': u'',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.ap-southeast-2.amazonaws.com',	
			u'lat': u'-33.86',
			u'lon': u'151.2',
			u'name': u'Asia Pacific (Sydney) Region',
			u'short_name': u'Sydney'
		},
		'ap-northeast-1': {
			u'ami_id': u'',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.ap-northeast-1.amazonaws.com',
			u'id': u'',
			u'lat': u'35.41',
			u'lon': u'139.42',
			u'name': u'Asia Pacific (Tokyo) Region',
			u'short_name': u'Tokyo'
		},
		'sa-east-1': {
			u'ami_id': u'',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.sa-east-1.amazonaws.com',
			u'id': u'sa-east-1',
			u'lat': u'-23.34',
			u'lon': u'-46.38',
			u'name': u'South America (Sao Paulo) Region',
			u'short_name': u'Sao Paulo'
		}
	}

	SECURITY_GROUP_NAME = 'wormhole-vpn-sg'
	INSTANCE_SIZE = 't1.micro'
	OPENVPN_PORT = 1194
