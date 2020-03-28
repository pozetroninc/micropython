import gc
import os
import sys
import utime

from uhttp_signature.authed_urequests import make_validated_request, RequestError, SignatureException

from pozetron_config import *
from credentials import KEY_ID, HMAC_SECRET
from logger import log, exc_logline

if isinstance(KEY_ID, bytes):
    KEY_ID = KEY_ID.decode('utf-8')

debug = False

# Module name for references
pozetron = sys.modules[__name__]

# Was POST checkin successful?
# See also post_checkin
_on_startup_checkin_done = False
last_refreshed_scripts = None
last_checked_commands = None
forget_network_time = None

# Some commands must be executed before others (when processed as a batch)
COMMAND_ORDER = {
    'log_mode': 0,
    'forget_network': 1,
    'reboot': 2
}

one_second = const(1000)
one_minute = const(60000)
five_minutes = const(300000)
one_day = const(24*60*60*1000)




def epilog():
    # We're trying to be cooperative here.
    utime.sleep_ms(0)
    now = utime.ticks_ms()

    # In the case of an signature error (client or server) try update the system time in
    # case the clock has skewed significantly
    for attempt in range(3):
        try:
            # Check commands before refreshing scripts so reboot remains a viable failsafe
            if utime.ticks_diff(now, pozetron.last_checked_commands) > one_minute or pozetron.last_checked_commands is None:
                try:
                    check_commands()
                    pozetron.last_checked_commands = now
                    flush_logs()
                except SignatureException as ex:
                    raise ex
                except RequestError:
                    pass

            if utime.ticks_diff(now, pozetron.last_refreshed_scripts) > one_minute or pozetron.last_refreshed_scripts is None:
                try:
                    refresh_scripts()
                    pozetron.last_refreshed_scripts = now
                    flush_logs()
                except SignatureException as ex:
                    raise ex
                except RequestError:
                    pass
        except SignatureException:
            # Try to set the time through NTP, but not too hard
            try:
                import ntptime
                ntptime.settime()
            except:
                pass
            finally:
                ntptime = None
                del(ntptime)
        else:
            break


# Wrapper for make_validated_request, for brevity
def request(url, **kw):
    result = make_validated_request(url, KEY_ID, HMAC_SECRET, debug=debug, **kw)
    # Successful request -> we can disable backoff
    reset_backoff()
    return result


# We must write "Failure sending logs..." message only once
# until the next flush_logs success
_logs_lost = False


# This function does not raise
def flush_logs():
    global _logs_lost
    import logger
    url = API_BASE + '/logs/'
    try:
        if should_backoff():
            return

        # If log is empty, then we don't have to flush anything
        if not logger.file_size:
            logs = logger._logs
            if len(logs) == 0:
                return
        else:
            try:
                if os.stat(logger._LOG_FILE)[6] == 0:  # size == 0
                    return
            except OSError:  # No file = no logs = no problem
                return
        # Post logs to API
        try:
            try:
                # NOTE: when API is available again after failure, this will not execute
                # if log is empty, until some other message is logged.
                if _logs_lost:
                    request(url, method='POST', json=[{'text': 'Failure sending logs, truncated logs have been lost'}])
                    _logs_lost = False
                # TODO: In the future, find a way to compute the HMAC on the file rather piece by piece than after
                # loading the list to memory.
                if not logger.file_size:
                    json = [{'text': x} for x in logger._logs]
                    if logger._overflow_errors:
                        json.append({'text': '{} failed writes to log file due to logger.file_size={}'.format(logger._overflow_errors, logger.file_size)})
                    request(url, method='POST', json=json)
                    del json
                else:
                    # If there are overflow errors we send them separately to make sure they get there.
                    if logger._overflow_errors:
                        json = [{'text': '{} failed writes to log file due to logger.file_size={}'.format(logger._overflow_errors, logger.file_size)}]
                        request(url, method='POST', json=json)
                        del json
                        logger._overflow_errors = 0
                    # If there were no overflow errors we just send the log file.
                    request(url, method='POST', in_file=logger._LOG_FILE)
                # Success - clear logs
                logger._overflow_errors = 0
                logger._send_fails = 0
                if not logger.file_size:
                    logger._logs.clear()
                else:
                    _truncate_file(logger._LOG_FILE)
            except RequestError as ex:
                # NOTE: API will accept logs even if they are corrupted
                print(ex)
                set_backoff()
                raise ex
            #finally:
                # Delete variable
                # The follow call to del causes:
                # MemoryError: memory allocation failed, allocating 1073672184 bytes
                #del logs
        except Exception as ex:
            log(exc_logline.format('send logs', ex))
            logger._send_fails += 1
        # If too many fails, reset log
        if logger._send_fails >= 3:
            clear_logs()
            _logs_lost = True
    except Exception as o:
        sys.print_exception(o)
    finally:
        del url
        del logger


