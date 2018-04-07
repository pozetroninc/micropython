##############################
#    Setup board after initial power on     #
##############################
import gc

# There is a ESP8266 quirk where the first reset after flashing requires a full powercycle.
# https://github.com/esp8266/Arduino/issues/1017
# https://github.com/esp8266/Arduino/issues/1722#issuecomment-289129671


try:
    ntp_success = False

    from bootstrap_network import previously_configured, connect_with_saved_credentials, request_credentials

    if previously_configured():
        ntp_success = connect_with_saved_credentials()
    else:
        request_credentials()
        ntp_success = connect_with_saved_credentials()

    del(previously_configured)
    del(connect_with_saved_credentials)
    del(request_credentials)
except:
    print('Network bootstrap failed')
finally:
    gc.collect()


###############################################
#     Perform pozetron setup actions after network acquired       #
###############################################
debug = True

# Set up logging
try:
    from logger import log
    import builtins
    builtins.log = log
    del(builtins)
    del(log)
except:
    print('Error setting up logging')


###############################################
#                   Setup necessary Pozetron functionality                       #
###############################################

# The following adds the scripts path so that MicroPython can easily import user scripts
try:
    from sys import path
    from pozetron_config import SCRIPTS_DIR
    path.insert(0, SCRIPTS_DIR[:-1:])
    del(path, SCRIPTS_DIR)
    gc.collect()

except:
    log('Error setting up the scripts directory')

# Everything below this line stays resident during the devices uptime
import pozetron
try:
    pozetron.check_commands()
    gc.collect()
except:
    log('Error checking commands on boot')


# The following will update the device with all the scripts assigned to it
try:
    pozetron.refresh_scripts()
    gc.collect()
except:
    log('Error refreshing scripts on boot')

del pozetron
gc.collect()

###############################################
#              Initialize all of the user supplied variables                       #
###############################################
try:
    log('Device rebooted')
    from main import main_loop
except Exception as ex:
    log('Error importing main: {}'.format(ex))
    from machine import idle as main_loop

while True:

###############################################
#                Start the user provided main.main_loop                        #
###############################################

    # Main Event Loop
    try:
        main_loop()
    except Exception as ex:
        gc.collect()
        log('Error in main_loop: {}'.format(ex))
        from pozetron import flush_logs
        flush_logs()
        del flush_logs
    finally:
        gc.collect()

###############################################
#                            Start the pozetron epilog                                       #
###############################################

    import pozetron
    try:
        pozetron.epilog()
    except Exception as ex:
        log('Pozetron epilog failed with {}'.format(ex))
    finally:
        # This decision to flush the logs every time is a trade off to provide quicker access to the logs
        # at the expense of more cycles spent on housekeeping tasks.
        pozetron.flush_logs()
        del pozetron
        gc.collect()
