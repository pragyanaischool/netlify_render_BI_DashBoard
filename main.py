import os
import httpx
import asyncio
import logging
import json
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from dotenv import load_dotenv
from pydantic import BaseModel, Field
from typing import List, Optional

# --- Basic Logger Configuration ---
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

# Load environment variables from a .env file for local development
load_dotenv()

# --- API Configuration and Startup Check ---
API_KEY = os.getenv("FMP_API_KEY")
if not API_KEY:
    raise RuntimeError("FMP_API_KEY environment variable not set. Application cannot start.")

BASE_URL = "https://financialmodelingprep.com/api/v3"

app = FastAPI(
    title="Stock Analytics API",
    description="An optimized proxy API for fetching data from FinancialModelingPrep."
)

# --- CORS Middleware (allowing frontend to connect) ---
origins = [
    "https://lucky-starlight-b2967e.netlify.app",
    "http://localhost",
    "http://localhost:8080",
    "http://127.0.0.1:5500",
    # Add any other frontend URLs you use
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], #origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- Pydantic Models for Data Validation & Serialization ---
class StockQuote(BaseModel):
    symbol: str
    name: str
    price: float
    changes_percentage: float = Field(alias="changesPercentage")
    change: float
    day_low: float = Field(alias="dayLow")
    day_high: float = Field(alias="dayHigh")
    market_cap: Optional[int] = Field(alias="marketCap", default=None)
    volume: int
    exchange: str

class StockProfile(BaseModel):
    symbol: str
    price: float
    beta: Optional[float]
    vol_avg: Optional[int] = Field(alias="volAvg")
    mkt_cap: Optional[int] = Field(alias="mktCap")
    last_div: Optional[float] = Field(alias="lastDiv")
    range: str
    changes: float
    company_name: str = Field(alias="companyName")
    currency: str
    isin: str
    description: Optional[str]
    website: Optional[str]
    image: Optional[str]
    ceo: Optional[str] = Field(alias="ceo")
    sector: Optional[str]
    country: Optional[str]
    industry: Optional[str]
    exchange: str

class IntradayChartPoint(BaseModel):
    date: str
    open: float
    low: float
    high: float
    close: float
    volume: int

class HistoricalDataPoint(BaseModel):
    date: str
    open: float
    high: float
    low: float
    close: float
    adj_close: float = Field(alias="adjClose")
    volume: int
    unadjusted_volume: int = Field(alias="unadjustedVolume")
    change: float
    change_percent: float = Field(alias="changePercent")
    vwap: float
    label: str
    change_over_time: float = Field(alias="changeOverTime")

class CombinedStockData(BaseModel):
    profile: Optional[StockProfile]
    quote: Optional[StockQuote]
    chart_intraday: List[IntradayChartPoint]

# --- Logging Helper ---
def log_data_summary(endpoint_name: str, data: dict | list):
    """Logs a clean, readable summary of the data being returned."""
    try:
        summary = {}
        if isinstance(data, dict):
            for key, value in data.items():
                if isinstance(value, list):
                    summary[key] = f"List with {len(value)} items"
                elif value is not None:
                    summary[key] = "Data present"
                else:
                    summary[key] = "None"
        elif isinstance(data, list):
            summary = {"response": f"List with {len(data)} items"}
        
        pretty_summary = json.dumps(summary, indent=2)
        logging.info(f"<{endpoint_name}> - Returning data summary:\n{pretty_summary}")
    except Exception as e:
        logging.error(f"Failed to create data summary for {endpoint_name}: {e}")

# --- API Call Helper ---
async def fetch_fmp_data(endpoint: str, client: httpx.AsyncClient):
    """A helper function to fetch data from the FMP API."""
    logging.info(f"Fetching data from FMP endpoint: {endpoint}")
    url = f"{BASE_URL}{endpoint}?apikey={API_KEY}"
    try:
        response = await client.get(url)
        response.raise_for_status()
        logging.info(f"Successfully fetched data from: {endpoint}")
        data = response.json()
        return data if data else None
    except httpx.HTTPStatusError as exc:
        logging.error(f"API request failed for {endpoint}: {exc.response.status_code} - {exc.response.text}")
        raise HTTPException(status_code=exc.response.status_code, detail=f"Error from external API: {exc.response.text}")
    except Exception as e:
        logging.critical(f"An unexpected error occurred for {endpoint}: {e}")
        raise HTTPException(status_code=500, detail="An unexpected internal error occurred.")

# --- API Endpoints ---
@app.get("/")
def read_root():
    """Root endpoint for health checks."""
    return {
        "message": "Stock Analytics API is running.",
        "api_key_status": "CONFIGURED",
        "docs_url": "/docs"
    }

@app.get("/api/quote/{ticker}", response_model=StockQuote)
async def get_quote(ticker: str):
    """Endpoint to get the latest quote for a stock."""
    async with httpx.AsyncClient() as client:
        quote_data = await fetch_fmp_data(f"/quote/{ticker}", client)
    
    if isinstance(quote_data, list) and quote_data:
        processed_data = quote_data[0]
        log_data_summary("get_quote", processed_data)
        return processed_data
    
    raise HTTPException(status_code=404, detail="Quote data for ticker not found.")

@app.get("/api/historical/daily/{ticker}", response_model=List[HistoricalDataPoint])
async def get_historical_daily(ticker: str):
    """Endpoint to get daily historical data."""
    async with httpx.AsyncClient() as client:
        historical_data = await fetch_fmp_data(f"/historical-price-full/{ticker}", client)
    
    if historical_data and "historical" in historical_data:
        processed_data = historical_data["historical"]
        log_data_summary("get_historical_daily", processed_data)
        return processed_data
        
    return []

@app.get("/api/stock/{ticker}", response_model=CombinedStockData)
async def get_stock_all_data(ticker: str):
    """Endpoint to get a combined set of data for a stock ticker concurrently."""
    async with httpx.AsyncClient() as client:
        tasks = [
            fetch_fmp_data(f"/profile/{ticker}", client),
            fetch_fmp_data(f"/quote/{ticker}", client),
            fetch_fmp_data(f"/historical-chart/5min/{ticker}", client)
        ]
        profile_data, quote_data, intraday_data = await asyncio.gather(*tasks)

    if not any([profile_data, quote_data, intraday_data]):
        raise HTTPException(status_code=404, detail=f"Could not retrieve any data for ticker {ticker}.")

    processed_data = {
        "profile": profile_data[0] if isinstance(profile_data, list) and profile_data else None,
        "quote": quote_data[0] if isinstance(quote_data, list) and quote_data else None,
        "chart_intraday": intraday_data if isinstance(intraday_data, list) else []
    }
    log_data_summary("get_stock_all_data", processed_data)
    return processed_data
