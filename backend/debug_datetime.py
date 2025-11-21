from datetime import datetime, timezone
from pydantic import BaseModel

class RefundRequest(BaseModel):
    purchase_date: datetime

data = {"purchase_date": "2025-11-21T16:15:23.260Z"}
req = RefundRequest(**data)

print(f"Input: {data['purchase_date']}")
print(f"Parsed: {req.purchase_date}")
print(f"Tzinfo: {req.purchase_date.tzinfo}")

now = datetime.now(timezone.utc)
print(f"Now (UTC): {now}")
print(f"Now Tzinfo: {now.tzinfo}")

try:
    diff = now - req.purchase_date
    print(f"Diff: {diff}")
    print("SUCCESS")
except TypeError as e:
    print(f"ERROR: {e}")
