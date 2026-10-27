"""Read-only HTTP verification of the assembled local release, not browser QA."""
import datetime
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

RELEASE = Path(__file__).resolve().parents[1]
BASE = 'http://127.0.0.1:4177'
name = sys.argv[1] if len(sys.argv) == 2 else 'dist'
root = (RELEASE / name).resolve(strict=True)
if root.parent != RELEASE or not name.startswith('dist'):
    raise SystemExit('Expected an assembled dist child')
checks = []

class NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, request, fp, code, message, headers, new_url):
        return None

opener = urllib.request.build_opener(urllib.request.ProxyHandler({}), NoRedirect())

def get(route, method='GET'):
    request = urllib.request.Request(BASE + route, method=method)
    try:
        response = opener.open(request, timeout=30)
    except urllib.error.HTTPError as error:
        response = error
    with response:
        data = response.read()
        return response.status, response.headers, data

for route, file in [('/', 'index.html'), ('/blog/', 'blog/index.html'),
                    ('/blog/archive/', 'blog/archive/index.html'),
                    ('/blog/about/', 'blog/about/index.html'),
                    ('/blog/posts/welcome-to-archive/', 'blog/posts/welcome-to-archive/index.html'),
                    ('/blog/categories/', 'blog/categories/index.html'),
                    ('/blog/tags/', 'blog/tags/index.html'),
                    ('/blog/rss.xml', 'blog/rss.xml'), ('/blog/atom.xml', 'blog/atom.xml'),
                    ('/blog/pagefind/pagefind.js', 'blog/pagefind/pagefind.js'),
                    ('/robots.txt', 'robots.txt'), ('/sitemap-index.xml', 'sitemap-index.xml')]:
    status, headers, data = get(route)
    expected = (root / file).read_bytes()
    checks.append({'route': route, 'status': status, 'passed': status == 200 and data == expected,
                   'bytes': len(data), 'sha256': hashlib.sha256(data).hexdigest(),
                   'content_type': headers.get('Content-Type')})

for route in ['/not-a-real-page/', '/blog/not-a-real-page/', '/blog/projects/',
              '/blog/games/', '/.env', '/blog/package.json', '/blog/src/', '/assets/', '/404.html', '/blog/404.html']:
    status, headers, data = get(route)
    checks.append({'route': route, 'status': status, 'passed': status == 404 and data == (root / '404.html').read_bytes(),
                   'custom_404': data == (root / '404.html').read_bytes()})
for route in ['/', '/blog/', '/not-a-real-page/']:
    status, headers, data = get(route, 'HEAD')
    expected = 404 if route == '/not-a-real-page/' else 200
    checks.append({'route': route, 'method': 'HEAD', 'status': status, 'passed': status == expected and not data and int(headers['Content-Length']) > 0})
for route, destination in [('/blog', '/blog/'), ('/blog?x=1', '/blog/?x=1')]:
    status, headers, data = get(route)
    checks.append({'route': route, 'status': status, 'location': headers.get('Location'),
                   'passed': status == 308 and headers.get('Location') == destination})
for suffix, mime in [('.glb', 'model/gltf-binary'), ('.wasm', 'application/wasm'), ('.woff2', 'font/woff2')]:
    file = next(root.rglob('*' + suffix))
    route = '/' + file.relative_to(root).as_posix()
    status, headers, data = get(route, 'HEAD')
    checks.append({'route': route, 'method': 'HEAD', 'status': status, 'content_type': headers.get('Content-Type'),
                   'passed': status == 200 and not data and headers.get('Content-Type') == mime and int(headers['Content-Length']) == file.stat().st_size})

stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%dT%H%M%SZ')
output = RELEASE / 'evidence' / ('http-' + name + '-' + stamp + '.json')
result = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(),
          'root': str(root), 'base': BASE, 'passed': all(row['passed'] for row in checks),
          'checks': checks, 'scope': 'Local static HTTP only; Nginx, TLS and browser remain separate.'}
with output.open('x', encoding='utf-8') as stream:
    json.dump(result, stream, ensure_ascii=False, indent=2)
print(json.dumps({'report': str(output), 'passed': result['passed'], 'checks': len(checks)}))
raise SystemExit(0 if result['passed'] else 1)
