import os, json, time, sys
# import web
import wormhole
import memcache
from threading import Thread, Event
from settings import *

from flask import Flask, make_response, render_template, request, redirect, url_for
app = Flask(__name__)


@app.route('/launch', methods=['GET', 'POST'])
def launch():
    if request.method=='GET':
        region = wormhole.Wormhole.REGIONS.get(load_region(), {}).get('short_name', False)
        mc = memcache.Client([MEMCACHE_SERVER], debug=0)
        open_tunnel = mc.get('tunnel-open')             
        return render_template('launch.html', open_tunnel=open_tunnel, region=region)

    elif request.method=='POST':
        form = web.input(activate=-1)      
        mc = memcache.Client([MEMCACHE_SERVER], debug=0)        
        open_tunnel = mc.get('tunnel-open') 
        j = ''
        if int(form.activate)==1:   
            if not open_tunnel:
                print 'attempting to open tunnel'
                try:    
                    mc.set('deactivate', False)   

                    # TODO: change this to use the multiprocess module

                    t = Thread(target=open_wormhole)
                    t.daemon = True # thread dies with the program
                    t.start()
                    j = json.dumps({'result': 'starting'})
                except Exception, e:
                    j = json.dumps({'result': 'error'})
                    raise e
            else:
                j = json.dumps({'result': 'already open'})
        elif int(form.activate)==0:            
            if open_tunnel:
                mc.set('deactivate', True)
                j = json.dumps({'result': 'stopping'})
            else:
                j = json.dumps({'result': 'already closed'})
        resp = make_response(j, 200)
        resp.headers['Content-Type'] = 'application/json'
        return resp

@app.route('/settings', methods=['GET', 'POST'])
def settings():
    if request.method=='GET':
        credentials = load_credentials()
        if not credentials:
            valid_credentials = False
        else:
            region = wormhole.get_valid_regions().items()[0][0]
            wh = wormhole.Wormhole(region, credentials[0], credentials[1], AWS_DIRECTORY)
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

        return render_template('settings.html', valid_credentials=valid_credentials, valid_regions=valid_regions, current_region=current_region)

    elif request.method=='POST':
        if request.form.get('access_key','')=='DELETE' and request.form.get('secret_key','')=='DELETE':
            os.unlink(credential_file_path())
        elif not '' in (request.form.get('access_key',''), request.form.get('secret_key','')):
            save_credentials(request.form.get('access_key'), request.form.get('secret_key'))        
        save_region(request.form.get('region'))     
        return redirect(url_for('settings'))

@app.route('/ajax/validate', methods=['POST'])
def ajax_validate():
    if request.method=='POST':    
        region = wormhole.get_valid_regions().items()[0][0]        
        wh = wormhole.Wormhole(region, request.form.get('access_key'), request.form.get('secret_key'), AWS_DIRECTORY)
        resp = make_response(json.dumps({'success': wh.validate_credentials()}), 200)
        resp.headers['Content-Type'] = 'application/json'
        return resp

@app.route('/ajax/launch-status')
def ajax_launch_status():
    if request.method=='GET':
        web.header('Content-Type', 'application/json')
        mc = memcache.Client([MEMCACHE_SERVER], debug=0)
        status = mc.get('status')
        j = ''
        if not status:
            j = json.dumps({})
        else:
            j = json.dumps(status)
        resp = make_response(json.dumps(j), 200)
        resp.headers['Content-Type'] = 'application/json'
        return resp


@app.route('/status')
def status():
    if request.method=='GET':
        return render_template('status.html')

@app.route('/about')
def about():
    if request.method=='GET':
        return render_template('about.html')

def update_status(mc, code, result):
    status = mc.get('status')
    if not status:
        status = {}
    status[code] = result
    mc.set('status', status)

def open_wormhole():

    def deactivation_signal_detected():
        global mc, region, credentials, wh

        deactivation_signal = mc.get('deactivate')
        if deactivation_signal:
            return True
        else:
            return False

    def do_settings():
        global mc, region, credentials, wh

        region = load_region()
        if not region or len(wormhole.Wormhole.REGIONS.get(region, {}).get('ami_id',''))==0:
            raise Exception('No valid region found')
        
        credentials = load_credentials()
        if not credentials:
            raise Exception('No stored credentials found')

        wh = wormhole.Wormhole(region, credentials[0], credentials[1], AWS_DIRECTORY)
        if not wh.validate_credentials():
            raise Exception('No valid credentials found')

    def do_orphans():
        global mc, region, credentials, wh
        wh.stop_all_global_instances()

    def do_instance():
        global mc, region, credentials, wh
        wh.start_instance()
        mc.set('instance-id', wh.instance.id)

    def do_boot():
        time.sleep(5)

    def do_openvpn():
        global mc, region, credentials, wh
        wh.start_openvpn()
        while wh.check_tunnel_status()=='working':
            time.sleep(0.25)
        if wh.check_tunnel_status()=='error':
            raise Exception('Error opening OpenVPN tunnel: %s' % (wh.tunnel_process_stdout,))

    def do_routing():
        global mc, region, credentials, wh
        wh.start_routing()

    def stop_routing():
        global mc, region, credentials, wh
        wh.stop_routing()

    def stop_openvpn():
        global mc, region, credentials, wh
        wh.stop_openvpn()

    def stop_boot():
        pass

    def stop_instance():
        global mc, region, credentials, wh
        wh.stop_instance()

    def stop_orphans():
        pass

    def stop_settings():
        pass

    global mc, region, credentials, wh
    mc = memcache.Client([MEMCACHE_SERVER], debug=0)
    mc.set('status', [])
    region = None
    credentials = None
    wh = None

    steps = ['settings', 'orphans', 'instance', 'boot', 'openvpn', 'routing']
    for step in steps:
        update_status(mc, step, 'working')
        operation_func = locals().get('do_%s' % step)
        try:
            operation_func()
        except Exception, e:
            update_status(mc, step, 'error')
            raise e
        update_status(mc, step, 'ok')

        # check on the process being cancelled
        if deactivation_signal_detected():
            # TODO: tear down any half-started processes?
            mc.set('status', [])
            return True
    
    mc.set('tunnel-open', True)

    # wait for deactivation signal
    while not deactivation_signal_detected():        
        time.sleep(0.25)

    # now reverse the procedure
    for step in reversed(steps):
        update_status(mc, step, 'working')
        operation_func = locals().get('stop_%s' % step)
        try:
            operation_func()
        except Exception, e:
            update_status(mc, step, 'error')
            raise e
        update_status(mc, step, 'pending')

    mc.set('tunnel-open', False)


if __name__ == "__main__":    
    app.run(host='0.0.0.0', debug=('--debug' in sys.argv))