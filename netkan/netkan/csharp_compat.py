
def csharp_uri_tostring(uri: str) -> str:
    """
    Equivalent to C#: return new System.Uri(uri).ToString();

    https://docs.microsoft.com/en-us/dotnet/api/system.uri.tostring?view=netframework-4.7.2

    That documentation is either wrong or misleading:
    It DOES NOT escape # or ?, but it does UNescape some, but not all, special characters.

    There are many other characters that it neither encodes nor decodes but rather leaves
    in their original form, encoded or decoded, so we can't use urllib.parse here.
    """
    return uri.replace('%20', ' ') \
              .replace('%3A', ':') \
              .replace('%27', "'") \
              .replace('%28', '(') \
              .replace('%29', ')')
