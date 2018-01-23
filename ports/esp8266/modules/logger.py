exc_logline = 'Failed to {} with Exception: {}'
# Send logs to server? If False, log() is the same as print()
_send_logs = None
_send_fails = 0
# List of log lines
_logs = []
_LOG_BUFFER_SIZE = 15  # lines
# Log file path
_LOG_FILE = '/scripts/log'
# Number of errors
_overflow_errors = 0


# User can configure maximum log file size (in bytes).
# Set it to 0 to avoid using file and keep log lines in memory.
# NOTE: set this variable as soon as possible (immediately after import).
# If you set it after calling log(), some log lines may be lost.
file_size = 1024


def log(text):
    global _overflow_errors
    try:
        if not _send_logs:
            return
        if not file_size:
            if len(_logs) < _LOG_BUFFER_SIZE:
                _logs.append(text)
            else:
                _overflow_errors += 1
        else:
            try:
                with open(_LOG_FILE, 'rb+') as f:
                    f.seek(0, 2)
                    if f.tell() + len(text) + 1 <= file_size:
                        f.write(text + '\n')
                    else:
                        _overflow_errors += 1
            except OSError as ex:
                if ex.args[0] == 2:  # no file
                    with open(_LOG_FILE, 'wb') as f:
                        f.write(text + '\n')
                else:
                    raise ex
    except Exception as ex:
        print('LOGGING ERROR: {}'.format(ex))
    finally:
        print(text)
