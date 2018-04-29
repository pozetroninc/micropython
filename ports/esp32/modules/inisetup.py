import uos
from flashbdev import bdev
import gc

def check_bootsec():
    buf = bytearray(bdev.SEC_SIZE)
    bdev.readblocks(0, buf)
    empty = True
    for b in buf:
        if b != 0xff:
            empty = False
            break
    if empty:
        return True
    fs_corrupted()

def fs_corrupted():
    import time
    while 1:
        print("""\
FAT filesystem appears to be corrupted. If you had important data there, you
may want to make a flash snapshot to try to recover it. Otherwise, perform
factory reprogramming of MicroPython firmware (completely erase flash, followed
by firmware programming).
""")
        time.sleep(3)

def setup():
    check_bootsec()
    print("Performing initial setup")
    uos.VfsFat.mkfs(bdev)
    vfs = uos.VfsFat(bdev)
    uos.mount(vfs, '/flash')
    uos.chdir('/flash')
    with open("boot.py", "w") as f:
        f.write("""import gc""")

    # The following writes the pozetron config to a file so it can later be overwritten if necessary.
    try:
        config_string = """\
SCRIPTS_DIR = '/scripts/'
API_BASE = 'http://api.pozetron.com/device/v1'
CACHE_FILE_NAME = '/scripts/.scripts_cache'
"""
        with open('pozetron_config.py', 'w') as config_file:
            config_file.write(config_string)
    except:
        print('Error setting up the pozetron config')

    try:
        from resources import resources
        for resource in resources:
            with open('.'.join(resource.rsplit('_', 1)), 'wb') as resource_file:
                resource_file.write(bytes(x for x in resources[resource]))
    except OSError:
        print('Nothing in resources')
    finally:
        resources = None
        del(resources)
    try:
        from user import resources
        from pozetron_config import SCRIPTS_DIR
        try:
            uos.listdir(SCRIPTS_DIR.rsplit('/', 2)[1])
        except OSError:
            uos.mkdir(SCRIPTS_DIR.rsplit('/', 2)[1])
        for resource in resources:
            with open(SCRIPTS_DIR+'.'.join(resource.rsplit('_', 1)), 'wb') as resource_file:
                resource_file.write(bytes(x for x in resources[resource]))
        resources.clear()
    except OSError:
        print('Nothing in user')
    finally:
        resources = None
        SCRIPTS_DIR = None
        del(resources)
        del(SCRIPTS_DIR)
    gc.collect()
    with open("main.py", "w") as f:
        f.write('import gc')
        f.write('\n')
        f.write("import init")
    return vfs
