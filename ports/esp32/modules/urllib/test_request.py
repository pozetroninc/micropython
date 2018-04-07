from request import parse_http_list

# This is the failUnlessEqual method from unittest.TestCase
def assertEqual(first, second): 
    """Fail if the two objects are unequal as determined by the '==' 
    operator. 
    """ 
    if not first == second: 
        raise AssertionError('%r != %r' % (first, second))

def test_parse_http_list(self):
    tests = [
        ('a,b,c', ['a', 'b', 'c']),
        ('path"o,l"og"i"cal, example', ['path"o,l"og"i"cal', 'example']),
        ('a, b, "c", "d", "e,f", g, h',
         ['a', 'b', '"c"', '"d"', '"e,f"', 'g', 'h']),
        ('a="b\\"c", d="e\\,f", g="h\\\\i"',
         ['a="b"c"', 'd="e,f"', 'g="h\\i"'])]
    for string, list in tests:
        assertEqual(parse_http_list(string), list)