#!/home/pi/.virtualenvs/wormhole/bin/python

# Find orphaned or ready-to-expire EC2 instances and shut them down.
# This file should be run on a regular cron

import time
from settings import *
import wormhole
from wormhole_web import get_mc, DEACTIVATION_SIGNAL_KEY, WORMHOLE_EXPIRATION_KEY, WORMHOLE_INSTANCE_ID

def scavenge():
	# check for active tunnel & shut down, if necessary
	# can't just rely on the other system, because local 
	# routing won't be reset that way
	mc = get_mc()	
	instance_id = mc.get(WORMHOLE_INSTANCE_ID)
	if instance_id: # is there an active instance?
		
		expire = mc.get(WORMHOLE_EXPIRATION_KEY)
		if expire:
			if expire>0 and expire<time.time(): # are we past expiration?
				mc.set(DEACTIVATION_SIGNAL_KEY, True) # SHUT IT DOOOOWN

	# okay, now go through and kill the other instances
	credentials = load_credentials()
	if not credentials:
		raise Exception('No valid credentials found.')
	
	aws_access_key = credentials[0]
	aws_secret_key = credentials[1]

	# iterate through every region
	for (region_id, region_values) in wormhole.Wormhole.REGIONS.items():
			
		# only process regions for which a Wormhole AMI is available
		ami_id = region_values.get('ami_id', '')
		if len(ami_id)==0:
			continue

		wh = wormhole.Wormhole(region_id, aws_access_key, aws_secret_key, AWS_DIRECTORY)
		for instance in wh.conn.get_only_instances():

			# if the instance has an expiration flag, make sure
			# we don't terminate it prematurely
			if instance.tags.has_key('wormhole-expire'):						
				expiration = int(instance.tags.get('wormhole-expire', -1))
				if expiration>0:
					if time.time()<expiration:
						continue

			# ensure that we only shut down instances created by
			# this machine, and which are wormhole AMIs
			system_id = instance.tags.get('wormhole-system-id')
			if system_id==wh.system_id and instance.image_id==ami_id:
				instance.terminate()

if __name__ == '__main__':
	scavenge()
