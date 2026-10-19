import unittest
from admin_upgrade_policy_helper import require_clock_only_change


class ClockHelperUpgradeTests(unittest.TestCase):
    def test_only_clock_function_body_may_change(self):
        before='import time\ndef daemon_birth(p):return 1\ndef report():return 2\n'
        after='import time\ndef daemon_birth(p):return 3\ndef report():return 2\n'
        require_clock_only_change(before,after)
        for candidate in [before, after+'x=1\n', after.replace('import time','import os'),
                          after.replace('return 2','return 4'), after.replace('def report','def changed')]:
            with self.subTest(candidate=candidate),self.assertRaises(ValueError):
                require_clock_only_change(before,candidate)


if __name__=='__main__':unittest.main()
