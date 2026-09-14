from html.parser import HTMLParser
from pathlib import Path
from tempfile import TemporaryDirectory
from urllib.parse import urljoin

from django.core.management import call_command
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings


class StylesheetLinks(HTMLParser):
    def __init__(self, html):
        super().__init__()
        self.urls = []
        self.feed(html)

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == 'link' and attrs.get('rel') == 'stylesheet':
            self.urls.append(attrs['href'])


@override_settings(DEBUG=False)
class ProductionStylesTests(TestCase):
    def test_404_uses_shared_layout_for_guest_and_signed_in_user(self):
        self.client.raise_request_exception = False
        user = get_user_model().objects.create_user(username='error-page-viewer')
        for signed_in in (False, True):
            if signed_in:
                self.client.force_login(user)
            for path in ('/profile/5235/', '/__minto_missing_91af6e__/'):
                with self.subTest(signed_in=signed_in, path=path):
                    response = self.client.get(path)
                    self.assertEqual(response.status_code, 404)
                    self.assertTemplateUsed(response, 'base.html')
                    self.assertContains(response, '<main class="minto-main">', count=1, status_code=404)
                    self.assertContains(response, 'href="/" class="error-button"', status_code=404)
                    self.assertContains(response, 'Log Out' if signed_in else 'Sign In', status_code=404)

    def test_pages_load_collected_css_without_debug(self):
        # A fresh middleware chain must serve collected assets, not test-server
        # static handlers or the source directories used only in DEBUG mode.
        with TemporaryDirectory() as root:
            with override_settings(STATIC_ROOT=Path(root)):
                call_command('collectstatic', interactive=False, verbosity=0)
                for path, status in [('/', 200), ('/profile/5235/', 404),
                                     ('/__minto_missing_91af6e__/', 404)]:
                    with self.subTest(path=path):
                        response = self.client.get(path)
                        self.assertEqual(response.status_code, status)
                        if status == 404:
                            self.assertTemplateUsed(response, '404.html')
                        links = StylesheetLinks(response.content.decode()).urls
                        self.assertGreaterEqual(len(links), 2)
                        for href in links:
                            css = self.client.get(urljoin(path, href))
                            self.assertEqual(css.status_code, 200, href)
                            self.assertEqual(css['Content-Type'].split(';')[0], 'text/css')
                            body = b''.join(css.streaming_content) if css.streaming else css.content
                            self.assertNotIn(b'<html', body.lower())
                            self.assertIn(b'{', body)

    def test_shared_template_has_no_markdown_fences(self):
        self.assertNotContains(self.client.get('/'), '```')
