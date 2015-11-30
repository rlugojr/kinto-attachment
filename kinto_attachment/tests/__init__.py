import uuid
import os

import webtest
from cliquet import utils as cliquet_utils
from cliquet.tests import support as cliquet_support
from pyramid_storage.s3 import S3FileStorage


SAMPLE_SCHEMA = {
    "title": "Font file",
    "type": "object",
    "properties": {
        "family": {"type": "string"},
        "author": {"type": "string"},
    }
}


def get_user_headers(user):
    credentials = "%s:secret" % user
    authorization = 'Basic {0}'.format(cliquet_utils.encode64(credentials))
    return {
        'Authorization': authorization
    }


class BaseWebTest(object):
    config = ''

    def __init__(self, *args, **kwargs):
        super(BaseWebTest, self).__init__(*args, **kwargs)
        self.app = self.make_app()
        self._created = []

    def setUp(self):
        super(BaseWebTest, self).setUp()
        self.headers = {
            'Content-Type': 'application/json',
            'Origin': 'http://localhost:9999'
        }
        self.headers.update(get_user_headers('mat'))

        self.create_collection('fennec', 'fonts')
        self.record_uri = self.get_record_uri('fennec', 'fonts', uuid.uuid4())
        self.attachment_uri = self.record_uri + '/attachment'

    def make_app(self):
        curdir = os.path.dirname(os.path.realpath(__file__))
        app = webtest.TestApp("config:%s" % self.config, relative_to=curdir)
        app.RequestClass = cliquet_support.get_request_class(prefix="v1")
        return app

    def upload(self, files=None, params=[], headers={}, status=None):
        files = files or [('attachment', 'image.jpg', '--fake--')]
        headers = headers or self.headers.copy()
        content_type, body = self.app.encode_multipart(params, files)
        headers['Content-Type'] = cliquet_utils.encode_header(content_type)

        resp = self.app.post(self.attachment_uri, body, headers=headers,
                             status=status)
        if 200 <= resp.status_code < 300:
            self._created.append(resp.json['filename'])

        return resp

    def create_collection(self, bucket_id, collection_id):
        bucket_uri = '/buckets/%s' % bucket_id
        self.app.put_json(bucket_uri,
                          {},
                          headers=self.headers)
        collection_uri = bucket_uri + '/collections/%s' % collection_id
        collection = {
            'schema': SAMPLE_SCHEMA
        }
        self.app.put_json(collection_uri,
                          {'data': collection},
                          headers=self.headers)

    def get_record_uri(self, bucket_id, collection_id, record_id):
        return ('/buckets/{bucket_id}/collections/{collection_id}'
                '/records/{record_id}').format(**locals())


class BaseWebTestLocal(BaseWebTest):
    config = 'config/local.ini'

    def tearDown(self):
        """Delete uploaded local files.
        """
        super(BaseWebTest, self).tearDown()
        basepath = self.app.app.registry.settings['kinto.attachment.base_path']
        for created in self._created:
            filepath = os.path.join(basepath, created)
            if os.path.exists(filepath):
                os.remove(filepath)


class BaseWebTestS3(BaseWebTest):
    config = 'config/s3.ini'

    def __init__(self, *args, **kwargs):
        self._s3_bucket_created = False
        super(BaseWebTestS3, self).__init__(*args, **kwargs)

    def make_app(self):
        app = super(BaseWebTestS3, self).make_app()

        # Create the S3 bucket if necessary
        if not self._s3_bucket_created:
            prefix = 'kinto.attachment.'
            settings = app.app.registry.settings
            fs = S3FileStorage.from_settings(settings, prefix=prefix)

            bucket_name = settings[prefix + 'aws.bucket_name']
            fs.get_connection().create_bucket(bucket_name)
            self._s3_bucket_created = True

        return app