# No truncate() so we use a workaround.
# Don't physically write if file is already empty, to save flash.
def _truncate_file(filename):
    try:
        if os.stat(filename)[6] > 0:
            with open(filename, 'w'):
                pass
    except OSError:
        pass


def clear_logs():
    import logger
    logger._overflow_errors = 0
    logger._send_fails = 0
    logger._logs.clear()
    _truncate_file(logger._LOG_FILE)
    del logger


# Exponential backoff: don't do requests to API for some time,
# increasing that time after every subsequent failure.
_backoff_until = None
_backoff_factor = 0
_backoff_factor_max = 7  # max wait depends on this and on timeout below
_backoff_timeout_ms = const(10000)  # max wait is about 20 minutes


def set_backoff(timeout=None):
    global _backoff_until, _backoff_factor
    if not timeout:
        # We randomize backoff period by 25% to avoid "thundering herd" problem
        import urandom
        timeout = (_backoff_timeout_ms * 2**_backoff_factor) * (1024 + (256 - urandom.getrandbits(9))) // 1024
        del urandom
        # Increase backoff factor
        _backoff_factor = min(_backoff_factor + 1, _backoff_factor_max)
    # next try at (now + timeout)
    _backoff_until = utime.ticks_add(utime.ticks_ms(), timeout)


# Return True if backoff is in effect and we should come later
def should_backoff():
    global _backoff_until
    if _backoff_until is None:
        return False
    diff = utime.ticks_diff(_backoff_until, utime.ticks_ms())
    # Check for wrap around
    if not (-one_day < diff < one_day):
        diff = 0
    # Are we still waiting?
    if diff > 0:
        return True
    # Reset wait, but don't reset factor. Factor is reset on first successful request.
    _backoff_until = None
    return False


# Reset back-off mechanism after successful request.
def reset_backoff():
    global _backoff_factor
    _backoff_factor = 0


def makesubdir(path, subdir):
    # Replacement for os.makedirs
    if path[-1] != '/':
        path += '/'
    items = subdir.strip('/').split('/')
    for x in items:
        path += x + '/'
        try:
            os.mkdir(path)
        except OSError:
            pass
    del x, items


def autocollect(function):
    def autocollect_decorator(*args, **kwargs):
        try:
            return function(*args, **kwargs)
        finally:
            gc.collect()
    return autocollect_decorator


def post_checkin():
    # Returns True if checkin is successful, False otherwise.
    global _on_startup_checkin_done
    if should_backoff():
        return False
    try:
        request(API_BASE + '/checkin/', method='POST', data=' ')
    except RequestError as ex:
        print(exc_logline.format('post checkin', ex))
        set_backoff()
        return False
    _on_startup_checkin_done = True
    return True


@autocollect
def on_startup():
    # This function MUST be called once on device startup.
    post_checkin()
    #log('on_startup completed')


def _reboot():
    log('Rebooting')
    flush_logs()
    import machine
    machine.reset()


