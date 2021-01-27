import unittest

from netkan.csharp_compat import csharp_uri_tostring

class TestCsharpCompat(unittest.TestCase):

    def test_csharp_uri_tostring(self) -> None:
        """
        https://docs.microsoft.com/en-us/dotnet/api/system.uri.tostring?view=netframework-4.7.2

        That documentation is incomplete or wrong; these tests determined empirically in Mono.
        """

        # Stuff that should be changed
        self.assertEqual(csharp_uri_tostring('%20'), ' ')
        self.assertEqual(csharp_uri_tostring('%3A'), ':')
        self.assertEqual(csharp_uri_tostring('%27'), "'")
        self.assertEqual(csharp_uri_tostring('%28'), '(')
        self.assertEqual(csharp_uri_tostring('%29'), ')')

        # Stuff that shouldn't be changed
        stay_same = " :'()&%26/%2F+%2B?%3F#%23,%2C"
        self.assertEqual(csharp_uri_tostring(stay_same), stay_same)
