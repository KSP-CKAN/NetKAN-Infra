# pylint: disable-all
# flake8: noqa

from datetime import datetime, timezone, timedelta
import unittest
from unittest.mock import patch, call
import git
from pynamodb.attributes import MapAttribute

from netkan.auto_freezer import AutoFreezer
from netkan.repos import NetkanRepo
from netkan.metadata import Netkan
from netkan.github_pr import GitHubPR


class TestAutoFreezer(unittest.TestCase):

    now = datetime.now(timezone.utc)
    a_while_ago = now - timedelta(days=1001)
    a_long_time_ago = now - timedelta(days=1050)
    IDENT_TIMESTAMPS = {
        'Astrogator': a_while_ago,
        'SmartTank':  a_long_time_ago,
        'Ringworld':  now,
    }
    IDENT_RESOURCES = {
        'Astrogator': {
            'homepage': 'https://forum.kerbalspaceprogram.com/index.php?/topic/155998-*'
        },
        'SmartTank': {
            'repository': 'https://github.com/HebaruSan/SmartTank'
        },
        'Ringworld': {
            'bugtracker': 'https://github.com/HebaruSan/Ringworld/issues'
        },
    }

    def test_find_idle_mods(self):
        """
        Return freshly idle mods, skip active and ancient mods
        """

        # Arrange
        with patch('git.Repo') as repo_mock, \
            patch('netkan.repos.NetkanRepo') as nk_repo_mock, \
            patch('netkan.auto_freezer.ModStatus') as status_mock, \
            patch('netkan.github_pr.GitHubPR') as pr_mock:

            nk_repo_mock.return_value.netkans.return_value = [
                Netkan(contents='{ "identifier": "Astrogator" }'),
                Netkan(contents='{ "identifier": "SmartTank"  }'),
                Netkan(contents='{ "identifier": "Ringworld"  }'),
            ]
            status_mock.get.side_effect = lambda ident, range_key: unittest.mock.Mock(
                release_date=self.IDENT_TIMESTAMPS[ident])
            nk_repo = nk_repo_mock(git.Repo('/blah'))
            github_pr = pr_mock('', '', '')
            af = AutoFreezer(nk_repo, github_pr, 'ksp')

            # Act
            astrogator_dttm = af._last_timestamp('Astrogator')
            smarttank_dttm = af._last_timestamp('SmartTank')
            ringworld_dttm = af._last_timestamp('Ringworld')
            idle_mods = af._find_idle_mods(1000, 21)

            # Assert
            self.assertEqual(astrogator_dttm, self.a_while_ago)
            self.assertEqual(smarttank_dttm, self.a_long_time_ago)
            self.assertEqual(ringworld_dttm, self.now)
            self.assertEqual(idle_mods, [('Astrogator', self.a_while_ago)])

    def test_submit_pr(self):
        """
        Check pull request format
        """

        # Arrange
        with patch('git.Repo') as repo_mock, \
            patch('netkan.repos.NetkanRepo') as nk_repo_mock, \
            patch('netkan.auto_freezer.ModStatus') as status_mock, \
            patch('netkan.github_pr.GitHubPR') as pr_mock:

            status_mock.get.side_effect = lambda ident, range_key: unittest.mock.Mock(
                release_date=self.IDENT_TIMESTAMPS[ident],
                resources=MapAttribute(**self.IDENT_RESOURCES[ident]))
            unittest.util._MAX_LENGTH = 999999999  # :snake:

            nk_repo = nk_repo_mock(git.Repo('/blah'))
            github_pr = pr_mock('', '', '')
            af = AutoFreezer(nk_repo, github_pr, 'ksp')

            # Act
            af._submit_pr('test_branch_name', 69, [
                ('Astrogator', datetime(2010, 1, 1, tzinfo=timezone.utc)),
                ('SmartTank',  datetime(2015, 1, 1, tzinfo=timezone.utc)),
                ('Ringworld',  datetime(2020, 1, 1, tzinfo=timezone.utc)),
            ])

            # Assert
            self.assertEqual(pr_mock.return_value.create_pull_request.mock_calls, [
                call(branch='test_branch_name',
                     title='Freeze idle mods',
                     body='The attached mods have not updated in 69 or more days. Freeze them to save the bot some CPU cycles.\n\nMod | Last Update\n:-- | :--\n**Astrogator**<br>[homepage](https://forum.kerbalspaceprogram.com/index.php?/topic/155998-*) | 2010-01-01 00:00 UTC\n**SmartTank**<br>[repository](https://github.com/HebaruSan/SmartTank) | 2015-01-01 00:00 UTC\n**Ringworld**<br>[bugtracker](https://github.com/HebaruSan/Ringworld/issues) | 2020-01-01 00:00 UTC',
                     labels=['Pull request', 'Freeze', 'Needs looking into'],
                )
            ])
