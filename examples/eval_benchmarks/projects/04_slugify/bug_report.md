# Slugs truncated at hyphen boundaries end with trailing hyphen

When `slugify` truncates text to `max_len`, it can leave a trailing hyphen.
For example, `slugify("quick brown fox jumps", max_len=12)` produces `"quick-brown-"` (12 characters).
The slug should be stripped of trailing hyphens after truncation, producing `"quick-brown"`.
