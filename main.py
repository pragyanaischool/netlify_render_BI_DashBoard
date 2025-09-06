import os
import httpx
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field

# Load environment variables from .env file for local development
load_dotenv()

# --- API Configuration and Startup Check ---
API_KEY = os.getenv("FMP_API_KEY")
if not API_KEY:
    raise RuntimeError("FMP_API_KEY environment variable not set. Application cannot start.")

BASE_URL = "https://financialmodelingprep.com/api/v3"

app = FastAPI(
    title="Stock Analytics API",
    description="A proxy API for fetching data from FinancialModelingPrep."
)

# --- CORS Middleware (Secure Configuration) ---
origins = [
    # Add your frontend domains here
    "https://lucky-starlight-b2967e.netlify.app",
    # Add localhost variants for local development
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1:5500",
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],# origins,
    allow_credentials=True,
    allow_methods=["*"], # Be specific about the methods you allow
    allow_headers=["*"],
)

# --- Pydantic Models for Response Validation ---
class StockQuote(BaseModel):
    symbol: str
    name: str
    price: float
    changes_percentage: float = Field(alias="changesPercentage")
    market_cap: int | None = Field(alias="marketCap", default=None)
    volume: int
    exchange: str

# You can create models for your other responses as well
# class StockProfile(BaseModel): ...
# class ChartData(BaseModel): ...

# --- Helper Function for API Calls ---
async def fetch_fmp_data(endpoint: str):
    """A helper function to fetch data from the FinancialModelingPrep API."""
    url = f"{BASE_URL}{endpoint}?apikey={API_KEY}"
    async with httpx.AsyncClient() as client:
        try:
            response = await client.get(url)
            response.raise_for_status()
            data = response.json()
            if not data:
                raise HTTPException(status_code=404, detail=f"No data found at endpoint: {endpoint}")
            return data
        except httpx.HTTPStatusError as exc:
            raise HTTPException(status_code=exc.response.status_code, detail=f"API request failed: {exc.response.text}")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"An unexpected error occurred: {str(e)}")


# --- API Endpoints ---
@app.get("/api/quote/{ticker}", response_model=StockQuote)
async def get_quote(ticker: str):
    """Endpoint to get the latest quote for a stock."""
    quote_data = await fetch_fmp_data(f"/quote/{ticker}")
    if isinstance(quote_data, list) and quote_data:
        return quote_data[0]
    raise HTTPException(status_code=404, detail="Quote data for ticker not found.")

@app.get("/api/historical/daily/{ticker}")
async def get_historical_daily(ticker: str):
    """Endpoint to get daily historical data."""
    historical_data = await fetch_fmp_data(f"/historical-price-full/{ticker}")
    return historical_data.get("historical", [])

# Feel free to add Pydantic models for this comprehensive endpoint too!
@app.get("/api/stock/{ticker}")
async def get_stock_all_data(ticker: str):
    """Endpoint to get a combined set of data for a stock ticker."""
    profile_data = await fetch_fmp_data(f"/profile/{ticker}")
    quote_data = await fetch_fmp_data(f"/quote/{ticker}")
    intraday_data = await fetch_fmp_data(f"/historical-chart/5min/{ticker}")

    if not all([profile_data, quote_data, intraday_data]):
        raise HTTPException(status_code=404, detail=f"Could not retrieve full data for ticker {ticker}.")

    return {
        "profile": profile_data[0] if profile_data else None,
        "quote": quote_data[0] if quote_data else None,
        "chart_intraday": intraday_data
    }

@app.get("/")
def read_root():
    """Root endpoint with a status message."""
    return {
        "message": "Stock Analytics API is running.",
        "api_key_status": "CONFIGURED", # We know it is, or the app would not have started
        "docs_url": "/docs"
    }
