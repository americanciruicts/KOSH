"""Reproduce the KOSH 'signed out after each transaction' loop against the real app.

Scenario from the 2026-07-16 prod logs: the user has /pick and /part-number-change
open in two tabs. Any SSO round-trip re-clears the session, rotating csrf_token, so
the other tab's next submit fails CSRF -> bounces through SSO -> rotates again.
"""
import os, re, sys

os.environ.setdefault('SSO_SECRET_KEY', 'test-sso-secret-for-local-verification')
os.environ['SESSION_COOKIE_SECURE'] = 'false'

sys.path.insert(0, '/app')
from jose import jwt as jose_jwt
from datetime import datetime, timedelta
import app as koshapp

USER = 'parts@americancircuits.com'
CSRF_RE = re.compile(r'name="csrf_token"[^>]*value="([^"]+)"')


def sso_url():
    token = jose_jwt.encode(
        {'sub': USER, 'type': 'sso', 'target_app': 'kosh',
         'exp': datetime.utcnow() + timedelta(minutes=5)},
        os.environ['SSO_SECRET_KEY'], algorithm='HS256')
    return '/sso/callback?token=' + token


def token_on_page(client, path):
    r = client.get(path)
    assert r.status_code == 200, f'GET {path} -> {r.status_code} (expected 200)'
    m = CSRF_RE.search(r.get_data(as_text=True))
    assert m, f'no csrf_token found on {path}'
    return m.group(1)


def main():
    koshapp.app.config['WTF_CSRF_ENABLED'] = True
    c = koshapp.app.test_client()

    # Tab A: sign in via SSO and render /pick. This is the tab that gets broken.
    assert c.get(sso_url()).status_code == 302, 'initial SSO login failed'
    tab_a_token = token_on_page(c, '/pick')
    print(f'  tab A (/pick) rendered, csrf={tab_a_token[:18]}...')

    # The user's other tab bounces through SSO again (same user, already signed in).
    # Pre-fix this called session.clear() and rotated csrf_token.
    assert c.get(sso_url()).status_code == 302, 'second SSO login failed'
    tab_b_token = token_on_page(c, '/part-number-change')
    print(f'  tab B (/part-number-change) rendered after SSO round-trip')

    results = []

    # TEST 1: tab A's token must still be accepted after the SSO round-trip.
    same_session = tab_a_token == tab_b_token
    results.append(('SSO re-login preserves session/csrf for same user', same_session))
    print(f'\nTEST 1 csrf token survived SSO round-trip: {same_session}')

    # TEST 2: submit tab A's stale-era form. Must NOT fail CSRF.
    r = c.post('/pick', data={'csrf_token': tab_a_token, 'part_number': 'NO-SUCH-JOB-TEST',
                              'pcn': '999999999', 'quantity': '1'},
               follow_redirects=False)
    to_login = 'aci-forge.vercel.app/login' in r.headers.get('Location', '')
    ok = not to_login and r.status_code == 200
    results.append(('tab A submit is not bounced to SSO login', ok))
    print(f'TEST 2 POST /pick from tab A -> {r.status_code} '
          f'{r.headers.get("Location", "(rendered in place)")}')

    # TEST 3: a genuinely bad token, while signed in, must re-render the page in
    # place rather than bouncing to the FORGE login (which reads as a sign-out).
    r = c.post('/pick', data={'csrf_token': 'garbage-token', 'part_number': 'X',
                              'quantity': '1'}, follow_redirects=False)
    loc = r.headers.get('Location', '')
    stays = r.status_code == 302 and loc.endswith('/pick') and 'aci-forge' not in loc
    results.append(('bad CSRF token returns to page, not login', stays))
    print(f'TEST 3 POST /pick w/ bad token -> {r.status_code} {loc}')

    # TEST 4: the user must still be signed in after that CSRF failure.
    r = c.get('/pick')
    still_in = r.status_code == 200
    results.append(('still signed in after a CSRF failure', still_in))
    print(f'TEST 4 GET /pick after CSRF failure -> {r.status_code}')

    print('\n' + '=' * 62)
    for name, passed in results:
        print(f'  [{"PASS" if passed else "FAIL"}] {name}')
    print('=' * 62)
    return 0 if all(p for _, p in results) else 1


if __name__ == '__main__':
    sys.exit(main())
