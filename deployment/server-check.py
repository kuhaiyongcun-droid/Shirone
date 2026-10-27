"""Read-only, opt-in HTTP acceptance for a known static package; Python standard library."""
import argparse
import gzip
import hashlib
import http.client
import io
import json
import re
import ssl
import urllib.error
import urllib.parse
import urllib.request
import zlib
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath


class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def origin(value):
    u = urllib.parse.urlsplit(value)
    if u.scheme not in ('http', 'https') or not u.hostname or u.username or u.password or u.query or u.fragment or u.path not in ('', '/'):
        raise ValueError('Expected an HTTP(S) origin without credentials, path, query or fragment')
    return urllib.parse.urlunsplit((u.scheme, u.netloc, '', '', ''))


def manifest_files(value):
    rows = value.get('files')
    if not isinstance(rows, list):
        raise ValueError('Expected package MANIFEST.json files')
    out = {}
    for row in rows:
        name = row.get('path', '')
        if not name.startswith('dist/'):
            continue
        name = name[5:]
        if not name or '\\' in name or any(p in ('', '.', '..') for p in name.split('/')) or PurePosixPath(name).is_absolute() or any(ord(c) < 32 for c in name):
            raise ValueError('Unsafe public asset path')
        if name in out or type(row.get('bytes')) is not int or row['bytes'] < 0 or not re.fullmatch('[0-9a-f]{64}', row.get('sha256', '')):
            raise ValueError('Invalid/duplicate public file record')
        out[name] = row
    if not {'index.html', 'blog/index.html', '404.html'} <= out.keys():
        raise ValueError('Required public entries absent')
    return out


def immutable(name):
    return bool(re.search(r'\.[0-9a-f]{8,64}\.(?:css|js|mjs|png|jpe?g|webp|avif|gif|svg|ico|woff2?|ttf|otf|wasm|glb|bin)$', name, re.I) or re.match(r'^(?:blog/)?_astro/[^/]+\.[A-Za-z0-9_-]{8,}\.(?:css|js|mjs|png|jpe?g|webp|avif|gif|svg|woff2?|ttf|otf|wasm)$', name))


def request(url, method='HEAD', headers=None, limit=2 * 1024 * 1024):
    # No proxy environment, authentication, cookies, redirects, or TLS bypass.
    opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect(), urllib.request.HTTPSHandler(context=ssl.create_default_context()))
    req = urllib.request.Request(url, method=method, headers={'User-Agent': 'kuhai-read-only-acceptance/1', **(headers or {})})
    try:
        response = opener.open(req, timeout=15)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        body = response.read(limit + 1) if method != 'HEAD' else b''
        if len(body) > limit:
            raise ValueError('Response exceeds bounded read')
        return {'status': response.status, 'headers': {k.lower(): v for k, v in response.headers.items()}, 'body': body}


