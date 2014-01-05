# Find orphaned or ready-to-expire EC2 instances and shut them down.
# This file should be run on a regular cron

import wormhole
import time

def scavenge():
	(aws_access_key, aws_secret_key) = load_credentials()

	# iterate through every region
	for (region_id, region_values) in wormhole.Wormhole.REGIONS.items():
			
		# only process regions for which a Wormhole AMI is available
		ami_id = region_values.get('ami_id', '')
		if len(ami_id)==0:
			continue

		wh = wormhole.Wormhole(region_id, aws_access_key, aws_secret_key)
		for instance in wh.conn.get_only_instances():

			# if the instance has an expiration flag, make sure
			# we don't terminate it prematurely
			if instance.tags.has_key('wormhole-expire'):						
				expiration = int(instance.tags.get('wormhole-expire', 0))
				if time.time()<expiration:
					continue

			# ensure that we only shut down instances created by
			# this machine, and which are wormhole AMIs
			system_id = instance.tags.get('wormhole-system-id')
			if system_id==wh.system_id and instance.image_id==ami_id:
				instance.terminate()

if __name__ == '__main__':
	scavenge()