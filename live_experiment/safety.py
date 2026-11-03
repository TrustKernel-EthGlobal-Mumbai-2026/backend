"""Research-child Python socket/process boundary; HTTP/CFFI policy is source_http."""
import socket
import sys

API_HOST='api.openai.com'
_INSTALLED=False


def normalize_host(host):
    if isinstance(host,bytes):host=host.decode('ascii')
    return host.lower().rstrip('.') if isinstance(host,str) else ''


def host_allowed(host,source_hosts):
    return normalize_host(host) in ({API_HOST}|set(source_hosts))


def network_guard(trace=None):
    """Install once in an arm child, never in the supervisor.

    Python sockets are limited to TLS443 at explicitly named providers and
    resolved addresses; child subprocesses are prohibited. Native curl traffic
    bypasses Python socket hooks and MUST also be gated by sources.live_tools /
    source_http.data_http. OpenAI HTTP transport separately permits Responses.
    """
    global _INSTALLED
    if _INSTALLED:return
    from .source_http import SOURCE_HOSTS
    source_hosts=set(SOURCE_HOSTS)
    allowed_ips=set()
    original=socket.getaddrinfo

    def resolve(host,port,*args,**kwargs):
        if not host_allowed(host,source_hosts) or str(port) not in ('443','https'):
            raise PermissionError('Live research DNS destination is outside the explicit source policy')
        result=original(host,port,*args,**kwargs)
        allowed_ips.update(row[4][0] for row in result)
        return result

    def audit(event,args):
        if event=='socket.getaddrinfo':
            if not host_allowed(args[0],source_hosts) or str(args[1]) not in ('443','https'):
                raise PermissionError('Live research DNS request denied')
        if event=='socket.connect':
            address=args[1]
            if not isinstance(address,tuple) or len(address)<2 or address[1]!=443 or not (address[0] in allowed_ips or host_allowed(address[0],source_hosts)):
                raise PermissionError('Live research socket destination denied')
        if event in ('subprocess.Popen','os.system','os.exec','os.posix_spawn','os.spawn'):
            raise PermissionError('Live research child cannot launch a process')

    socket.getaddrinfo=resolve
    sys.addaudithook(audit)
    _INSTALLED=True
    if trace is not None:
        trace.emit('safety.network_policy',{'api_host':API_HOST,'source_hosts':sorted(source_hosts),
            'port':443,'subprocesses':False,'curl_requires_source_http_policy':True,
            'scope':'Application-level research child boundaries, not an operating-system firewall.'})
