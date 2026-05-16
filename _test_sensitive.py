import sys
sys.path.insert(0, '.')
from agents.apply_agent import ApplyAgent

a = ApplyAgent()

cases = [
    ('Please enter your passport number', 'passport number'),
    ('Visa Grant Number', 'visa grant number'),
    ('Grant Number (required)', 'visa grant number'),
    ('TFN', 'tax file number (TFN)'),
    ('Tax File Number', 'tax file number (TFN)'),
    ('Your tax file number', 'tax file number (TFN)'),
    ('First Name', None),
    ('staffing agency', None),
    ('email address', None),
]

all_ok = True
for text, expected in cases:
    got = a._sensitive_pattern_in(text)
    status = 'OK' if got == expected else 'FAIL'
    if status == 'FAIL':
        all_ok = False
    print(f'  [{status}] "{text}" -> {got!r} (expected {expected!r})')

print()
print('All tests passed' if all_ok else 'SOME TESTS FAILED')
sys.exit(0 if all_ok else 1)