@autocollect
def check_commands(debug=pozetron.debug):
    # Get list of commands from server and execute them.
    global _on_startup_checkin_done, forget_network_time
    if not _on_startup_checkin_done:
        if not post_checkin():
            return
    if should_backoff():
        return
    try:
        commands = request(API_BASE + '/checkin/')
    # Because SignatureException is a type of RequestError we have to
    # catch it here and raise it explicitly.
    except SignatureException as ex:
        raise ex
    except RequestError as ex:
        print(ex)
        set_backoff()
        return
    commands = commands.json()
    import logger
    try:
        # Commands must be executed in a particular order
        if len(commands) > 1:
            commands.sort(key=lambda x: COMMAND_ORDER.get(x['type'], 0))
        for command in commands:
            # set error=<str> and it will be reported to server
            error = ''
            if command['type'] == 'log_mode':
                # Log enable/disable
                old_send_logs = logger._send_logs
                logger._send_logs = command['data']['enable']
                # If being disabled, flush remaining lines
                if old_send_logs and not logger._send_logs:
                    flush_logs()
                # Change log mode
                new_size = None
                if command['data'].get('mode') == 'memory':
                    new_size = 0
                elif command['data'].get('mode') == 'file' and 'file_size' in command['data']:
                    new_size = command['data']['file_size']
                if new_size is not None and new_size != logger.file_size:
                    # Flush unconditionally, to keep it simple.
                    flush_logs()
                    # Flush failed? Force clear.
                    # (this is not relevant if mode is still "file")
                    if logger._send_fails and (logger.file_size == 0 or new_size == 0):  # memory <-> file
                        clear_logs()
                        logger.file_size = new_size  # so that following line goes to new destination
                        global _logs_lost
                        _logs_lost = True
                logger.file_size = new_size
                del new_size
                if logger._send_logs != old_send_logs:
                    log('Log mode enabled' if logger._send_logs else 'Log mode disabled')
                # Save log mode to file, to be used on next reboot
                _save_log_mode()
            elif command['type'] == 'reboot':
                # Make sure there is 1 second delay between forget-network and reboot
                if forget_network_time is not None:
                    utime.sleep_ms(one_second - utime.ticks_diff(utime.ticks_ms(), forget_network_time))
                _reboot()
                continue  # reboot is special, we send confirmation AFTER reboot
            elif command['type'] == 'forget_network' and forget_network_time is None:
                try:
                    os.remove('/network_config.py')
                    forget_network_time = utime.ticks_ms()
                    log('Removed network config')
                except OSError:  # no file = do nothing
                    print('forget-network is a no-op')
            else:
                error = 'Unknown command'
            # Confirm command execution
            request(API_BASE + '/command/', method='POST',
                    json={
                       'command': command,
                       'success': error == '',
                       'error': error
                    })
    finally:
        del logger


def check_file_signature(in_file, signature, secret):
    try:
        from ubinascii import unhexlify
        import uhmac
        try:
            # Try and just read the entire file into memory to HMAC it
            hmac_instance = uhmac.new(unhexlify(secret), digestmod="sha256")
            content = in_file.read()
            hmac_instance.update(content)
        except MemoryError:
            try:
                del(hmac_instance)
                del(content)
            except NameError:
                pass
            hmac_instance = uhmac.new(unhexlify(secret), digestmod="sha256")
            # If we don't have enough memory to fit the file, try and optimize the largest buffer size
            # to minimize the number of times we call update on the HMAC.
            mem_free = gc.mem_free()
            if mem_free > 2048 + 48:
                buf_size = 2048
            elif mem_free > 1024 + 48:
                buf_size = 1024
            if mem_free > 512 + 48:
                buf_size = 512
            else:
                buf_size = 256
            in_file.seek(0)
            content = in_file.read(buf_size)
            while content:
                hmac_instance.update(content)
                content = in_file.read(buf_size)
        return uhmac.compare_digest(unhexlify(signature), hmac_instance.digest())
    finally:
        del(unhexlify)


