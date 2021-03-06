# Copyright (c) 2015 Mirantis, Inc.
# All Rights Reserved.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.

"""Tests for database."""

import base64
import hashlib
import six
import mock
from oslo_config import fixture as config_fixture
from oslotest import base
import sqlalchemy.orm

from refstack import db
from refstack.api import constants as api_const
from refstack.db.sqlalchemy import api
from refstack.db.sqlalchemy import models


class DBAPITestCase(base.BaseTestCase):
    """Test case for database API."""

    @mock.patch.object(api, 'store_results')
    def test_store_results(self, mock_store_results):
        db.store_results('fake_results')
        mock_store_results.assert_called_once_with('fake_results')

    @mock.patch.object(api, 'get_test')
    def test_get_test(self, mock_get_test):
        db.get_test(12345)
        mock_get_test.assert_called_once_with(12345, allowed_keys=None)

    @mock.patch.object(api, 'get_test_results')
    def test_get_test_results(self, mock_get_test_results):
        db.get_test_results(12345)
        mock_get_test_results.assert_called_once_with(12345)

    @mock.patch.object(api, 'get_test_records')
    def test_get_test_records(self, mock_db):
        filters = mock.Mock()
        db.get_test_records(1, 2, filters)
        mock_db.assert_called_once_with(1, 2, filters)

    @mock.patch.object(api, 'get_test_records_count')
    def test_get_test_records_count(self, mock_db):
        filters = mock.Mock()
        db.get_test_records_count(filters)
        mock_db.assert_called_once_with(filters)

    @mock.patch.object(api, 'user_get')
    def test_user_get(self, mock_db):
        user_openid = 'user@example.com'
        db.user_get(user_openid)
        mock_db.assert_called_once_with(user_openid)

    @mock.patch.object(api, 'user_save')
    def test_user_save(self, mock_db):
        user_info = 'user@example.com'
        db.user_save(user_info)
        mock_db.assert_called_once_with(user_info)


class DBHelpersTestCase(base.BaseTestCase):
    """Test case for database backend helpers."""

    @mock.patch.object(api, '_create_facade_lazily')
    def test_get_engine(self, mock_create_facade):
        facade = mock_create_facade.return_value
        facade.get_engine = mock.Mock(return_value='fake_engine')

        result = api.get_engine()
        mock_create_facade.assert_called_once_with()
        facade.get_engine.assert_called_once_with()
        self.assertEqual(result, 'fake_engine')

    @mock.patch.object(api, '_create_facade_lazily')
    def test_get_session(self, mock_create_facade):
        facade = mock_create_facade.return_value
        facade.get_session = mock.Mock(return_value='fake_session')

        fake_kwargs = {'foo': 'bar'}
        result = api.get_session(**fake_kwargs)

        mock_create_facade.assert_called_once_with()
        facade.get_session.assert_called_once_with(**fake_kwargs)
        self.assertEqual(result, 'fake_session')

    @mock.patch('oslo_db.sqlalchemy.session.EngineFacade.from_config')
    def test_create_facade_lazily(self, session):
        session.return_value = 'fake_session'
        result = api._create_facade_lazily()
        self.assertEqual(result, 'fake_session')


