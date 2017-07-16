import gc

def previously_configured():
    try:
        import network_config
        del(network_config)
        return True
    except:
        return False

def connect_with_saved_credentials(min_timeout= 15000, max_timeout= 30000, max_rounds = 4):
    try:
        network_name = None
        network_psk = None
        ntp_success = False
        import network_config

        network_name = network_config.network_name
        network_psk = network_config.network_psk
        print("We've been provided network credentials, connecting for the first time.")
        del(network_config)
    except ImportError:
        # Credentials are only used first time to bootstrap, then they are deleted.
        print('Starting up with network config from flash.')

    try:
        import network
        ap = network.WLAN(network.AP_IF)
        ap.active(False)

        nic = network.WLAN(network.STA_IF)
        nic.active(True)
        if network_name and network_psk:
            nic.connect(network_name, network_psk)
    finally:
        del(network)

    timeout = min_timeout
    current_round = 1

    try:
        import utime
        while timeout <= max_timeout and not nic.isconnected():
            print('Waiting {} tics for the network'.format(timeout))
            start = utime.ticks_ms()
            while not nic.isconnected() and (utime.ticks_diff(start, utime.ticks_ms()) < timeout):
                utime.sleep(1)
            if not nic.isconnected():
                current_round = current_round + 1
                timeout = int((current_round / max_rounds) * max_timeout)
                if timeout < min_timeout: timeout = min_timeout
        else:
            if not nic.isconnected():
                nic.active(False)
                print('Max Timeout reached, disabling network')

        if nic.isconnected():
            try:
                import ntptime
                current_round = 1
                while not ntp_success and current_round < max_rounds:
                    try:
                        ntptime.settime()
                        ntp_success = True
                    except OSError:
                        utime.sleep(2)
                if not ntp_success:
                    print('ntp server unreachable')
            finally:
                del(ntptime)
    finally:
        del(utime)

    if nic.isconnected():
        # The network credentials are stored in the flash, so delete them from the filesystem to keep them safe
        with open('/network_config.py', 'w') as config_file:
            config_file.write('#REDACTED')

    gc.collect()
    return ntp_success

def request_credentials():
    import ubinascii
    import machine
    import network
    nic = network.WLAN(network.STA_IF)
    nic.active(False)
    ap = network.WLAN(network.AP_IF)
    ap.active(True)
    essid = b'DIRACK-%s' % ubinascii.hexlify(machine.unique_id()).upper()[:6:]
    ap.config(essid=essid, authmode=network.AUTH_WPA_WPA2_PSK, password=b'pozetron')
    del(ubinascii)
    del(machine)
    del(network)

    import web_server
    try:
        webserv = web_server.network_bootstrap_webserver(debug=True)
    except Exception as ex:
        print('Exception from webserver: {}'.format(ex))
        import os
        import utime
        try:
            os.remove('/network_config.py')
        except:
            pass
        finally:
            utime.sleep(1)
        del(utime)
        del(os)
        import sys
        sys.exit()
    finally:
        del(web_server)
        gc.collect()
