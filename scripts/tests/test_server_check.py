"""Offline HTTP-response tests only: no socket, server, certificate or deployment."""
import gzip
import hashlib
import contextlib
import http.client
import importlib.util
import io
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock
spec=importlib.util.spec_from_file_location('server_check',Path(__file__).resolve().parents[2]/'deployment/server-check.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
class ServerChecks(unittest.TestCase):
    def setUp(self):
        self.payload={'index.html':b'<html>home</html>','blog/index.html':b'<html>blog</html>','404.html':b'404','blog/posts/welcome/index.html':b'article','assets/app.12345678.js':b'x'*2048,'assets/style.css':b'x'*1536,'assets/a.glb':b'glTF'+b'x'*2044,'assets/a.wasm':b'wasm','assets/a.woff2':b'woff'}
        self.files={n:{'path':'dist/'+n,'bytes':len(v),'sha256':hashlib.sha256(v).hexdigest()} for n,v in self.payload.items()}
    def fetch(self,url,method='HEAD',headers=None,limit=None):
        self.assertIn(method,('HEAD','GET')); route=url.split('example.test',1)[1]; headers=headers or {}
        if route=='/blog?kuhai_probe=1':return {'status':308,'headers':{'location':'/blog/?kuhai_probe=1'},'body':b''}
        if route.startswith('/__kuhai_missing_') or route in ('/404.html','/blog/404.html'):return {'status':404,'headers':{'cache-control':'no-store'},'body':b''}
        name={'/':'index.html','/blog/':'blog/index.html','/blog/posts/welcome/':'blog/posts/welcome/index.html'}.get(route,route.lstrip('/'))
        data=self.payload[name]; ext=Path(name).suffix; mime={'.html':'text/html','.js':'text/javascript','.css':'text/css','.glb':'model/gltf-binary','.wasm':'application/wasm','.woff2':'font/woff2'}[ext]
        out={'content-type':mime,'content-length':str(len(data)),'cache-control':'no-cache' if ext=='.html' else 'public, max-age=31536000, immutable' if m.immutable(name) else 'public, max-age=3600'}
        if headers.get('Range'):return {'status':206,'headers':{**out,'content-range':'bytes 0-1023/'+str(len(data))},'body':data[:1024]}
        if headers.get('Accept-Encoding')=='gzip':return {'status':200,'headers':{**out,'content-encoding':'gzip','vary':'Accept-Encoding'},'body':gzip.compress(data)}
        return {'status':200,'headers':out,'body':b'' if method=='HEAD' else data}
    def test_manifest_known_public_only(self):
        rows=list(self.files.values())+[{'path':'deployment/server-check.py'}]
        self.assertEqual(set(m.manifest_files({'files':rows})),set(self.files))
        with self.assertRaises(ValueError):m.manifest_files({'files':rows+[{'path':'dist/../secret','bytes':0,'sha256':'a'*64}]})
    def test_complete_expected_responses(self):
        r=m.audit('https://example.test',self.files,self.fetch);self.assertTrue(r['passed'],r)
        self.assertIn('HTTP to HTTPS redirect: --http-origin not supplied',r['notExecuted'])
    def test_bad_cache_mime_gzip_range_are_failures(self):
        def wrong(url,**kwargs):
            r=self.fetch(url,**kwargs)
            if '/assets/' in url:r['headers']['content-type']='text/html';r['headers']['cache-control']='no-store'
            if kwargs.get('headers',{}).get('Range'):r['status']=200
            if kwargs.get('headers',{}).get('Accept-Encoding')=='gzip':r['body']=gzip.compress(b'wrong')
            return r
        r=m.audit('https://example.test',self.files,wrong);self.assertFalse(r['passed']);self.assertGreaterEqual(sum(not x['passed'] for x in r['checks']),7)
    def test_redirect_must_preserve_query(self):
        def wrong(url,**kwargs):
            r=self.fetch(url,**kwargs)
            if r['status']==308:r['headers']['location']='/blog/'
            return r
        self.assertFalse(m.audit('https://example.test',self.files,wrong)['passed'])
    def test_credentials_and_nonorigin_urls_rejected(self):
        for x in ['https://user:pass@example.test','file:///tmp','https://example.test/private','https://example.test/?x=1']:
            with self.assertRaises(ValueError):m.origin(x)
    def test_no_redirect_handler(self):
        self.assertIsNone(m.NoRedirect().redirect_request(None,None,308,'',{},'https://elsewhere.test'))
    def test_invalid_deflate_records_failure_and_continues(self):
        def wrong(url,**kwargs):
            r=self.fetch(url,**kwargs)
            if kwargs.get('headers',{}).get('Accept-Encoding')=='gzip':
                r['body']=bytes.fromhex('1f8b0800000000000003ff000000000000000000')
            return r
        result=m.audit('https://example.test',self.files,wrong)
        self.assertFalse(result['passed'])
        row=next(x for x in result['checks'] if x['name']=='gzip actual text bytes')
        self.assertFalse(row['passed']);self.assertEqual(row['decodeError']['type'],'error')
        self.assertTrue(next(x for x in result['checks'] if x['name']=='GLB single byte range')['passed'])
    def test_transport_failure_retains_independent_checks(self):
        for error in (TimeoutError('timed out'),http.client.IncompleteRead(b'glTF',1020),m.urllib.error.URLError('TLS verification failed')):
            with self.subTest(error=type(error).__name__):
                def wrong(url,**kwargs):
                    if kwargs.get('headers',{}).get('Range'):raise error
                    return self.fetch(url,**kwargs)
                result=m.audit('https://example.test',self.files,wrong)
                self.assertFalse(result['passed'])
                self.assertTrue(next(x for x in result['checks'] if x['name']=='entry /')['passed'])
                self.assertFalse(next(x for x in result['checks'] if x['name']=='GLB single byte range')['passed'])
                failure=next(x for x in result['checks'] if x['name']=='HTTP request failed')
                self.assertEqual(failure['errorType'],type(error).__name__)
                self.assertEqual(failure['method'],'GET')
    def test_cli_saves_failed_report_after_response_disconnect(self):
        def wrong(url,**kwargs):
            if kwargs.get('headers',{}).get('Range'):raise http.client.RemoteDisconnected('connection closed')
            return self.fetch(url,**kwargs)
        with tempfile.TemporaryDirectory(prefix='kuhai-http-evidence-') as tmp:
            manifest=Path(tmp)/'MANIFEST.json';output=Path(tmp)/'report.json'
            manifest.write_text(json.dumps({'files':list(self.files.values())}),encoding='utf-8')
            args=['server-check.py','--origin','https://example.test','--manifest',str(manifest),'--out',str(output)]
            with mock.patch.object(sys,'argv',args),mock.patch.object(m,'request',wrong),contextlib.redirect_stdout(io.StringIO()):
                self.assertEqual(m.main(),1)
            result=json.loads(output.read_text(encoding='utf-8'))
            self.assertFalse(result['passed']);self.assertIn('finishedUtc',result)
            self.assertEqual(result['manifestSha256'],hashlib.sha256(manifest.read_bytes()).hexdigest())
            self.assertTrue(any(row.get('errorType')=='RemoteDisconnected' for row in result['checks']))
    def test_redirect_target_validated_before_any_request(self):
        with self.assertRaises(ValueError):
            m.audit('https://example.test',self.files,lambda *a,**k:self.fail('unexpected request'),http_base='http://other.test')
if __name__=='__main__':unittest.main()