class DBBackendTestCase(base.BaseTestCase):
    """Test case for database backend."""

    def setUp(self):
        super(DBBackendTestCase, self).setUp()
        self.config_fixture = config_fixture.Config()
        self.CONF = self.useFixture(self.config_fixture).conf

    def test_to_dict(self):
        fake_query_result = mock.Mock()
        fake_query_result.keys.return_value = ('fake_id',)
        fake_query_result.index = 1
        fake_query_result.fake_id = 12345
        self.assertEqual({'fake_id': 12345}, api._to_dict(fake_query_result))

        fake_query_result_list = [fake_query_result]
        self.assertEqual([{'fake_id': 12345}],
                         api._to_dict(fake_query_result_list))

        fake_query = mock.Mock(spec=sqlalchemy.orm.Query)
        fake_query.all.return_value = fake_query_result
        self.assertEqual({'fake_id': 12345}, api._to_dict(fake_query))

        fake_model = mock.Mock(spec=models.RefStackBase)
        fake_model.default_allowed_keys = ('fake_id', 'meta',
                                           'child', 'childs')
        fake_child = mock.Mock(spec=models.RefStackBase)
        fake_child.iteritems.return_value = {'child_id': 42}.items()
        fake_child.default_allowed_keys = ('child_id',)
        fake_child.metadata_keys = {}
        actuall_dict = {'fake_id': 12345,
                        'meta': [{'meta_key': 'answer',
                                  'value': 42}],
                        'child': fake_child,
                        'childs': [fake_child]}
        fake_model.iteritems.return_value = actuall_dict.items()
        fake_model.metadata_keys = {'meta': {'key': 'meta_key',
                                             'value': 'value'}}

        self.assertEqual({'fake_id': 12345,
                          'meta': {'answer': 42},
                          'child': {'child_id': 42},
                          'childs': [{'child_id': 42}]},
                         api._to_dict(fake_model))

    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.models.TestResults')
    @mock.patch('refstack.db.sqlalchemy.models.Test')
    @mock.patch('refstack.db.sqlalchemy.models.TestMeta')
    @mock.patch('uuid.uuid4')
    def test_store_results(self, mock_uuid, mock_test_meta, mock_test,
                           mock_test_result, mock_get_session):
        fake_tests_result = {
            'cpid': 'foo',
            'duration_seconds': 10,
            'results': [
                {'name': 'tempest.some.test'},
                {'name': 'tempest.test', 'uid': '12345678'}
            ],
            'meta': {'answer': 42}
        }
        _id = 12345

        mock_uuid.return_value = _id
        test = mock_test.return_value
        test.save = mock.Mock()

        session = mock_get_session.return_value
        session.begin = mock.MagicMock()

        test_result = mock_test_result.return_value
        test_result.save = mock.Mock()

        test_id = api.store_results(fake_tests_result)

        mock_test.assert_called_once_with()
        mock_get_session.assert_called_once_with()
        test.save.assert_called_once_with(session)
        session.begin.assert_called_once_with()

        self.assertEqual(test_id, six.text_type(_id))
        self.assertEqual(test.cpid, fake_tests_result['cpid'])
        self.assertEqual(test.duration_seconds,
                         fake_tests_result['duration_seconds'])
        self.assertEqual(mock_test_result.call_count,
                         len(fake_tests_result['results']))

    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.models.Test')
    @mock.patch.object(api, '_to_dict', side_effect=lambda x, *args: x)
    def test_get_test(self, mock_to_dict, mock_test, mock_get_session):
        session = mock_get_session.return_value
        session.query = mock.Mock()
        query = session.query.return_value
        query.filter_by = mock.Mock()
        filter_by = query.filter_by.return_value
        mock_result = 'fake_test_info'
        filter_by.first = mock.Mock(return_value=mock_result)
        test_id = 'fake_id'
        actual_result = api.get_test(test_id)

        mock_get_session.assert_called_once_with()
        session.query.assert_called_once_with(mock_test)
        query.filter_by.assert_called_once_with(id=test_id)
        filter_by.first.assert_called_once_with()
        self.assertEqual(mock_result, actual_result)

        session = mock_get_session.return_value
        session.query = mock.Mock()
        query = session.query.return_value
        query.filter_by.return_value.first.return_value = None
        self.assertRaises(api.NotFound, api.get_test, 'fake_id')

    @mock.patch('refstack.db.sqlalchemy.api.models')
    @mock.patch.object(api, 'get_session')
    def test_delete_test(self, mock_get_session, mock_models):
        session = mock_get_session.return_value
        test_query = mock.Mock()
        test_meta_query = mock.Mock()
        test_results_query = mock.Mock()
        session.query = mock.Mock(side_effect={
            mock_models.Test: test_query,
            mock_models.TestMeta: test_meta_query,
            mock_models.TestResults: test_results_query
        }.get)
        db.delete_test('fake_id')
        session.begin.assert_called_once_with()
        test_query.filter_by.return_value.first\
            .assert_called_once_with()
        test_meta_query.filter_by.return_value.delete\
            .assert_called_once_with()
        test_results_query.filter_by.return_value.delete\
            .assert_called_once_with()
        session.delete.assert_called_once_with(
            test_query.filter_by.return_value.first.return_value)

        mock_get_session.return_value = mock.MagicMock()
        session = mock_get_session.return_value
        session.query.return_value\
            .filter_by.return_value\
            .first.return_value = None
        self.assertRaises(api.NotFound, db.delete_test, 'fake_id')

    @mock.patch('refstack.db.sqlalchemy.api.models')
    @mock.patch.object(api, 'get_session')
    def test_get_test_meta_key(self, mock_get_session, mock_models):
        session = mock_get_session.return_value
        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .first.return_value = mock.Mock(value=42)
        self.assertEqual(42, db.get_test_meta_key('fake_id', 'fake_key'))
        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .first.return_value = None
        self.assertEqual(24, db.get_test_meta_key('fake_id', 'fake_key', 24))

    @mock.patch('refstack.db.sqlalchemy.api.models')
    @mock.patch.object(api, 'get_session')
    def test_save_test_meta_item(self, mock_get_session, mock_models):
        session = mock_get_session.return_value
        mock_meta_item = mock.Mock()
        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .first.return_value = mock_meta_item
        db.save_test_meta_item('fake_id', 'fake_key', 42)
        self.assertEqual('fake_id', mock_meta_item.test_id)
        self.assertEqual('fake_key', mock_meta_item.meta_key)
        self.assertEqual(42, mock_meta_item.value)
        session.begin.assert_called_once_with()
        mock_meta_item.save.assert_called_once_with(session)

        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .first.return_value = None
        mock_meta_item = mock.Mock()
        mock_models.TestMeta.return_value = mock_meta_item
        db.save_test_meta_item('fake_id', 'fake_key', 42)
        self.assertEqual('fake_id', mock_meta_item.test_id)
        self.assertEqual('fake_key', mock_meta_item.meta_key)
        self.assertEqual(42, mock_meta_item.value)

    @mock.patch('refstack.db.sqlalchemy.api.models')
    @mock.patch.object(api, 'get_session')
    def test_delete_test_meta_item(self, mock_get_session, mock_models):
        session = mock_get_session.return_value
        mock_meta_item = mock.Mock()
        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .first.return_value = mock_meta_item
        db.delete_test_meta_item('fake_id', 'fake_key')
        session.begin.assert_called_once_with()
        session.delete.assert_called_once_with(mock_meta_item)

        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .first.return_value = None
        self.assertRaises(db.NotFound,
                          db.delete_test_meta_item, 'fake_id', 'fake_key')

    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.models.TestResults')
    def test_get_test_results(self, mock_test_result, mock_get_session):
        mock_test_result.name = mock.Mock()

        session = mock_get_session.return_value
        session.query = mock.Mock()
        query = session.query.return_value
        query.filter_by = mock.Mock()
        filter_by = query.filter_by.return_value
        mock_result = 'fake_test_results'
        expected_result = ['fake_test_results']
        filter_by.all = mock.Mock(return_value=[mock_result])

        test_id = 'fake_id'
        actual_result = api.get_test_results(test_id)

        mock_get_session.assert_called_once_with()
        session.query.assert_called_once_with(mock_test_result)
        query.filter_by.assert_called_once_with(test_id=test_id)
        filter_by.all.assert_called_once_with()
        self.assertEqual(expected_result, actual_result)

    @mock.patch('refstack.db.sqlalchemy.models.Test')
    @mock.patch('refstack.db.sqlalchemy.models.TestMeta')
    def test_apply_filters_for_query_unsigned(self, mock_meta,
                                              mock_test):
        query = mock.Mock()
        mock_test.created_at = six.text_type()
        mock_meta.test_id = six.text_type()

        filters = {
            api_const.START_DATE: 'fake1',
            api_const.END_DATE: 'fake2',
            api_const.CPID: 'fake3'
        }

        unsigned_query = (query
                          .filter.return_value
                          .filter.return_value
                          .filter.return_value)

        unsigned_query.session.query.return_value.filter_by.side_effect = (
            'signed_results_query', 'shared_results_query'
        )

        result = api._apply_filters_for_query(query, filters)

        query.filter.assert_called_once_with(mock_test.created_at >=
                                             filters[api_const.START_DATE])

        query = query.filter.return_value
        query.filter.assert_called_once_with(mock_test.created_at <=
                                             filters[api_const.END_DATE])

        query = query.filter.return_value
        query.filter.assert_called_once_with(mock_test.cpid ==
                                             filters[api_const.CPID])

        unsigned_query.session.query.assert_has_calls((
            mock.call(mock_meta.test_id),
            mock.call().filter_by(meta_key='public_key'),
            mock.call(mock_meta.test_id),
            mock.call().filter_by(meta_key='shared'),
        ))
        unsigned_query.filter.assert_has_calls((
            mock.call(mock_test.id.notin_.return_value),
            mock.call(mock_test.id.in_.return_value),
            mock.call().union(unsigned_query.filter.return_value)
        ))
        filtered_query = unsigned_query.filter.return_value.union.return_value

        self.assertEqual(result, filtered_query)

    @mock.patch('refstack.db.sqlalchemy.models.Test')
    @mock.patch('refstack.db.sqlalchemy.models.TestMeta')
    def test_apply_filters_for_query_signed(self, mock_meta,
                                            mock_test):
        query = mock.Mock()
        mock_test.created_at = six.text_type()
        mock_meta.test_id = six.text_type()

        filters = {
            api_const.START_DATE: 'fake1',
            api_const.END_DATE: 'fake2',
            api_const.CPID: 'fake3',
            api_const.USER_PUBKEYS: ['fake_pk'],
            api_const.SIGNED: 'true'
        }

        signed_query = (query
                        .filter.return_value
                        .filter.return_value
                        .filter.return_value)

        result = api._apply_filters_for_query(query, filters)

        signed_query.join.assert_called_once_with(mock_test.meta)
        signed_query = signed_query.join.return_value
        signed_query.filter.assert_called_once_with(
            mock_meta.meta_key == api_const.PUBLIC_KEY
        )
        signed_query = signed_query.filter.return_value
        mock_meta.value.in_.assert_called_once_with(
            filters[api_const.USER_PUBKEYS])
        signed_query.filter.assert_called_once_with(
            mock_meta.value.in_.return_value)

        filtered_query = signed_query.filter.return_value
        self.assertEqual(result, filtered_query)

    @mock.patch.object(api, '_apply_filters_for_query')
    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.models.Test')
    def test_get_test_records(self, mock_model,
                              mock_get_session,
                              mock_apply):

        per_page = 9000
        filters = {
            api_const.START_DATE: 'fake1',
            api_const.END_DATE: 'fake2',
            api_const.CPID: 'fake3'
        }

        session = mock_get_session.return_value
        first_query = session.query.return_value
        second_query = mock_apply.return_value
        ordered_query = second_query.order_by.return_value
        query_with_offset = ordered_query.offset.return_value
        query_with_offset.limit.return_value.all.return_value = 'fake_uploads'

        result = api.get_test_records(2, per_page, filters)

        mock_get_session.assert_called_once_with()
        session.query.assert_called_once_with(mock_model)
        mock_apply.assert_called_once_with(first_query, filters)
        second_query.order_by.\
            assert_called_once_with(mock_model.created_at.desc())

        self.assertEqual(result, 'fake_uploads')
        ordered_query.offset.assert_called_once_with(per_page)
        query_with_offset.limit.assert_called_once_with(per_page)

    @mock.patch.object(api, '_apply_filters_for_query')
    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.models.Test')
    def test_get_test_records_count(self, mock_model,
                                    mock_get_session,
                                    mock_apply):

        filters = mock.Mock()
        session = mock_get_session.return_value
        query = session.query.return_value
        apply_result = mock_apply.return_value
        apply_result.count.return_value = 999

        result = api.get_test_records_count(filters)
        self.assertEqual(result, 999)

        session.query.assert_called_once_with(mock_model.id)
        mock_apply.assert_called_once_with(query, filters)
        apply_result.count.assert_called_once_with()

    @mock.patch.object(api, 'get_session',
                       return_value=mock.Mock(name='session'),)
    @mock.patch('refstack.db.sqlalchemy.models.User')
    def test_user_get(self, mock_model, mock_get_session):
        user_openid = 'user@example.com'
        session = mock_get_session.return_value
        query = session.query.return_value
        filtered = query.filter_by.return_value
        user = filtered.first.return_value

        result = api.user_get(user_openid)
        self.assertEqual(result, user)

        session.query.assert_called_once_with(mock_model)
        query.filter_by.assert_called_once_with(openid=user_openid)
        filtered.first.assert_called_once_with()

    @mock.patch.object(api, 'get_session',
                       return_value=mock.Mock(name='session'),)
    @mock.patch('refstack.db.sqlalchemy.models.User')
    def test_user_get_none(self, mock_model, mock_get_session):
        user_openid = 'user@example.com'
        session = mock_get_session.return_value
        query = session.query.return_value
        filtered = query.filter_by.return_value
        filtered.first.return_value = None
        self.assertRaises(api.NotFound, api.user_get, user_openid)

    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.models.User')
    @mock.patch.object(api, 'user_get', side_effect=api.NotFound('User'))
    def test_user_update_or_create(self, mock_get_user, mock_model,
                                   mock_get_session):
        user_info = {'openid': 'user@example.com'}
        session = mock_get_session.return_value
        user = mock_model.return_value
        result = api.user_save(user_info)
        self.assertEqual(result, user)

        mock_model.assert_called_once_with()
        mock_get_session.assert_called_once_with()
        user.save.assert_called_once_with(session=session)
        user.update.assert_called_once_with(user_info)
        session.begin.assert_called_once_with()

    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.api.models')
    def test_store_pubkey(self, mock_models, mock_get_session):
        session = mock_get_session.return_value
        pubkey_info = {
            'openid': 'fake_id',
            'format': 'ssh-rsa',
            'pubkey': 'cHV0aW4gaHVpbG8=',
            'comment': 'comment'
        }
        mock_pubkey = mock.Mock()
        mock_pubkey.id = 42
        mock_models.PubKey.return_value = mock_pubkey
        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .all.return_value = None
        self.assertEqual(42, db.store_pubkey(pubkey_info))
        self.assertEqual('fake_id', mock_pubkey.openid)
        self.assertEqual('ssh-rsa', mock_pubkey.format)
        self.assertEqual('cHV0aW4gaHVpbG8=', mock_pubkey.pubkey)
        self.assertEqual(
            hashlib.md5(
                base64.b64decode('cHV0aW4gaHVpbG8='.encode('ascii'))
            ).hexdigest(),
            '3b30cd2bdac1eeb7e92dfc983bf5f943'
        )
        mock_pubkey.save.assert_called_once_with(session)
        session.query.return_value\
            .filter_by.return_value\
            .filter_by.return_value\
            .all.return_value = mock_pubkey
        self.assertRaises(db.Duplication,
                          db.store_pubkey, pubkey_info)

    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.api.models')
    def test_delete_pubkey(self, mock_models, mock_get_session):
        session = mock_get_session.return_value
        db.delete_pubkey('key_id')
        key = session\
            .query.return_value\
            .filter_by.return_value\
            .first.return_value
        session.query.assert_called_once_with(mock_models.PubKey)
        session.query.return_value.filter_by.assert_called_once_with(
            id='key_id')
        session.delete.assert_called_once_with(key)
        session.begin.assert_called_once_with()

    @mock.patch.object(api, 'get_session')
    @mock.patch('refstack.db.sqlalchemy.api.models')
    @mock.patch.object(api, '_to_dict', side_effect=lambda x: x)
    def test_get_user_pubkeys(self, mock_to_dict, mock_models,
                              mock_get_session):
        session = mock_get_session.return_value
        actual_keys = db.get_user_pubkeys('user_id')
        keys = session \
            .query.return_value \
            .filter_by.return_value \
            .all.return_value
        session.query.assert_called_once_with(mock_models.PubKey)
        session.query.return_value.filter_by.assert_called_once_with(
            openid='user_id')
        self.assertEqual(keys, actual_keys)