@autocollect
def refresh_scripts(debug=pozetron.debug):
    if should_backoff():
        return
    # Update local scripts according to latest info from the server.
    scripts_url = API_BASE + '/scripts/'
    # Get latest script list from the server
    try:
        scripts = request(scripts_url).json()
    except Exception as ex:
        print(exc_logline.format('make request to refresh scripts', ex))
        set_backoff()
        raise ex
    # Update local scripts and cache
    with ScriptStore() as script_store:
        update_list = script_store.get_update_list(scripts)
        delete_list = script_store.get_delete_list(scripts)
        if not update_list and not delete_list:
            log('No changes to deployed scripts')
            return
        script_store.delete_scripts(delete_list)
        subdirs = set()  # created or existing subdirs (this is for optimization)
        for script in update_list:
            try:
                script_info = request(scripts_url + script['id'] + '/').json()
            except Exception as ex:
                log(exc_logline.format('get script info', ex))
                raise ex
            try:
                script_secret = request(scripts_url + script['id'] + '/secret/').json()['secret']
            except Exception as ex:
                log(exc_logline.format('get script secret', ex))
                raise ex
            # Try to stop people overriding pozetron functionality
            print(script_info['name'])
            if script_info['name'].startswith('pozetron'):
                return
            # Pre-create subdirectories if necessary
            if '/' in script_info['name']:
                subdir, _ = script_info['name'].rsplit('/', 1)
                if subdir not in subdirs:
                    makesubdir(SCRIPTS_DIR, subdir)
                    subdirs.add(subdir)
                del subdir, _
            # Added an outfile option to urequests to avoid extra allocations
            tmpname = SCRIPTS_DIR + script_info['name'] + '.tmp'
            if script_info['url']:
                import urequests
                urequests.get(script_info['url'], out_file=tmpname)
                del urequests
            else:
                # Empty file, such as __init__.py
                with open(tmpname, 'w'):
                    pass
            filename = script_info['name']
            if not filename.endswith('.py') and not filename.endswith('.mpy'):
                filename += '.py'
            pyname = SCRIPTS_DIR + filename
            # Check signature and finally write *.py file
            with open(tmpname, 'rb') as script:
                if check_file_signature(script, script_info['signature'], script_secret):
                    try:
                        os.rename(tmpname, pyname)
                    except OSError:
                        os.remove(pyname)
                        os.rename(tmpname, pyname)
                    script_store.update_script(script_info['id'], filename, script_info['signature'])
                    log('Added: {} {}'.format(script_info['id'], script_info['name']))
                else:
                    log('ERROR: signature mismatch: {} {}'.format(script_info['id'], script_info['name']))
                    os.remove(tmpname)
            del script_info, script_secret, tmpname, pyname, filename


