#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""Localized string loading from packaged UTF-8 property files."""

import locale
import os
import re

from libs.utils.assets import read_string_bundle


class StringBundle:

    __create_key = object()

    def __init__(self, create_key, locale_str):
        assert create_key == StringBundle.__create_key, (
            "StringBundle must be created using StringBundle.get_bundle")
        self.id_to_message = {}
        for index, bundle_name in enumerate(
                self.__create_lookup_fallback_list(locale_str)):
            self.__load_bundle(bundle_name, required=index == 0)

    @classmethod
    def get_bundle(cls, locale_str=None):
        if locale_str is None:
            # locale.getdefaultlocale() is deprecated and removed in Python
            # 3.15; use the current locale and fall back to the LANG env var.
            try:
                locale_str = locale.getlocale()[0] or os.getenv('LANG')
            except (ValueError, TypeError, AttributeError):
                print('Invalid locale, using English')
                locale_str = 'en'

        return StringBundle(cls.__create_key, locale_str)

    def get_string(self, string_id):
        assert string_id in self.id_to_message, (
            "Missing string id : " + string_id)
        return self.id_to_message[string_id]

    def __create_lookup_fallback_list(self, locale_str):
        bundle_names = ['strings']
        if locale_str is not None:
            # Keep the historical language/territory fallback without trying
            # to implement all of BCP 47.
            tags = [
                tag for tag in re.split('[^a-zA-Z]', locale_str) if tag
            ][:2]
            if tags:
                bundle_names.append('strings-' + tags[0])
            if len(tags) > 1:
                bundle_names.append(
                    'strings-' + tags[0] + '-' + tags[1])
        return bundle_names

    def __load_bundle(self, bundle_name, required=False):
        contents = read_string_bundle(bundle_name, required=required)
        if contents is None:
            return
        for line in contents.splitlines():
            key_value = line.split('=', 1)
            key = key_value[0].strip()
            value = (
                key_value[1] if len(key_value) > 1 else ''
            ).strip().strip('"')
            self.id_to_message[key] = value
