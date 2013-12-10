import boto.ec2, boto.manage.cmdshell
import os, time
from urllib import urlopen

AMI_ID = 'ami-64340421'
AMI_USER_NAME = 'root'
KEY_PAIR_NAME = 'wormhole-kp'
SECURITY_GROUP_NAME = 'wormhole-sg'
INSTANCE_SIZE = 't1.micro'
KEY_PAIR_PATH = '.'

class Wormhole(object):
	"""Creates EC2 instances for OpenVPN tunneling"""
	def __init__(self, region='us-west-1'):
		super(Wormhole, self).__init__()		
		self.conn = boto.ec2.connect_to_region(region, aws_access_key_id=os.getenv('AWS_ACCESS_KEY'), aws_secret_access_key=os.getenv('AWS_SECRET_KEY'))					
		self.security_group = None
		self.key_pair = None
		self.public_ip = None
		self.reservation = None

	def get_public_ip(self):
		self.public_ip = urlopen('http://bot.whatismyipaddress.com/').read().strip()
		return self.public_ip

	def _get_or_create_security_group(self):
		security_groups = self.conn.get_all_security_groups()
		for wormhole_sg in security_groups:			
			if wormhole_sg.name==SECURITY_GROUP_NAME:
				self.security_group = wormhole_sg
				return self.security_group

		if self.security_group is None:
			self.security_group = self.conn.create_security_group(SECURITY_GROUP_NAME, 'Wormhole VPN project')
			self.security_group.authorize(ip_protocol='tcp', from_port=22, to_port=22, cidr_ip='0.0.0.0/0')
			return self.security_group	

	def _key_path(self):
		return "%s/%s.pem" % (KEY_PAIR_PATH, KEY_PAIR_NAME)

	def create_key_pair_if_necessary(self):
		for kp in self.conn.get_all_key_pairs():
			if kp.name==KEY_PAIR_NAME:
				self.key_pair = kp

		# have we got both the KP record and the .pem file? if so, we're fine
		if self.key_pair is not None and os.path.exists(self._key_path()):
			return self.key_pair
		
		# if not, delete broken half-KPs
		elif self.key_pair is not None:
			self.key_pair.delete()
		elif os.path.exists(KEY_PAIR_PATH):
			os.unlink(KEY_PAIR_PATH)

		self.key_pair = self.conn.create_key_pair(KEY_PAIR_NAME)
		self.key_pair.save(KEY_PAIR_PATH)
		
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
		self.create_key_pair_if_necessary()
		self.enable_access()		
		self.reservation = self.conn.run_instances(AMI_ID, key_name=KEY_PAIR_NAME, instance_type=INSTANCE_SIZE, security_groups=[SECURITY_GROUP_NAME])

	def connect(self):
		instance = self.reservation.instances[0]
		print 'Waiting for instance...'
		while instance.state!='running':
			time.sleep(5)
			instance.update()
		print 'Instance is running.'
		self.instance_ip = instance.ip_address
		self.cmdshell = boto.manage.cmdshell.sshclient_from_instance(instance, self._key_path(), user_name=AMI_USER_NAME)

	def stop(self):
		self.disable_access()
		for reservation in self.conn.get_all_reservations():
			for instance in reservation.instances:
				if instance.image_id==AMI_ID:
					instance.terminate()

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
	