from slug.formatter import slugify


def test_simple_slugify():
    assert slugify("Hello World") == "hello-world"


def test_punctuation_removal():
    assert slugify("Hello, World!") == "hello-world"


def test_consecutive_separators_collapsed():
    assert slugify("foo   bar") == "foo-bar"
    assert slugify("foo---bar") == "foo-bar"


def test_empty_string():
    assert slugify("") == ""
    assert slugify("   ") == ""
