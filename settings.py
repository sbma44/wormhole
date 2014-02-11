import os, json

AWS_DIRECTORY = '/home/pi/Devel/wormhole/aws'
AWS_CREDENTIALS_FILE = 'aws_credentials.json'
REGION_FILE = 'aws_region.json'
MEMCACHE_SERVER = '127.0.0.1:11211'

def load_region():
    if os.path.exists('%s/%s' % (AWS_DIRECTORY, REGION_FILE)):
        return json.load(open('%s/%s' % (AWS_DIRECTORY, REGION_FILE)))
    else:
        return False
    
def save_region(region):
    f = open('%s/%s' % (AWS_DIRECTORY, REGION_FILE), 'w')
    json.dump(region, f)
    f.close()

def load_credentials():
    if os.path.exists('%s/%s' % (AWS_DIRECTORY, AWS_CREDENTIALS_FILE)):
        f = open('%s/%s' % (AWS_DIRECTORY, AWS_CREDENTIALS_FILE), 'r')
        j = f.read()
        f.close()
        return json.loads(j)
    else:
        return False
                    
def save_credentials(aws_access_key, aws_secret_key):
    f = open('%s/%s' % (AWS_DIRECTORY, AWS_CREDENTIALS_FILE), 'w')
    json.dump((aws_access_key, aws_secret_key), f)
    f.close()

try:
    from local_settings import *
except Exception, e:
    pass