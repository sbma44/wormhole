#!/home/pi/.virtualenvs/wormhole/bin/python

import os, json, time, sys
import wormhole
import memcache
from threading import Thread, Event
from settings import *

from flask import Flask, make_response, render_template, request, redirect, url_for, jsonify
app = Flask(__name__)

def get_mc():
    return memcache.Client([MEMCACHE_SERVER], debug=0)

DEACTIVATION_SIGNAL_KEY = 'wormhole-deactivate'
WORMHOLE_INSTANCE_ID = 'wormhole-instance-id'
WORMHOLE_EXPIRATION_KEY = 'wormhole-expiration-key'

@app.route('/', methods=['GET'])
def default():
    credentials = load_credentials()
    if not credentials:
        return redirect(url_for('settings'))
    else:
        return redirect(url_for('launch'))

@app.route('/launch', methods=['GET', 'POST'])
def launch():
    if request.method=='GET':
        region = wormhole.Wormhole.REGIONS.get(load_region(), {}).get('short_name', False)
        mc = get_mc()
        open_tunnel = mc.get('tunnel-open')             
        return render_template('launch.html', open_tunnel=open_tunnel, region=region)

    elif request.method=='POST':
        mc = get_mc()
        open_tunnel = mc.get('tunnel-open') 
        j = ''
        activate_val = int(request.form.get('activate',-1))
        if activate_val==1:   
            if not open_tunnel:
                print 'attempting to open tunnel'
                try:    
                    mc.delete(DEACTIVATION_SIGNAL_KEY)

                    # TODO: change this to use the multiprocess module
                    expire = int(request.form.get('expire',0))
                    if expire>0:
                        expire = expire + int(time.time())
                    t = Thread(target=open_wormhole, args=(expire,))
                    t.daemon = True # thread dies with the program
                    t.start()
                    j = {'result': 'starting'}
                except Exception, e:
                    j = {'result': 'error'}
                    raise e
            else:
                j = {'result': 'already open'}
        elif activate_val==0:            
            if open_tunnel:
                mc.set(DEACTIVATION_SIGNAL_KEY, True)
                j = {'result': 'stopping'}
            else:
                j = {'result': 'already closed'}

	return jsonify(**j)

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
	return jsonify(success=wh.validate_credentials())

@app.route('/ajax/launch-status')
def ajax_launch_status():
    if request.method=='GET':        
        mc = get_mc()
        status = mc.get('status')
        if not status:
            status = {}
        return jsonify(**status)

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

def open_wormhole(expire=0):

    def deactivation_signal_detected():
        global mc, region, credentials, wh

        deactivation_signal = mc.get(DEACTIVATION_SIGNAL_KEY)
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
        global mc, region, credentials, wh, wh_expire
        wh.start_instance(tags={'wormhole_expire': wh_expire})
        mc.set(WORMHOLE_INSTANCE_ID, wh.instance.id)

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
        mc.delete(WORMHOLE_INSTANCE_ID)

    def stop_orphans():
        pass

    def stop_settings():
        pass

    global mc, region, credentials, wh, wh_expire
    mc = get_mc()
    mc.set('status', [])
    mc.delete(WORMHOLE_INSTANCE_ID)
    region = None
    credentials = None
    wh = None
    wh_expire = expire

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
    if os.getuid()!=0:
        raise Exception('This script must be run as root')

    app.run('0.0.0.0')
