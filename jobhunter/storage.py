"""Cloudinary storage for CV uploads.

A CV is personal data, so files go up with delivery type `authenticated` rather
than the library default of `upload`, which would make every one of them
readable by anyone holding the URL.

Reads then cannot use the CDN: Cloudinary accounts restrict raw delivery by
default and answer 401 for both plain and signed delivery URLs. The signed
download endpoint under api.cloudinary.com is not part of that restriction, so
that is what `_open` and `url` hand out — and it expires, which a CDN URL for
someone's CV should.
"""

import os
import time

import cloudinary
import cloudinary.uploader
import cloudinary.utils
import requests
from django.core.files.base import ContentFile
from cloudinary_storage.storage import RawMediaCloudinaryStorage


class PrivateRawCloudinaryStorage(RawMediaCloudinaryStorage):
    DELIVERY_TYPE = "authenticated"
    URL_TTL_SECONDS = 3600

    def _download_url(self, name, ttl=None):
        return cloudinary.utils.private_download_url(
            self._prepend_prefix(name),
            None,  # raw public_ids carry their own extension
            resource_type=self._get_resource_type(name),
            type=self.DELIVERY_TYPE,
            expires_at=int(time.time()) + ttl if ttl else None,
        )

    def _upload(self, name, content):
        options = {
            "use_filename": True,
            "resource_type": self._get_resource_type(name),
            "type": self.DELIVERY_TYPE,
            "tags": self.TAG,
        }
        folder = os.path.dirname(name)
        if folder:
            options["folder"] = folder
        return cloudinary.uploader.upload(content, **options)

    def _open(self, name, mode="rb"):
        response = requests.get(self._download_url(name))
        if response.status_code == 404:
            raise IOError(f"{name} is not in Cloudinary")
        response.raise_for_status()
        file = ContentFile(response.content)
        file.name = name
        file.mode = mode
        return file

    def url(self, name):
        return self._download_url(name, self.URL_TTL_SECONDS)

    def exists(self, name):
        response = requests.head(self._download_url(name))
        if response.status_code == 404:
            return False
        response.raise_for_status()
        return True

    def size(self, name):
        response = requests.head(self._download_url(name))
        response.raise_for_status()
        return int(response.headers["content-length"])

    def delete(self, name):
        response = cloudinary.uploader.destroy(
            name,
            invalidate=True,
            resource_type=self._get_resource_type(name),
            type=self.DELIVERY_TYPE,
        )
        return response["result"] == "ok"
