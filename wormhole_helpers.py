import binascii
import os
from settings import * 

def credential_file_path():
    return '%s/%s' % (AWS_DIRECTORY, AWS_CREDENTIALS_FILE)

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
    if os.path.exists(credential_file_path()):
        f = open(credential_file_path(), 'r')
        j = f.read()
        f.close()
        return json.loads(j)
    else:
        return False
                    
def save_credentials(aws_access_key, aws_secret_key):
    f = open(credential_file_path(), 'w')
    json.dump((aws_access_key, aws_secret_key), f)
    f.close()

def generate_random_string(bits):
    return base64.b64encode(os.urandom(bits/8))[:-2]

