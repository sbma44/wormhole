import os, json, time
import web
import wormhole
import memcache
from threading import Thread, Event
from settings import *

urls = (
    '/settings', 'settings',    
    '/', 'status',
    '/ajax/validate', 'ajax_validate',
    '/ajax/launch-status', 'ajax_launch_status',
    '/launch', 'launch',
    '/about', 'about'
)

def make_menu(path):
    render = web.template.render('html')
    return render.menu(path)

class launch:
    def GET(self):
        web.header('Content-Type', 'text/html')     
        render = web.template.render('html', globals={'make_menu': make_menu})
        region = wormhole.Wormhole.REGIONS.get(load_region(), {}).get('short_name', False)
        mc = memcache.Client([MEMCACHE_SERVER], debug=0)
        open_tunnel = mc.get('tunnel-open')     
        return render.launch(open_tunnel, region)

    def POST(self):
        web.header('Content-Type', 'application/json')      
        form = web.input(activate=0, deactivate=0)      
        mc = memcache.Client([MEMCACHE_SERVER], debug=0)        
        open_tunnel = mc.get('tunnel-open') 
        print 'tunnel is open? %s' % open_tunnel
        if int(form.activate)==1:   
            if not open_tunnel:
                print 'attempting to open tunnel'
                try:    
                    mc.set('deactivate', False)             
                    t = Thread(target=open_wormhole)
                    t.daemon = True # thread dies with the program
                    t.start()
                    return json.dumps({'result': 'starting'})
                except Exception, e:
                    return json.dumps({'result': 'error'})
                    raise e
            else:
                return json.dumps({'result': 'already open'})
        elif int(form.deactivate)==1:            
            if open_tunnel:
                mc.set('deactivate', True)
                return json.dumps({'result': 'stopping'})
            else:
                return json.dumps({'result': 'already closed'})


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

        render = web.template.render('html', globals={'make_menu': make_menu})
        return render.settings(valid_credentials, valid_regions, current_region)

    def POST(self):
        form_values = web.input(access_key='', secret_key='')        
        if form_values.access_key=='DELETE' and form_values.secret_key=='DELETE':
            os.unlink(AWS_CREDENTIALS_FILE)
        elif not '' in (form_values.access_key, form_values.secret_key):
            save_credentials(form_values.access_key, form_values.secret_key)        
            save_region(form_values.region)     
        raise web.seeother('/settings')

class ajax_validate(object):
    def POST(self):
        web.header('Content-Type', 'application/json')
        region = wormhole.get_valid_regions().items()[0][0]
        form_values = web.input()
        wh = wormhole.Wormhole(region, form_values.access_key, form_values.secret_key)
        return json.dumps({'success': wh.validate_credentials()})

class ajax_launch_status(object):
    def GET(self):
        web.header('Content-Type', 'application/json')
        mc = memcache.Client([MEMCACHE_SERVER], debug=0)
        status = mc.get('status')
        if not status:
            return json.dumps({})
        else:
            return json.dumps(status)

class status(object):
    def GET(self):
        web.header('Content-Type', 'text/html')     
        render = web.template.render('html', globals={'make_menu': make_menu})
        return render.status()


class about(object):
    def GET(self):
        web.header('Content-Type', 'text/html')     
        render = web.template.render('html', globals={'make_menu': make_menu})
        return render.about()

def update_status(mc, code, result):
    status = mc.get('status')
    if not status:
        status = {}
    status[code] = result
    mc.set('status', status)

def open_wormhole():
    mc = memcache.Client([MEMCACHE_SERVER], debug=0)
    mc.set('status', [])

    # check settings
    update_status(mc, 'settings', 'working')
    try:
        region = load_region()
        if not region or len(wormhole.Wormhole.REGIONS.get(region, {}).get('ami_id',''))==0:
            raise Exception('No valid region found')
        
        credentials = load_credentials()
        if not credentials:
            raise Exception('No stored credentials found')

        wh = wormhole.Wormhole(region, credentials[0], credentials[1])
        if not wh.validate_credentials():
            raise Exception('No valid credentials found')
    except Exception, e:
        update_status(mc, 'settings', 'error')
        raise e
    update_status(mc, 'settings', 'ok')

    
    # stop all other instances
    update_status(mc, 'orphans', 'working')
    try:
        wh.stop_all_global_instances()
    except Exception, e:
        update_status(mc, 'orphans', 'error')
        raise e
    update_status(mc, 'orphans', 'ok')

    # launch instance
    update_status(mc, 'instance', 'working')
    try:
        wh.start_instance()
    except Exception, e:
        update_status(mc, 'instance', 'error')
        raise e
    update_status(mc, 'instance', 'ok')
    mc.set('instance-id', wh.instance.id)

    # wait for instance
    update_status(mc, 'booted', 'working')
    time.sleep(5)
    update_status(mc, 'booted', 'ok')

    # launch openvpn
    update_status(mc, 'openvpn', 'working')
    try:
        wh.start_openvpn()
        while wh.check_tunnel_status()=='working':
            time.sleep(0.25)
        if wh.check_tunnel_status()=='error':
            update_status(mc, 'openvpn', 'error')       
    except Exception, e:
        update_status(mc, 'openvpn', 'error')
        # print wh.tunnel_process_stdout
        raise e
    update_status(mc, 'openvpn', 'ok')

    # set up routing
    update_status(mc, 'routing', 'working')
    try:
        wh.start_routing()      
    except Exception, e:
        update_status(mc, 'routing', 'error')
        raise e
    update_status(mc, 'routing', 'ok')
    
    mc.set('tunnel-open', True)

    # wait for deactivation signal
    while True:
        deactivation_signal = mc.get('deactivate')
        if deactivation_signal:
            break
        time.sleep(0.25)

    # now reverse the procedure

    # stop routing
    update_status(mc, 'routing', 'working')
    try:
        wh.stop_routing()      
    except Exception, e:
        update_status(mc, 'routing', 'error')
        raise e
    update_status(mc, 'routing', 'pending')

    # stop openvpn
    update_status(mc, 'openvpn', 'working')
    try:
        wh.stop_openvpn()            
    except Exception, e:
        update_status(mc, 'openvpn', 'error')
        raise e
    update_status(mc, 'openvpn', 'pending')

    # booted is sort of a non-entry
    update_status(mc, 'booted', 'pending')

    # stop instance
    update_status(mc, 'instance', 'working')
    try:
        wh.stop_instance()
    except Exception, e:
        update_status(mc, 'instance', 'error')
        raise e
    update_status(mc, 'instance', 'pending')

    # settings and orphans are also unimportant
    update_status(mc, 'orphans', 'pending')
    update_status(mc, 'settings', 'pending')

    mc.set('tunnel-open', False)


if __name__ == "__main__":
    app = web.application(urls, globals())
    app.run()