def audit(base, files, fetch=None, http_base=None):
    base = origin(base)
    if http_base:
        http_base = origin(http_base)
        if not http_base.startswith('http://') or not base.startswith('https://') or urllib.parse.urlsplit(http_base).hostname != urllib.parse.urlsplit(base).hostname:
            raise ValueError('HTTP redirect probe must use same hostname and HTTPS target')
    fetch = request if fetch is None else fetch
    report = {'schema': 'kuhai-server-http-check-v1', 'startedUtc': datetime.now(timezone.utc).isoformat(), 'origin': base,
              'checks': [], 'notExecuted': ['nginx -t / server filesystem permissions', 'certificate renewal / full TLS configuration audit', 'physical browser/touch/GPU/performance', 'filing approval', 'deployment or rollback'],
              'tlsTransport': 'Standard certificate/hostname verification used for HTTPS; not a full TLS audit', 'redirectsFollowed': False, 'proxiesUsed': False}
    def check(name, passed, **detail):
        report['checks'].append({'name': name, 'passed': bool(passed), **detail})
    def probe(target, **kwargs):
        try:
            return fetch(target, **kwargs)
        except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException) as error:
            check('HTTP request failed', False, url=target, method=kwargs.get('method', 'HEAD'),
                  errorType=type(error).__name__, error=str(error))
            return {'status': None, 'headers': {}, 'body': b''}
    def get(route, **kwargs):
        return probe(base + route, **kwargs)
    def url(name):
        return '/' + urllib.parse.quote(name, safe='/._-~')
    for route in ('/', '/blog/'):
        r = get(route)
        check('entry ' + route, r['status'] == 200 and r['headers'].get('content-type', '').split(';')[0] == 'text/html' and 'no-cache' in r['headers'].get('cache-control', ''), status=r['status'], headers=r['headers'])
    articles = sorted(n for n in files if n.startswith('blog/posts/') and n.endswith('/index.html'))
    if articles:
        route = url(articles[0][:-10]); r = get(route)
        check('actual article', r['status'] == 200 and r['headers'].get('content-type', '').startswith('text/html'), route=route, status=r['status'])
    else:
        report['notExecuted'].append('Article route: no published article in supplied manifest')
    r = get('/blog?kuhai_probe=1')
    check('blog slash preserves query', r['status'] == 308 and urllib.parse.urljoin(base, r['headers'].get('location', '')) == base + '/blog/?kuhai_probe=1', status=r['status'], headers=r['headers'])
    for route in ('/__kuhai_missing_' + hashlib.sha256(json.dumps(sorted(files)).encode()).hexdigest()[:16], '/404.html', '/blog/404.html'):
        r = get(route)
        check('404 ' + route, r['status'] == 404 and 'no-store' in r['headers'].get('cache-control', ''), status=r['status'], headers=r['headers'])
    types = {'.glb': {'model/gltf-binary'}, '.wasm': {'application/wasm'}, '.woff2': {'font/woff2'}, '.js': {'text/javascript', 'application/javascript'}, '.css': {'text/css'}}
    for ext, expected in types.items():
        names = sorted(n for n in files if n.endswith(ext))
        if not names:
            report['notExecuted'].append('MIME ' + ext + ': no such asset in manifest'); continue
        name = names[0]; r = get(url(name)); cache = r['headers'].get('cache-control', '')
        check('asset MIME/length/cache ' + ext, r['status'] == 200 and r['headers'].get('content-type', '').split(';')[0].strip().lower() in expected and r['headers'].get('content-length') == str(files[name]['bytes']) and (('immutable' in cache and 'max-age=31536000' in cache) if immutable(name) else ('max-age=3600' in cache and 'immutable' not in cache)), asset=name, status=r['status'], headers=r['headers'])
    hashed = next((n for n in sorted(files) if immutable(n)), None)
    if hashed:
        r = get(url(hashed)); check('actual hashed asset immutable', r['status'] == 200 and 'immutable' in r['headers'].get('cache-control', '') and 'max-age=31536000' in r['headers'].get('cache-control', ''), asset=hashed, headers=r['headers'])
    else:
        report['notExecuted'].append('Immutable cache: no matching hash-named resource')
    compressed = next((n for n in sorted(files) if n.endswith(('.css', '.js', '.json')) and 1024 <= files[n]['bytes'] <= 1024 * 1024), None)
    if compressed:
        r = get(url(compressed), method='GET', headers={'Accept-Encoding': 'gzip'})
        decode_error = None
        try:
            decoded = gzip.GzipFile(fileobj=io.BytesIO(r['body'])).read(files[compressed]['bytes'] + 1) if r['headers'].get('content-encoding') == 'gzip' else b''
            valid = hashlib.sha256(decoded).hexdigest() == files[compressed]['sha256']
        except (OSError, EOFError, zlib.error) as error:
            valid = False
            decode_error = {'type': type(error).__name__, 'message': str(error)}
        check('gzip actual text bytes', r['status'] == 200 and r['headers'].get('content-encoding') == 'gzip' and 'accept-encoding' in r['headers'].get('vary', '').lower() and valid, asset=compressed, status=r['status'], headers=r['headers'], decodeError=decode_error)
    else:
        report['notExecuted'].append('gzip: no eligible text asset between 1 KiB and 1 MiB')
    model = next((n for n in sorted(files) if n.endswith('.glb') and files[n]['bytes'] >= 1024), None)
    if model:
        r = get(url(model), method='GET', headers={'Range': 'bytes=0-1023', 'Accept-Encoding': 'identity'}, limit=1024)
        check('GLB single byte range', r['status'] == 206 and r['headers'].get('content-range') == 'bytes 0-1023/' + str(files[model]['bytes']) and len(r['body']) == 1024 and r['body'][:4] == b'glTF', asset=model, status=r['status'], headers=r['headers'])
    else:
        report['notExecuted'].append('Range: no GLB of at least 1024 bytes')
    if http_base:
        r = probe(http_base + '/blog/?kuhai_probe=1')
        check('HTTP to HTTPS preserves path/query', r['status'] in (301, 308) and urllib.parse.urljoin(http_base, r['headers'].get('location', '')) == base + '/blog/?kuhai_probe=1', status=r['status'], headers=r['headers'])
    else:
        report['notExecuted'].append('HTTP to HTTPS redirect: --http-origin not supplied')
    report['passed'] = all(row['passed'] for row in report['checks'])
    return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--origin', required=True, help='Explicit target origin; sends read-only HEAD/GET only')
    parser.add_argument('--http-origin', help='Optional same-host HTTP origin for redirect probe')
    parser.add_argument('--manifest', required=True, type=Path, help='Extracted static package MANIFEST.json; not deployment hash manifest')
    parser.add_argument('--out', required=True, type=Path, help='New local evidence JSON; never overwrites')
    args = parser.parse_args()
    if args.out.exists():
        parser.error('Output already exists; use a new report name')
    data = args.manifest.read_bytes()
    files = manifest_files(json.loads(data.decode('utf-8-sig')))
    try:
        report = audit(args.origin, files, http_base=args.http_origin)
    except (OSError, ValueError, urllib.error.URLError, http.client.HTTPException) as error:
        report = {'schema': 'kuhai-server-http-check-v1', 'passed': False, 'error': str(error), 'completedChecksUnavailable': True, 'notExecuted': ['nginx -t', 'deployment', 'full TLS audit']}
    report['manifestSha256'] = hashlib.sha256(data).hexdigest()
    report['finishedUtc'] = datetime.now(timezone.utc).isoformat()
    with args.out.open('x', encoding='utf-8') as stream:
        json.dump(report, stream, ensure_ascii=False, indent=2)
        stream.write('\n')
    print(json.dumps({'passed': report['passed'], 'report': str(args.out)}))
    return 0 if report['passed'] else 1


if __name__ == '__main__':
    raise SystemExit(main())
