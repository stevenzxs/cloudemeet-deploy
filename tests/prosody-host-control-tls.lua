-- Run in the actual Prosody image after overlay activation. Never prints body.
package.path = '/opt/cloudmeet-prosody/lib/?.lua;/opt/cloudmeet-prosody/lib/prosody/?.lua;' .. package.path
package.cpath = '/opt/cloudmeet-prosody/lib/?.so;/opt/cloudmeet-prosody/lib/prosody/?.so;' .. package.cpath
_G.prosody = { config_loaded = true, paths = { config = '/run/prosody/config', data = '/var/lib/prosody' }, events = require('prosody.util.events').new() }
local config = require 'prosody.core.configmanager'
assert(config.load('/run/prosody/config/prosody.cfg.lua'))
local http = require 'prosody.net.http'
local server = require 'prosody.net.server'
local json = require 'prosody.util.json'
local timer = require 'prosody.util.timer'
local settings = config.get('*', 'client_https_ssl')
assert(settings and settings.verify == 'peer' and settings.cafile)
local builder = server.tls_builder('/run/prosody/config')
builder:apply({mode='client', protocol='tlsv1_2+', verify='peer', cafile=settings.cafile})
http.default.options.sslctx = assert(builder:build())
local secret = assert(config.get('muc.meet.jitsi', 'host_role_check_secret'))
local url = assert(config.get('muc.meet.jitsi', 'host_transfer_status_url'))
local done = false
http.request(url, {method='POST', body=json.encode({roomName='123456789'}),
    headers={['Content-Type']='application/json',['X-Role-Check-Secret']=secret}}, function(_,code)
    assert(code==200 or code==409, 'strict Lua HTTPS/auth request failed: '..tostring(code))
    print('Prosody Lua strict HTTPS and authenticated private API passed: '..code)
    done=true;server.setquitting(true)
end)
timer.add_task(15,function() assert(done,'Prosody Lua HTTPS timeout');server.setquitting(true) end)
server.loop()
assert(done)
