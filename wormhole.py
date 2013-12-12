import boto.ec2
import os, time, sqlite3, subprocess
from urllib import urlopen

def find_all_global_instances():
	db = sqlite3.connect(self.SQLITE_DB)
	cursor = db.cursor()
	targets = []
	for (name, region_id) in cursor.execute("SELECT name, id FROM regions"):
		targets.append((name, region_id))
	db.close()

	for (name, region_id) in targets:
		wh = Wormhole(region_id)
		for instance in wh.conn.get_only_instances():
			wh.record_instance(instance)

def stop_all_global_instances():
	db = sqlite3.connect(self.SQLITE_DB)
	db.close()

class Wormhole(object):
	"""Creates EC2 instances for OpenVPN tunneling"""
	def __init__(self, region='us-west-1'):
		super(Wormhole, self).__init__()		

		if not self.REGIONS.get(region):
			raise Exception('Invalid AWS region.')

		if len(self.REGIONS.get(region, {}).get('ami_id', ''))==0:
			raise Exception('Wormhole AMI not yet available in region %s.' % region)

		(aws_access_key, aws_secret_key) = self._get_credentials()
		self.conn = boto.ec2.connect_to_region(region, aws_access_key_id=aws_access_key, aws_secret_access_key=aws_secret_key)					
		self.region = region
		self.security_group = None
		self.key_pair = None
		self.public_ip = None
		self.reservation = None		

	def record_instance(self, instance):
		db = sqlite3.connect(self.SQLITE_DB)
		cursor = db.cursor()
		cursor.execute("DELETE FROM instances WHERE instance_id=?", (instance.id,))
		cursor.execute("INSERT INTO instances (instance_id, timestamp, region, ip, state, public_dns_name, instance_type, image_id) VALUES (?, ?, ?, ?, ?, ?, ?, ?);", (instance.id, int(time.time()), self.region, instance.ip_address, instance.state, instance.public_dns_name, instance.instance_type, instance.image_id))
		db.commit()
		db.close()

	def _get_credentials(self):
		return (os.getenv('AWS_ACCESS_KEY'), os.getenv('AWS_SECRET_KEY'))

	def get_public_ip(self):
		self.public_ip = urlopen('http://bot.whatismyipaddress.com/').read().strip()
		return self.public_ip

	def _get_or_create_security_group(self):
		security_groups = self.conn.get_all_security_groups()
		for wormhole_sg in security_groups:			
			if wormhole_sg.name==self.SECURITY_GROUP_NAME:
				# remove orphan SGs with port 1194 open
				for rule in wormhole_sg.rules:					
					if int(rule.from_port)==1194 and int(rule.to_port)==1194 and rule.ip_protocol.lower().strip()=='udp':
						wormhole_sg.delete()
						wormhole_sg = None
				self.security_group = wormhole_sg
		
		if self.security_group is not None:
			return self.security_group
		else:
			self.security_group = self.conn.create_security_group(self.SECURITY_GROUP_NAME, 'Wormhole VPN project')
			self.security_group.authorize(ip_protocol='tcp', from_port=22, to_port=22, cidr_ip='0.0.0.0/0')
			return self.security_group	

	def _key_path(self):
		return "%s/%s.pem" % (self.KEY_PAIR_PATH, self.KEY_PAIR_NAME)

	def create_key_pair_if_necessary(self):
		for kp in self.conn.get_all_key_pairs():
			if kp.name==self.KEY_PAIR_NAME:
				self.key_pair = kp

		# have we got both the KP record and the .pem file? if so, we're fine
		if self.key_pair is not None and os.path.exists(self._key_path()):
			return self.key_pair
		
		# if not, delete broken half-KPs
		elif self.key_pair is not None:
			self.key_pair.delete()
		elif os.path.exists(self.KEY_PAIR_PATH):
			os.unlink(self.KEY_PAIR_PATH)

		self.key_pair = self.conn.create_key_pair(self.KEY_PAIR_NAME)
		self.key_pair.save(self.KEY_PAIR_PATH)
		
		return self.key_pair

	def enable_access(self):
		if self.security_group is None:
			self._get_or_create_security_group()
		self.security_group.authorize(ip_protocol='udp', from_port=1194, to_port=1194, cidr_ip='%s/32' % self.get_public_ip())

	def disable_access(self):
		if self.security_group is None:
			self._get_or_create_security_group()
		if self.public_ip is None:
			self.get_public_ip()
		self.security_group.revoke(ip_protocol='udp', from_port=1194, to_port=1194, cidr_ip='%s/32' % self.public_ip)

	def start(self):
		print 'Setting up key pair...'
		self.create_key_pair_if_necessary()
		
		print 'Configuring security rule...'
		self.enable_access()		

		print 'Launching instance...'
		self.reservation = self.conn.run_instances(self.REGIONS[self.region]['ami_id'], key_name=self.KEY_PAIR_NAME, instance_type=self.INSTANCE_SIZE, security_groups=[self.SECURITY_GROUP_NAME])
		instance = self.reservation.instances[0]
		
		print 'Waiting for instance...'
		while instance.state!='running':
			time.sleep(5)
			instance.update()
		
		print 'Instance is running.'
		self.instance_ip = instance.ip_address

		
	# def connect(self):
	# 	self.cmdshell = boto.manage.cmdshell.sshclient_from_instance(instance, self._key_path(), user_name=AMI_USER_NAME)

	def launch_tunnel_process(self):
		# openvpn process call
		openvpn_call = [
			'openvpn'
			'--client',
			'--dev tun',
			'--proto udp',
			'--remote %s 1194' % self.instance_ip,
			'--resolv-retry infinite',
			'--nobind',
			'--persist-key',
			'--persist-tun',
			'--ca ca.crt',
			'--cert client.crt',
			'--key client.key',
			'--comp-lzo',
			'--verb 3',
			'--cd %s/openvpn' % os.getcwd()
		]
		self.tunnel_process = subprocess.Popen(openvpn_call, stdout=subprocess.PIPE)
		self.tunnel_process_stdout = ''
		return self.tunnel_process

	def check_tunnel_status(self):				
		while True:
			print 'refreshing buffer'
			buf = self.tunnel_process.stdout.read()
			if len(buf)==0:
				break
			self.tunnel_process_stdout += buf

		# perform tests against buffer of output
		return self.tunnel_process_stdout

	def stop(self):
		self.disable_access()
		for reservation in self.conn.get_all_reservations():
			for instance in reservation.instances:
				if instance.image_id==self.REGIONS[self.region]['ami_id']:
					instance.terminate()

	REGIONS = {
		'us-east-1': {
			u'ami_id': u'ami-034c636a',
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
			u'ami_id': u'ami-fc2616b9',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.us-west-1.amazonaws.com',
			u'lat': u'41.48',
			u'lon': u'-120.53',
			u'name': u'US West (Northern California) Region',
			u'short_name': u'California'
		},
		'eu-west-1': {
			u'ami_id': u'',
			u'connection_type': u'HTTP and HTTPS',
			u'domain': u'ec2.eu-west-1.amazonaws.com',
			u'lat': u'53',
			u'lon': u'-8',
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

	AMI_USER_NAME = 'ec2-user'
	KEY_PAIR_NAME = 'wormhole-kp'
	SECURITY_GROUP_NAME = 'wormhole-sg'
	INSTANCE_SIZE = 't1.micro'
	KEY_PAIR_PATH = '.'
	SQLITE_DB = 'wormhole.db'




wh = None

def main():
	print 'Creating WH object...'
	wh = Wormhole()
	print 'Starting instance...'
	wh.start()
	print 'done.'

def cleanup():
	if wh is None:
		wh = Wormhole()
	print 'Stopping instance...'
	wh.stop()
	print 'done.'

if __name__ == '__main__':
	main()
	x = raw_input('Press <ENTER> to continue')
	cleanup()
	