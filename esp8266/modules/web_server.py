#This module provides the webserver which will take the network credentials from the user and save them to
#the credentials file. It is not a generic webserver, and as one of the first files written for the project has plenty
#of refactoring opportunities.
HTTP_200_OK = 'HTTP/1.1 200 OK\r\nConnection: close\r\nServer: MicroPython\r\n'
HTTP_302_REDIRECT = 'HTTP/1.1 302 Found\r\nLocation: {}\r\nConnection: close\r\nServer: MicroPython\r\n\r\n'
HTML_CONTENT_TYPE = 'Content-Type: text/html\r\n\r\n'
SVG_CONTENT_TYPE = 'Content-Type: image/svg+xml\r\n\r\n'
#JSON_CONTENT_TYPE = 'Content-Type: application/json\r\n\r\n'
START_PAGE = '<html><head><link rel="icon" href="data:;base64,="><meta name="viewport" content="width=device-width, initial-scale=1.0"><style>* {color: #333333; text-align: center}'
WIFI_REQUEST = '</style><title>Network Setup</title></head><body><div id="wrapper"><div id="form" style="display: inline-block;"><h1>Network Credential Setup</h1><img src="wifi.svg"><br><br>'
FORM = '<form action="/" method="POST" enctype="application/x-www-form-urlencoded">Network Name:<br><input type="text" name="networkname"><br>WiFi Password:<br><input type="text" name="psk"><br><input type="submit" value="Submit">'
DIVS = '</div></div>'
UNSUPPORTED_CHROME ='<div style="border: 3px solid red; background-color: #EF4E57"><strong>Chrome is not currently supported. Please use Firefox.</strong></div>'
WIFI_SUCCESS = ' html, body { margin:0; padding:0; overflow:hidden } img { position:absolute; top:20%; left:5%; height:79%; width:90% }</style><title>Network Credentials Configured</title></head><body><p><h1>Network Credentials Configured</h1></p><br><br><img src="/wifi.svg/green">'
END_PAGE = '</body></html>'


def network_bootstrap_webserver(port= 80, debug = False):
    try:
        import usocket as socket
        import gc
        import utime as time
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind(('', port))
        if debug: print("Listening on port {}".format(port))
        s.listen(0)
        fin = False
        while not fin == True:
            try:
                conn, addr = s.accept()
                chrome = None
                if debug: print("Connection received: {}".format(str(addr)))
                request_line = conn.readline()
                request_line = str(request_line)
                header = conn.readline()
                while header != b'\r\n' and header != b'':
                    header = conn.readline()
                    if b'Chrome/' in header:
                        chrome = True
                if 'POST ' in request_line:
                    if debug: print('POST request')
                    request = str(conn.recv(1024))
                    if not chrome:
                        try:
                            body_start = request.find('networkname=')
                            request = request[body_start::]
                            value = ""
                            key = request.find('networkname=')
                            request = request[key::]
                            equals = request.find('=')
                            if "&" in request:
                                end = request.find("&")
                            elif "'" in request:
                                end = request.find("'")
                                fin = True
                            networkname = request[equals+1:end:]
                            value = value + networkname
                            if not fin:
                                key = request.find('psk=')
                                request = request[key::]
                                equals = request.find('=')
                                if "&" in request:
                                    end = request.find("&")
                                elif "'" in request:
                                    end = request.find("'")
                                psk = request[equals+1:end:]
                                conn.sendall(HTTP_200_OK+HTML_CONTENT_TYPE)
                                conn.sendall(START_PAGE)
                                conn.sendall(WIFI_SUCCESS)
                                conn.sendall(END_PAGE)
                        except:
                            conn.sendall(HTTP_302_REDIRECT.format('/'))
                    else:
                        conn.sendall(HTTP_302_REDIRECT.format('/'))
                elif 'GET /wifi.svg' in request_line:
                    if debug: print('SVG requested')
                    conn.sendall(HTTP_200_OK)
                    conn.sendall(SVG_CONTENT_TYPE)
                    with open('wifi.svg', 'r') as svg:
                        if '/green' in request_line:
                            green = True
                        else:
                            green = False
                        for line in svg:
                            gc.collect()
                            if green:
                                colour = line.find('#')
                                if colour > 0:
                                    colour += 1
                                    line = line[:colour:] + '00FF00' + line[colour+6::]
                            conn.sendall(line)
                        if green:
                            # This should be the last resource requested upon successful configuration.
                            fin = True
                else:
                    if debug: print('HTML requested')
                    conn.sendall(HTTP_200_OK+HTML_CONTENT_TYPE)
                    conn.sendall(START_PAGE)
                    conn.sendall(WIFI_REQUEST)
                    if chrome:
                        conn.sendall(UNSUPPORTED_CHROME)
                    conn.sendall(FORM+DIVS+END_PAGE)
                conn.sendall('\r\n')
                conn.close()
                gc.collect()
            except OSError as ex:
                if 'Errno 104' in str(ex):
                    pass
        else:
            with open("/network_config.py", "w") as f:
                f.write("network_name = '"+networkname+"'\n")
                f.write("network_psk = '"+psk+"'")
            # We have to give the filesystem time to sync the changes or sync them manually.
            time.sleep(1)
            import gc
            gc.collect()
    finally:
        try:
            s.close()
        except Exception as ex:
            s = None
            del(s)
            raise ex
