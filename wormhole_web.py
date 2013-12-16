import os, json
import web
import wormhole

AWS_CREDENTIALS_FILE = 'aws_credentials.json'
REGION_FILE = 'aws_region.json'

urls = (
    '/settings', 'settings',    
    '/', 'status',
    '/ajax/validate', 'ajax_validate',
    # '/location', 'location',
    '/launch', 'launch',
    # '/about', 'about'
)

class launch:
    def GET(self):
    	web.header('Content-Type', 'text/html')    	
    	render = web.template.render('html')
    	return render.launch()

class settings(object):
    def GET(self):
    	web.header('Content-Type', 'text/html')

    	credentials = load_credentials()
    	if not credentials:
    		valid_credentials = False
    	else:
    		region = wormhole.get_valid_regions().items()[0][0]
    		wh = wormhole.Wormhole(region, credentials[0], credentials[1])
    		valid_credentials = wh.validate_credentials()

    	if valid_credentials:
    		valid_credentials = 0
    	else:
    		valid_credentials = 1

    	valid_region_list = wormhole.get_valid_regions()
    	valid_regions = []
    	for vr in valid_region_list.items():
    		valid_regions.append((vr[0], vr[1]['name']))

    	current_region = load_region()

    	render = web.template.render('html')
    	return render.settings(valid_credentials, valid_regions, current_region)

    def POST(self):
		form_values = web.input(access_key='', secret_key='')
		save_region(form_values.region)		
		if not '' in (form_values.access_key, form_values.secret_key):
			save_credentials(form_values.access_key, form_values.secret_key)
		if form_values.access_key=='DELETE' and form_values.secret_key=='DELETE':
			os.unlink(AWS_CREDENTIALS_FILE)
		raise web.seeother('/settings')

class ajax_validate(object):
	def POST(self):
		web.header('Content-Type', 'application/json')
		region = wormhole.get_valid_regions().items()[0][0]
		form_values = web.input()
		wh = wormhole.Wormhole(region, form_values.access_key, form_values.secret_key)
		return json.dumps({'success': wh.validate_credentials()})

class start(object):
	def GET(self):
		pass

def load_region():
	if os.path.exists(REGION_FILE):
		return json.load(open(REGION_FILE))
	else:
		return False
	
def save_region(region):
	f = open(REGION_FILE, 'w')
	json.dump(region, f)
	f.close()

def load_credentials():
	if os.path.exists(AWS_CREDENTIALS_FILE):
		return json.load(open(AWS_CREDENTIALS_FILE))
	else:
		return False
					
def save_credentials(aws_access_key, aws_secret_key):
	f = open(AWS_CREDENTIALS_FILE, 'w')
	json.dump((aws_access_key, aws_secret_key), f)
	f.close()

if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()