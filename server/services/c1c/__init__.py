from server import app
from server.services.c1c import fake_data


def is_mock_c1c() -> bool:
    return app.config['MOCK_C1C'] and \
        app.config['FLASK_ENV'].lower() != 'production'


class C1C:
    def __init__(self, proxy_url, api_domain, username, password):
        self.proxy_dict = {
            'http': proxy_url,
            'https': proxy_url
        } if proxy_url else None
        self.api_domain = api_domain
        self.username = username
        self.password = password

    def _make_request(self, path, method='GET'):
        import requests
        url = f'{self.api_domain}{path}'
        if self.proxy_dict:
            return requests.request(method, url, proxies=self.proxy_dict,
                                    auth=(self.username, self.password))
        else:
            return requests.request(method, url, auth=(self.username, self.password))

    def get_student_photo(self, student_sid):
        if is_mock_c1c():
            return fake_data.get_fake_photo(student_sid)
        try:
            r = self._make_request(f'/c1c-api/v1/photo/{student_sid}')
            if r.status_code == 200:
                return r.content
            else:
                return None
        except:
            return None


c1c_client = C1C(app.config['C1C_PROXY_URL'], app.config['C1C_API_DOMAIN'],
                 app.config['C1C_API_USERNAME'], app.config['C1C_API_PASSWORD'])
