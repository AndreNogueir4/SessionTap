## What and why

<!-- What does this change, and why is it needed? Link the issue. -->

## Security checklist

- [ ] No real cookies, tokens, HAR files or captured data in the diff (tests use fake values)
- [ ] New/changed API routes require the token and are covered in `core/tests/test_security.py`
- [ ] Nothing new logs, returns or displays secrets unmasked by default
- [ ] No new extension permissions (or they are justified below)
- [ ] No `eval`, remote code, or `dangerouslySetInnerHTML`

## Testing

<!-- How did you test it? -->