class ScriptStore:
    # Encapsulates scripts cache and filesystem.

    def __init__(self):
        self._cache = {}
        self._changed = False
        with open(CACHE_FILE_NAME, 'a'):
            pass
        try:
            os.listdir(SCRIPTS_DIR.split('/')[1])
        except OSError:
            os.mkdir(SCRIPTS_DIR.split('/')[1])
        with open(CACHE_FILE_NAME, 'r') as file:
            for line in file:
                line = line.strip()
                if not line:
                    continue
                id, filename, signature = line.split(',', 2)
                # File does not exists - remove from cache
                # (later it will be re-downloaded from server if necessary)
                try:
                    with open(SCRIPTS_DIR + filename):
                        pass
                # On some platforms FileNotFoundError doesn't exist
                except OSError:
                    continue
                self._cache[id] = (filename, signature)

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.write_cache()

    def get_update_list(self, scripts):
        result = []
        for script in scripts:
            value = self._cache.get(script['id'])
            # script doesn't have a signature. That would require a second network call with the way the
            # API is today
            if value is None:# or value[1] != script['signature']:
                result.append(script)
        return result

    def update_script(self, id, filename, signature):
        self._cache[id] = (filename, signature)
        self._changed = True

    def get_delete_list(self, scripts):
        result = []
        ids = set(x['id'] for x in scripts)
        for x in self._cache.keys():
            if x not in ids:
                result.append(x)
        del ids
        return result

    def delete_scripts(self, ids):
        for id in ids:
            try:
                filename, hash = self._cache[id]
                self._cache.pop(id)
                self._changed = True
            except KeyError:
                continue
            try:
                os.remove(SCRIPTS_DIR + filename)
                log('Removed: {} {}'.format(id, filename))
            except OSError:
                pass

    def write_cache(self):
        if not self._changed:
            return
        with open(CACHE_FILE_NAME, 'w') as file:
            for key, value in self._cache.items():
                # id, module_name, hash
                file.write(','.join([key, value[0], value[1]]) + '\n')


# Get log mode on reboot
def get_log_mode():
    import logger
    try:
        logger._send_logs = LOG_SEND
        logger.file_size = LOG_FILE_SIZE
    except NameError:
        logger._send_logs = False
        logger.file_size = 1024
    try:
        data = request(API_BASE + '/log-mode/').json()
        logger._send_logs = data['enable']
        if data['mode'] == 'file':
            logger.file_size = data['file_size']
        else:
            logger.file_size = 0
    except Exception as ex:
        print('Failed to get log mode from API: {}'.format(ex))
    del logger


# Save current log mode to file, to be used on next restart.
# Return True if file was changed
def _save_log_mode():
    import logger
    log_file_size = 'LOG_FILE_SIZE = {!r}\n'.format(logger.file_size)
    log_send = 'LOG_SEND = {!r}\n'.format(logger._send_logs)
    del logger
    changed = False
    with open('/pozetron_config.py', 'r') as file:
        lines = file.readlines()
    # Replace existing lines
    for i in range(len(lines)):
        if lines[i].startswith('LOG_FILE_SIZE'):
            if lines[i] != log_file_size:
                lines[i] = log_file_size
                changed = True
            log_file_size = None
        elif lines[i].startswith('LOG_SEND'):
            if lines[i] != log_send:
                lines[i] = log_send
                changed = True
            log_send = None
    # Add new lines
    if log_file_size:
        lines.append(log_file_size)
        changed = True
    if log_send:
        lines.append(log_send)
        changed = True
    # Rewrite file only if changed
    if changed:
        with open('/pozetron_config.py', 'w') as file:
            for line in lines:
                file.write(line)
    del log_file_size, log_send
    return changed


#  Write whatever is passed in as data to the datalogger
def datapoint(data):
    try:
        request(API_BASE + '/data/', method='POST', json=data)
    except Exception as ex:
        print('Unable to post data to datalogger: {}'.format(ex))


# This is a convinient callable that takes any arguments and always returns True
always_true = lambda *a, **k: True


# This is the list of subscribers for the Events system
subscribers = set()


def subscribe(topic,filter,action):
    subscriber = Subscriber(topic,filter,action)
    global subscribers
    subscribers.add(subscriber)


def unsubscribe(topic,filter,action):
    subscriber = Subscriber(topic,filter,action)
    global subscribers
    subscribers.remove(subscriber)


#  Write whatever is passed in as data to the eventlogger
def event(data):
    try:
        for subscriber in pozetron.subscribers:
            if (subscriber.topic == '*' or subscriber.topic == data.get('topic', None)) and subscriber.filter(data):
                subscriber.action(data)
    except Exception as ex:
        log(exc_logline.format('run subscribers', ex))
    try:
        request(API_BASE + '/events/', method='POST', json=data)
    except Exception as ex:
        log(exc_logline.format('send event', ex))
