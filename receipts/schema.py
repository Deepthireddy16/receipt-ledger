"""The shape of the data we want from one receipt.

Every field is optional on purpose. If the receipt does not show a value,
the model should return null. A missing value is easy to catch later;
a guessed value looks correct and is not.

Every field is a string on purpose. The model only copies text from the
receipt. Turning that text into a date or an amount is done by our own
code in normalize.py, where it is easy to test.
"""

from pydantic import BaseModel, Field

FIELD_NAMES = ["company", "date", "address", "total"]


class ReceiptFields(BaseModel):
    company: str | None = Field(None, description="Name of the business that issued the receipt")
    date: str | None = Field(None, description="Date of the receipt, copied exactly as printed")
    address: str | None = Field(None, description="Address of the business")
    total: str | None = Field(None, description="Final amount paid, digits only, for example 12.50")
