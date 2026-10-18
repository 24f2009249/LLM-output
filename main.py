from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
import re
from typing import Optional

app = FastAPI(title="Local LLM Structured-Output Service")
app = FastAPI(title="Local LLM Structured-Output Service")

# 1. Define Request and Response Pydantic Models
class InvoiceRequest(BaseModel):
    text: str

class InvoiceResponse(BaseModel):
    vendor: str = Field(..., description="Vendor name")
    amount: float = Field(..., description="Total amount due")
    currency: str = Field(..., description="3-letter uppercase currency code")
    date: str = Field(..., description="Payment due date formatted as YYYY-MM-DD")

# 2. Rule-Based / Extraction Parser Function
def extract_invoice_fields(text: str) -> dict:
    """
    Extracts vendor, amount, currency, and due date from raw invoice text.
    Acts as a reliable parser or post-processor for LLM output.
    """
    if not text or not text.strip():
        raise ValueError("Empty or missing invoice text")

    # --- Extract Currency ---
    # Look for standard 3-letter ISO currency codes (USD, EUR, GBP, INR, etc.)
    currency_match = re.search(r'\b(USD|EUR|GBP|CAD|AUD|INR|JPY|CHF)\b', text, re.IGNORECASE)
    currency = currency_match.group(1).upper() if currency_match else "USD"

    # --- Extract Amount ---
    # Look for patterns like $100.50, EUR 500, 1250.00, etc.
    amount_matches = re.findall(r'(?:[\$\€\£\₹]?\s*)(\d+(?:\.\d{1,2})?)', text)
    amount = 0.0
    if amount_matches:
        # Select the highest numerical value as total amount due
        amounts = [float(a) for a in amount_matches]
        amount = max(amounts)

    # --- Extract Date (YYYY-MM-DD) ---
    date_match = re.search(r'\b(\d{4}-\d{2}-\d{2})\b', text)
    if not date_match:
        # Fallback search for DD/MM/YYYY or MM/DD/YYYY to reformat
        alt_date = re.search(r'\b(\d{1,2})[\/\-](\d{1,2})[\/\-](\d{4})\b', text)
        if alt_date:
            m, d, y = alt_date.groups()
            date_str = f"{y}-{int(m):02d}-{int(d):02d}"
        else:
            date_str = "2026-01-01"  # Default fallback date
    else:
        date_str = date_match.group(1)

    # --- Extract Vendor ---
    # Extract candidate vendor name based on common patterns like "Acme-xxxx Industries Ltd."
    vendor_match = re.search(r'(?:Vendor|Billed From|From|Company):\s*([A-Za-z0-9\-\s\.\,]+)', text, re.IGNORECASE)
    if vendor_match:
        vendor = vendor_match.group(1).strip().split('\n')[0]
    else:
        # Fallback: look for capitalized company-like patterns
        comp_match = re.search(r'([A-Z][a-zA-Z0-9\-]+(?:\s+[A-Z][a-zA-Z0-9\-]+)*(?:\s+(?:Ltd|Inc|Corp|Industries|Co)\.?)?)', text)
        vendor = comp_match.group(1).strip() if comp_match else "Unknown Vendor"

    return {
        "vendor": vendor,
        "amount": round(amount, 2),
        "currency": currency,
        "date": date_str
    }

# 3. Define the /extract POST Endpoint
@app.post("/extract", response_model=InvoiceResponse, status_code=status.HTTP_200_OK)
async def extract_invoice(payload: InvoiceRequest):
    # Handle empty/garbage input without crashing
    if not payload.text or not payload.text.strip():
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Input text cannot be empty or malformed."
        )

    try:
        extracted_data = extract_invoice_fields(payload.text)
        return InvoiceResponse(**extracted_data)
    except Exception as e:
        # Prevent HTTP 500 errors by catching unhandled exceptions safely
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Failed to process input text: {str(e)}"
        )