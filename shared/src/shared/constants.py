"""Fixed identifiers for the local single-tenant edition (doc 1 §6.6).

`make seed` inserts exactly these ids; LocalAuthProvider returns them on every
request so the whole app is usable with zero login friction.
"""

LOCAL_ORG_ID = "00000000-0000-0000-0000-000000000001"
LOCAL_USER_ID = "00000000-0000-0000-0000-000000000002"
LOCAL_ORG_NAME = "Local Organization"
LOCAL_USER_EMAIL = "local@forecast.local"
