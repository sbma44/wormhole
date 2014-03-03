import os, json
from wormhole_helpers import * 

AWS_DIRECTORY = '/home/pi/Devel/wormhole/aws'
AWS_CREDENTIALS_FILE = 'aws_credentials.json'
REGION_FILE = 'aws_region.json'
MEMCACHE_SERVER = '127.0.0.1:11211'

try:
    from local_settings import *
except Exception, e:
    pass